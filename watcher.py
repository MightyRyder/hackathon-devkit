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
               "Check the watcher terminal for details.")
    os_type = platform.system()
    if os_type == "Windows":
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x00 | 0x30 | 0x1000)
    elif os_type == "Darwin":
        cmd = f'display alert "{title}" message "{message}" buttons {{"OK"}} default button "OK"'
        subprocess.run(['osascript', '-e', cmd])
    elif os_type == "Linux":
        try:
            subprocess.run(['zenity', '--warning', '--title', title, '--text', message])
        except FileNotFoundError:
            print(f"\n*** ALERT: {message} ***\n")

def touch_files():
    """Updates modification timestamps so VS Code refreshes."""
    for root, dirs, files in os.walk("."):
        if ".git" in root: continue
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
    if resolve and active_conflict_issue_id:
        url = f"https://api.github.com/repos/{conf.get('REPO_OWNER')}/{conf.get('REPO_NAME')}/issues/{active_conflict_issue_id}"
        try:
            requests.patch(url, headers=headers, json={"state": "closed"})
            print(f"Conflict resolved. Closed Issue #{active_conflict_issue_id}")
            active_conflict_issue_id = None
        except:
            pass
        return

    if not resolve and active_conflict_issue_id is None:
        print("Reporting conflict to GitHub Issues...")
        try:
            diff_data = subprocess.check_output(f"git diff HEAD..origin/{conf['BRANCH']}", shell=True, text=True)[:2000]
        except:
            diff_data = "Could not generate diff summary."
        url = f"https://api.github.com/repos/{conf.get('REPO_OWNER')}/{conf.get('REPO_NAME')}/issues"
        data = {
            "title": f"Sync Conflict: {platform.node()}",
            "body": f"Merge failed on `{conf['BRANCH']}`.\n\n```diff\n{diff_data}\n```\n**Error:**\n{error_msg}",
            "labels": ["bug", "sync-issue"]
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 201:
                active_conflict_issue_id = response.json().get('number')
                print(f"Issue created: #{active_conflict_issue_id}")
        except Exception as e:
            print(f"Failed to connect to GitHub API: {e}")

def relaunch_node(conf):
    if conf.get('IS_NODE') == "True":
        my_pid = os.getpid()
        print("Relaunching services...")
        # ... (Rest of your original relaunch_node logic stays the same) ...
        # [Truncated for brevity, but keep your existing implementation here]
        pass

def sync(conf):
    ts = time.strftime("%H:%M:%S")
    branch = conf.get('BRANCH', 'main')
    is_node = conf.get('IS_NODE') == "True"
    
    # Track state before attempt
    old_sha = run("git rev-parse HEAD").stdout.strip()

    if is_node:
        print(f"[{ts}] Node Mode: Force-resetting...")
        subprocess.run(f"git reset --hard origin/{branch}", shell=True, capture_output=True)
        touch_files()
        relaunch_node(conf)
        return

    # Attempt merge
    result = subprocess.run(f"git merge origin/{branch}", shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        # DETECT CONFLICTS (B: Only find what needs to be changed)
        unmerged_res = subprocess.run("git diff --name-only --diff-filter=U", shell=True, capture_output=True, text=True)
        conflicted_files = unmerged_res.stdout.splitlines()

        # Dirty tree check (files that would be overwritten)
        if not conflicted_files and "overwritten by merge" in result.stderr:
            match = re.search(r"overwritten by merge:\n(.*?)(?:\nPl(?:ease|s)|$)", result.stderr, re.DOTALL)
            if match:
                conflicted_files = [line.strip() for line in match.group(1).splitlines() if line.strip()]

        if not conflicted_files:
            # Fallback to prevent infinite loops if something else is wrong
            subprocess.run(f"git reset --mixed origin/{branch}", shell=True, capture_output=True)
            return

        # A: THE COMPARISON (Show the user exactly what is different)
        print("\n--- CODE DIFFERENCES (REMOTE vs LOCAL) ---")
        # Shows lines added/missing for the conflicted files
        diff_view = subprocess.run(f"git diff --stat origin/{branch}", shell=True, capture_output=True, text=True).stdout
        print(diff_view if diff_view else "Binary or complex changes detected.")
        print("------------------------------------------\n")

        handle_github_issue(conf, result.stderr + result.stdout)
        print(f"CONFLICTED FILES: {', '.join(conflicted_files)}")
        choice = input("Overwrite ONLY these files with remote version? (y/n): ").lower().strip()
        
        if choice == 'y':
            # Safely clear merge state only if it exists
            if os.path.exists(".git/MERGE_HEAD"):
                subprocess.run("git merge --abort", shell=True, capture_output=True)
            
            # B: SURGICAL CHANGE (Only touch the specific files)
            for f in conflicted_files:
                print(f"Updating {f}...")
                # This pulls the remote version of JUST this file
                subprocess.run(f"git checkout origin/{branch} -- {f}", shell=True, capture_output=True)
                subprocess.run(f"git add {f}", shell=True, capture_output=True)
            
            # Finalize: Move the pointer forward
            subprocess.run(f"git reset --mixed origin/{branch}", shell=True, capture_output=True)
            
            handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)
        else:
            if os.path.exists(".git/MERGE_HEAD"):
                subprocess.run("git merge --abort", shell=True, capture_output=True)
            print(f"[{ts}] Sync aborted. Local changes kept.")
    else:
        # Clean merge success
        new_sha = run("git rev-parse HEAD").stdout.strip()
        if old_sha != new_sha:
            handle_github_issue(conf, "", resolve=True)
            touch_files()
            relaunch_node(conf)

def main():
    conf = get_config()
    print(f"Watcher Online | Branch: {conf['BRANCH']}")
    
    while True:
        try:
            # 1. Fetch first so local tracking knows about remote
            subprocess.run("git fetch origin", shell=True, capture_output=True)
            
            # 2. Count how many commits the remote is ahead of us
            # This is much more stable than comparing raw SHAs
            check_behind = run(f"git rev-list --count HEAD..origin/{conf['BRANCH']}")
            behind_count = int(check_behind.stdout.strip() or 0)

            if behind_count > 0:
                print(f"[{time.strftime('%H:%M:%S')}] {behind_count} new commit(s) detected.")
                sync(conf)
                print(f"[{time.strftime('%H:%M:%S')}] Sync finished.")
                
        except Exception as e:
            print(f"Connection glitch: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    main()