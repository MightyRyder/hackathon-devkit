import os
import re
import sys
import time
import subprocess
import json
import requests
import signal
import platform
import ctypes

print("Watcher Mode:")
print("- Auto-sync enabled with other teammates on the same branch")
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
                # Get PIDs using the current directory
                pids = subprocess.check_output(["fuser", "."]).decode().split()
                
                for pid_str in pids:
                    pid = int(pid_str)
                    if pid == my_pid:
                        continue
                    
                    try:
                        # 1. Get the command line arguments for this PID
                        with open(f"/proc/{pid}/cmdline", "rb") as f:
                            # cmdline is null-terminated, so we split by \x00
                            args = f.read().split(b'\x00')
                        
                        # 2. Look for the script path (usually the second arg)
                        # and check if that file contains your cluster header
                        for arg in args:
                            arg_str = arg.decode().strip()
                            if arg_str.endswith(".py") and os.path.exists(arg_str):
                                with open(arg_str, "r") as script_file:
                                    header = script_file.readline()
                                    if "# cluster-start" in header.lower():
                                        os.kill(pid, signal.SIGKILL)
                                        break # Found and killed, move to next PID
                    except (FileNotFoundError, ProcessLookupError, PermissionError):
                        continue
            except Exception:
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
        print(f"[{ts}] Force-resetting to match remote...")
        res = subprocess.run(f"git reset --hard origin/{branch}", shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            # handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)
        return

    # 2. THE DEVELOPER PATH: Surgical Protection
    result = subprocess.run(f"git merge origin/{branch}", shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        alert_user_of_push(branch)
        
        # --- LOGIC FIX START ---
        # Step A: Check for active Merge Conflicts (Index State 'U')
        unmerged_res = subprocess.run("git diff --name-only --diff-filter=U", shell=True, capture_output=True, text=True)
        conflicted_files = unmerged_res.stdout.splitlines()

        # Step B: Check for Pre-Merge Aborts (Dirty Tree)
        # If Git aborted because local files would be overwritten, 'diff-filter=U' is empty.
        # We must parse stderr to find the files blocking the merge.
        if not conflicted_files and result.stderr:
             # Look for: "Your local changes to the following files would be overwritten by merge:"
             if "overwritten by merge" in result.stderr:
                 match = re.search(r"overwritten by merge:\n(.*?)(?:\nPl(?:ease|s)|$)", result.stderr, re.DOTALL)
                 if match:
                     # Add the blocking files to our list of conflicts
                     dirty_files = [line.strip() for line in match.group(1).splitlines() if line.strip()]
                     conflicted_files.extend(dirty_files)
        # --- LOGIC FIX END ---

        print("\n--- CONFLICT DETAILS ---")
        conflicts = subprocess.run("git diff --color=always", shell=True, capture_output=True, text=True).stdout
        print(conflicts if conflicts else "Conflict markers detected.")
        print("------------------------\n")

        handle_github_issue(conf, result.stderr + result.stdout)
        
        # Guard clause: If we still can't find files, return to avoid infinite loop
        if not conflicted_files:
            print(f"[{ts}] Merge failed, but no conflicting files could be identified.")
            print("Check your git status manually.")
            return

        print("MERGE CONFLICT DETECTED.")
        print(f"Files requiring overwrite: {', '.join(conflicted_files)}")
        choice = input("Overwrite ONLY conflicted files with remote version? (y/n): ").lower().strip()
        
        if choice == 'y':
            # 1. ABORT: Return to pre-merge state (restores local changes if merge was in progress)
            # Note: If it was a Dirty Tree abort, this command does nothing, which is fine.
            subprocess.run("git merge --abort", shell=True, capture_output=True)
            
            # 2. BACKUP: Save the local changes that we are about to overwrite
            subprocess.run("git diff > local_changes_backup.patch", shell=True)
            
            # 3. SURGICAL REPAIR
            for f in conflicted_files:
                print(f"Surgically syncing {f}...")
                # Checkout the remote version ONLY for this file
                subprocess.run(f"git checkout origin/{branch} -- {f}", shell=True, capture_output=True)
                # Stage it immediately
                subprocess.run(f"git add {f}", shell=True, capture_output=True)
            
            subprocess.run(f"git reset --soft origin/{branch}", shell=True)

            # 5. API PROTECTION
            handle_github_issue(conf, "", resolve=True)
            
            touch_files()
            relaunch_node(conf)
            print("Overwrite complete. Local changes preserved where possible.")
        else:
            print(f"[{ts}] Sync aborted. Local changes preserved.")
            subprocess.run("git merge --abort", shell=True, capture_output=True)
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
                    print(f"[{time.strftime('%H:%M:%S')}] Sync finished.")
            else:
                print(f"Git Remote Check Failed: {remote_check_res.stderr}")
                
        except Exception as e:
            print(f"Connection glitch: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    main()