import os
import sys
import time
import subprocess
import json
import requests
import signal
import platform
import ctypes

print("Watcher Mode:")
print("- Auto-sync enabled with other teammates on the same it ")
print("- May overwrite local changes")
print("- Conflicts will be reported to GitHub")
print("- Press Ctrl+C to stop")

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

def alert_user_of_push(branch_name):
    title = "GIT OVERWRITE WARNING"
    message = (f"A push to the '{branch_name}' branch has been detected.\n\n"
               "This may overwrite your local code. Check the watcher terminal "
               "window for details and the detailed sync prompt.")
    
    os_type = platform.system()

    # 1. WINDOWS: 0x00 (OK button) | 0x30 (Warning Icon) | 0x1000 (Always on Top)
    if os_type == "Windows":
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x00 | 0x30 | 0x1000)

    # 2. MACOS: Simple alert via AppleScript
    elif os_type == "Darwin":
        cmd = f'display alert "{title}" message "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', cmd])

    # 3. LINUX: Using zenity --warning
    elif os_type == "Linux":
        try:
            subprocess.run(['zenity', '--warning', '--title', title, '--text', message])
        except FileNotFoundError:
            print(f"\n*** ALERT: {message} ***\n")

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
    branch = conf.get('BRANCH', 'main')
    is_node = conf.get('IS_NODE') == "True"
    
    print(f"[{ts}] Syncing {branch}...")
    subprocess.run("git fetch origin", shell=True, capture_output=True)

    # 1. THE NODE PATH: Full Automation
    if is_node:
        print(f"[{ts}] Node Mode: Force-resetting to match remote...")
        res = subprocess.run(f"git reset --hard origin/{branch}", shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)
        return

    # 2. THE DEVELOPER PATH: Surgical Protection
    result = subprocess.run(f"git merge origin/{branch}", shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        alert_user_of_push(branch)
        
        print("\n--- CONFLICT DETAILS ---")
        conflicts = subprocess.run("git diff --color=always", shell=True, capture_output=True, text=True).stdout
        print(conflicts if conflicts else "Conflict markers detected.")
        print("------------------------\n")

        handle_github_issue(conf, result.stderr + result.stdout)
        
        print("MERGE CONFLICT DETECTED.")
        choice = input("Overwrite ONLY conflicted lines? (y/n): ").lower().strip()
        
        if choice == 'y':
            # BACKUP: Only saves the current state of tracked files
            subprocess.run("git diff > last_conflict_backup.patch", shell=True)
            
            # SURGICAL RECOVERY
            # Get only the files that are actually broken/unmerged
            unmerged_res = subprocess.run("git diff --name-only --diff-filter=U", shell=True, capture_output=True, text=True)
            all_to_fix = unmerged_res.stdout.splitlines()

            for f in all_to_fix:
                print(f"Surgically syncing {f}...")
                # Remove from conflict state
                subprocess.run(f"git reset HEAD -- {f}", shell=True, capture_output=True)
                # Overwrite just this file with remote version
                subprocess.run(f"git checkout origin/{branch} -- {f}", shell=True, capture_output=True)
            
            # Abort the 'merge state' so git is clean again
            subprocess.run("git merge --abort", shell=True, capture_output=True)
            
            handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)
            print("Surgical sync complete. Your untracked .py files were preserved.")
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