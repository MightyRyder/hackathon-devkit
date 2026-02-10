import os
import sys
import time
import subprocess
import re
import site
import importlib

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

active_conflict_issue_id = None
conf = get_config()
DEBUG_MODE = conf.get("DEBUG_MODE", "False") == "True"

def run(cmd, capture=True, check_errors=False):
    ts = time.strftime("%H:%M:%S")
    if DEBUG_MODE:
        print(f"[{ts}] [DEBUG] $ {cmd}")

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=capture,
        text=True
    )

    # Catch failures if we explicitly ask for it, or if it's a critical error
    if result.returncode != 0 and (check_errors or DEBUG_MODE):
        print(f"[{ts}] [ERROR] Command failed: {cmd}")
        if result.stderr:
            print(f"--- stderr ---\n{result.stderr.strip()}\n--------------")
    
    return result

print("Installing requirements.txt...")
run("pip install --user -r requirements.txt")

importlib.invalidate_caches()
site.main()

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

def alert_user_of_push(branch_name):
    title = "GIT OVERWRITE WARNING"
    message = (f"A push to the '{branch_name}' branch has been detected.\n\n"
               "Check the watcher terminal for details.")
    os_type = platform.system()
    if os_type == "Windows":
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x00 | 0x30 | 0x1000)
    elif os_type == "Darwin":
        cmd = f'display alert "{title}" message "{message}" buttons {{"OK"}} default button "OK"'
        run(f"osascript -e '{cmd}'")
    elif os_type == "Linux":
        try:
            run(f"zenity --warning --title '{title}' --text '{message}'")
        except FileNotFoundError:
            print(f"\n*** ALERT: {message} ***\n")

def touch_files(target_files=None):
    """Updates modification timestamps. If target_files is provided, only touches those."""
    if target_files:
        files_to_touch = target_files
    else:
        # Fallback to walking if no list is provided
        files_to_touch = []
        for root, _, files in os.walk("."):
            if ".git" in root: continue
            for f in files:
                if f.endswith((".py", ".txt", ".sh", ".js")):
                    files_to_touch.append(os.path.join(root, f))
    
    for f in files_to_touch:
        try:
            os.utime(f, None)
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
        
        except Exception as e:
            if DEBUG_MODE:
                ts = time.strftime("%H:%M:%S")
                
                print(f"[{ts}] [DEBUG] GitHub API Error: {e}")
            # Even in non-debug, a tiny hint helps
            else:
                print("! GitHub Issue Sync paused (Network/Token issue)")
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
        print("\n[-] Scanning for runnable services...")
        interpreters = {".py": "python3", ".sh": "bash", ".js": "node"}
        targets = []
        if conf.get('RUN_BACKEND') == "True": targets.append("backend")
        if conf.get('RUN_FRONTEND') == "True": targets.append("frontend")

        existing_sessions_raw = run("tmux ls -F '#S' 2>/dev/null || true", capture=True).stdout
        existing_sessions = existing_sessions_raw.splitlines()

        for session in existing_sessions:
            if any(ext.replace('.', '_') in session for ext in interpreters):
                run(f"tmux kill-session -t {session}", capture=True)

        for folder in targets:
            if not os.path.exists(folder): continue
            for root, _, files in os.walk(folder):
                for file in files:
                    name, ext = os.path.splitext(file)
                    if ext in interpreters and not file.startswith("_") and "utils" not in file.lower():
                        full_path = os.path.abspath(os.path.join(root, file))
                        session_name = f"{name}_{ext.replace('.', '')}"
                        cmd = f"{interpreters[ext]} {full_path}"
                        print(f"  [+] Launching {file} -> Tmux: {session_name}")
                        run(f"tmux new-session -d -s {session_name} '{cmd}'")

        print("[!] All services initialized.\n")

