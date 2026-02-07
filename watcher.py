import os
import sys
import time
import subprocess
import json
import requests
import signal
import platform

# Global tracker for GitHub issues to prevent spam
active_conflict_issue_id = None

def get_config():
    conf = {}
    if not os.path.exists("config.txt"):
        print("Error: config.txt not found! Run setup.py first.")
        sys.exit(1)
    with open("config.txt", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                conf[k.strip()] = v.strip()
    return conf

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def touch_files():
    """Forces VS Code to refresh by updating file modification timestamps."""
    for root, dirs, files in os.walk("."):
        for f in files:
            if f.endswith((".py", ".txt", ".sh", ".js")):
                try:
                    os.utime(os.path.join(root, f), None)
                except:
                    pass

def handle_github_issue(conf, error_msg, resolve=False):
    global active_conflict_issue_id
    
    headers = {
        "Authorization": f"token {conf.get('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # RESOLVE: Close the issue if the sync finally works
    if resolve and active_conflict_issue_id:
        url = f"https://api.github.com/repos/{conf.get('REPO_OWNER')}/{conf.get('REPO_NAME')}/issues/{active_conflict_issue_id}"
        try:
            requests.patch(url, headers=headers, json={"state": "closed"})
            print(f"Conflict resolved. Closed Issue #{active_conflict_issue_id}")
            active_conflict_issue_id = None
        except:
            pass
        return

    # CREATE: Only if we haven't already reported this specific conflict
    if not resolve and active_conflict_issue_id is None:
        print("Reporting conflict to GitHub Issues...")
        
        # Grab the actual code differences
        try:
            diff_data = subprocess.check_output(
                f"git diff HEAD..origin/{conf['BRANCH']}", 
                shell=True, text=True
            )[:2000]
        except:
            diff_data = "Could not generate diff summary."

        url = f"https://api.github.com/repos/{conf.get('REPO_OWNER')}/{conf.get('REPO_NAME')}/issues"
        node_name = platform.node()
        
        data = {
            "title": f"Sync Conflict: {node_name}",
            "body": (
                f"### Conflict on {node_name}\n"
                f"Merge failed on branch `{conf['BRANCH']}`.\n\n"
                f"#### Code Comparison:\n"
                f"```diff\n{diff_data}\n```\n"
                f"**Raw Error:**\n```\n{error_msg}\n```"
            ),
            "labels": ["bug", "sync-issue"]
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 201:
                active_conflict_issue_id = response.json().get('number')
                print(f"Issue created: #{active_conflict_issue_id}")
            else:
                print(f"GitHub API Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Failed to connect to GitHub API: {e}")

def relaunch_node(conf):
    if conf.get('IS_NODE') == "True":
        my_pid = os.getpid()
        print("Cleaning up existing processes...")
        
        # Cleanup logic (Platform specific)
        if platform.system() != "Windows":
            try:
                pids = subprocess.check_output(["fuser", "."]).decode().split()
                for pid in pids:
                    if int(pid) != my_pid:
                        os.kill(int(pid), signal.SIGKILL)
            except:
                pass
        
        os.makedirs("logs", exist_ok=True)
        
        for filename in os.listdir("."):
            if filename.endswith(".py") and filename != "watcher.py":
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        header = f.read(150)
                    
                    if "# cluster-start" in header.lower():
                        print(f"Launching Service: {filename}")
                        log_file = f"logs/{filename}.log"
                        with open(log_file, "a") as log_out:
                            kwargs = {}
                            if platform.system() != "Windows":
                                kwargs.update(preexec_fn=os.setsid)
                                
                            subprocess.Popen(
                                [sys.executable, filename],
                                stdout=log_out,
                                stderr=log_out,
                                **kwargs
                            )
                except Exception as e:
                    print(f"Could not start {filename}: {e}")

def sync(conf):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] Syncing {conf['BRANCH']}...")
    
    subprocess.run("git fetch origin", shell=True, capture_output=True)
    
    # Attempt merge
    result = subprocess.run(f"git merge origin/{conf['BRANCH']}", shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        # 1. Grab the conflict lines specifically
        # This shows the diff of the unmerged (conflicted) files
        print("\n--- CONFLICT DETAILS ---")
        conflicts = subprocess.run("git diff --color=always", shell=True, capture_output=True, text=True).stdout
        if conflicts:
            print(conflicts)
        else:
            print("Conflict markers detected in file contents.")
        print("------------------------\n")

        handle_github_issue(conf, result.stderr + result.stdout)
        
        print("MERGE CONFLICT DETECTED.")
        choice = input("Overwrite the local lines shown above? (y/n): ").lower().strip()
        
        if choice == 'y':
            print("Backing up to lat_conflict_backup.patch... Use 'git apply last_conflict_backup.patch' to use the backup.")
            subprocess.run(
                "git diff > last_conflict_backup.patch",
                shell=True
            )
            print("Pre-sync snapshot:")
            subprocess.run("git status --porcelain", shell=True)
            # 1. Identify files that git is refusing to merge
            # This handles files that are modified locally and conflict with the incoming pull
            conflicted_files = subprocess.run(f"git diff --name-only origin/{conf['BRANCH']}", shell=True, capture_output=True, text=True).stdout.splitlines()
            
            # Also catch files git explicitly marks as 'Unmerged'
            unmerged_files = subprocess.run("git diff --name-only --diff-filter=U", shell=True, capture_output=True, text=True).stdout.splitlines()
            
            all_to_fix = list(set(conflicted_files + unmerged_files))

            for f in all_to_fix:
                print(f"Force-syncing {f} from remote...")
                # Reset the index for the file first (removes it from the 'conflict' state)
                subprocess.run(f"git reset HEAD -- {f}", shell=True, capture_output=True)
                # Overwrite with the remote version
                subprocess.run(f"git checkout origin/{conf['BRANCH']} -- {f}", shell=True, capture_output=True)
            
            # Try to abort a merge if one exists, but ignore errors if it doesn't
            subprocess.run("git merge --abort", shell=True, capture_output=True)
            
            handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)
            print("Surgical sync complete. File is now updated.")
        else:
            print(f"[{ts}] Sync aborted. Local changes preserved.")
    else:
        if "Already up to date" not in result.stdout:
            handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)

def main():
    conf = get_config()
    print(f"Watcher Online | Branch: {conf['BRANCH']}")
    
    while True:
        try:
            # Quick remote check
            remote_check_res = run(f"git ls-remote origin {conf['BRANCH']}")
            if remote_check_res.returncode == 0:
                remote_sha = remote_check_res.stdout.split()[0]
                local_sha = run("git rev-parse HEAD").stdout.strip()

                if local_sha != remote_sha:
                    sync(conf)
            else:
                print(f"Git Remote Check Failed: {remote_check_res.stderr}")
                
        except Exception as e:
            print(f"Connection glitch: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    main()