def sync(conf):
    ts = time.strftime("%H:%M:%S")
    branch = conf.get('BRANCH', 'main')
    is_node = conf.get('IS_NODE') == "True"
    
    old_sha = run("git rev-parse HEAD").stdout.strip()

    if is_node: 
        print(f"[{ts}] Auto-resetting...")
        run(f"git reset --hard origin/{branch}")
        touch_files(); relaunch_node(conf)
        return

    # ATTEMPT AUTO-MERGE
    # This is what handles 2 devs on 1 file (if they touch different lines)
    result = run(f"git merge origin/{branch}")
    
    if result.returncode != 0:
        # DETECT CONFLICTS
        unmerged_res = run("git diff --name-only --diff-filter=U")
        conflicted_files = unmerged_res.stdout.splitlines()

        if not conflicted_files and "overwritten by merge" in result.stderr:
            match = re.search(r"overwritten by merge:\n(.*?)(?:\nPl(?:ease|s)|$)", result.stderr, re.DOTALL)
            if match:
                conflicted_files = [line.strip() for line in match.group(1).splitlines() if line.strip()]

        if not conflicted_files:
            run(f"git reset --mixed origin/{branch}")
            return

        alert_user_of_push(branch)  

        # SHOW COMPARISON (Lines added/removed)
        print("\n--- INCOMING CHANGES SUMMARY ---")
        # Shows +/- lines per file
        diff_stat = run(f"git diff --stat HEAD..origin/{branch}")
        print(diff_stat.stdout if diff_stat.stdout else "Large file changes detected.")
        print("--------------------------------\n")

        handle_github_issue(conf, result.stderr + result.stdout)
        
        print(f"!!! CONFLICT IN: {', '.join(conflicted_files)} !!!")
        
        while True:
            print("\nOptions:")
            print("[y] Overwrite ALL (Take remote version, LOSE local edits)")
            print("[n] Open Visual Merge Editor (Try to SAVE both sets of edits)")
            
            choice = input("Select an option (y/n): ").lower().strip()
            
            if choice == 'y':
                print("Performing overwrite...")
                if os.path.exists(".git/MERGE_HEAD"):
                    run("git merge --abort")
                for f in conflicted_files:
                    run(f"git checkout origin/{branch} -- {f}")
                    run(f"git add {f}")
                run(f"git reset --mixed origin/{branch}")
                handle_github_issue(conf, "", resolve=True)
                touch_files(); relaunch_node(conf)
                break 

            elif choice == 'n':
                print("Preparing files for merge...")
                run("git stash")
                run(f"git pull origin {branch}")
                
                print("Applying your local changes back...")
                # We capture output to see if it merged cleanly or hit a conflict
                pop_res = run("git stash pop")
                
                # If 'conflict' is in the message, markers exist.
                if "conflict" in pop_res.stdout.lower() or "conflict" in pop_res.stderr.lower():
                    print("\n[!] CONFLICT DETECTED. Opening files for manual fix...")
                else:
                    print("\n[+] Changes merged CLEANLY. No markers needed.")

                for f in conflicted_files:
                    run(f"code {f}")
                
                print("\n>>> SCRIPT PAUSED.")
                print("1. Review files in VS Code.")
                print("2. If markers (<<<<<<<) exist, resolve them and SAVE.")
                input("3. Press Enter HERE once finished...")
                
                for f in conflicted_files:
                    run(f"git add {f}")
                
                # Final check to see if markers are still in the file
                markers_found = False
                for f in conflicted_files:
                    if contains_markers(f):
                        markers_found = True
                        break
                
                if markers_found:
                    print("\n[!] Markers still found in files! Please fix them properly.")
                    continue

                print("Merge finalized.")
                handle_github_issue(conf, "", resolve=True)
                touch_files(); relaunch_node(conf)
                break
            else:
                print("[!] Invalid choice. Please enter 'y' or 'n'.")
    else:
        # Success: Git handled the 2-dev merge automatically
        new_sha = run("git rev-parse HEAD").stdout.strip()
        if old_sha != new_sha:
            handle_github_issue(conf, "", resolve=True)
            touch_files(); relaunch_node(conf)

def contains_markers(filepath):
    """Checks for conflict markers line-by-line (RAM efficient)."""
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, 'r', errors='ignore') as f:
            for line in f:
                if "<<<<<<<" in line:
                    return True
    except:
        pass
    return False

def main():
    conf = get_config()
    print(f"Watcher Online | Branch: {conf['BRANCH']}")
    
    if conf.get('IS_NODE') == "True":
        print("First launch: Starting tmux services...")
        relaunch_node(conf)

    while True:
        try:
            # 1. Fetch first so local tracking knows about remote
            run("git fetch origin")
            
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

