/import os
import sys
import time
import subprocess

def get_config():
    conf = {}
    if not os.path.exists("config.txt"):
        print("Error: config.txt not found!")
        sys.exit(1)
    with open("config.txt", "r") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                conf[k] = v
    return conf

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def relaunch_node(conf):
    if conf.get('IS_NODE') == "True":
        my_pid = os.getpid()
        
        # 1. SURGICAL KILL (As before)
        print("Cleaning up folder-associated processes...")
        try:
            pids = subprocess.check_output(["fuser", "."]).decode().split()
            for pid in pids:
                if int(pid) != my_pid:
                    os.kill(int(pid), signal.SIGKILL)
        except:
            pass
    
        # 2. DYNAMIC RELAUNCH PHASE
        os.makedirs("logs", exist_ok=True)
        
        # Scan every file in the root
        for filename in os.listdir("."):
            if filename.endswith(".py") and filename != "watcher.py":
                
                # Check if the file SHOULD be started
                # We look for '# cluster-start' in the first 2 lines of the file
                try:
                    with open(filename, 'r') as f:
                        header = f.read(100) # Just read the beginning
                    
                    if "# cluster-start" in header.lower():
                        print(f"Starting cluster Service: {filename}")
                        
                        log_file = f"logs/{filename}.log"
                        with open(log_file, "a") as log_out:
                            # Use Popen so they all run simultaneously in the background
                            subprocess.Popen(
                                [sys.executable, filename],
                                stdout=log_out,
                                stderr=log_out,
                                preexec_fn=os.setpid # Ensures it stays in its own process group
                            )
                except Exception as e:
                    print(f"Could not scan {filename}: {e}")

import json

def handle_github_issue(conf, error_msg, resolve=False):
    global active_conflict_issue_id
    
    headers = {
        "Authorization": f"token {conf['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # RESOLVE: Close the issue if the sync finally works
    if resolve and active_conflict_issue_id:
        url = f"https://api.github.com/repos/{conf['REPO_OWNER']}/{conf['REPO_NAME']}/issues/{active_conflict_issue_id}"
        requests.patch(url, headers=headers, data=json.dumps({"state": "closed"}))
        print(f"Conflict resolved. Closed Issue #{active_conflict_issue_id}")
        active_conflict_issue_id = None
        return

    # CREATE: Only if we haven't already reported this specific conflict
    if not resolve and active_conflict_issue_id is None:
        url = f"https://api.github.com/repos/{conf['REPO_OWNER']}/{conf['REPO_NAME']}/issues"
        node_name = os.uname()[1] if os.name != 'nt' else "Main-PC"
        
        data = {
            "title": f"Sync Conflict: {node_name}",
            "body": f"Merge failed on branch **{conf['BRANCH']}**.\n\n**Error:**\n```\n{error_msg}\n```",
            "labels": ["bug", "hive-conflict"]
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 201:
                active_conflict_issue_id = response.json().get('number')
                print(f"Issue created: #{active_conflict_issue_id}")
            else:
                print(f"API Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Failed to connect to GitHub API: {e}")

def touch_files():
    """Update timestamps of all python files to force VS Code to refresh."""
    for root, dirs, files in os.walk("."):
        for f in files:
            if f.endswith((".py", ".txt", ".sh")):
                file_path = os.path.join(root, f)
                try:
                    # 'Touching' the file updates the Last Modified timestamp
                    os.utime(file_path, None)
                except Exception:
                    pass

def sync(conf):
    print(f"🔄 Syncing {conf['BRANCH']}...")
    
    # Try the pull
    result = subprocess.run(f"git pull origin {conf['BRANCH']}", shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        # PULL FAILED: Report it (if not already reported)
        handle_github_issue(conf, result.stderr + result.stdout)
        return False # Signal that sync failed
    else:
        touch_files()
        handle_github_issue(conf, "", resolve=True)
        relaunch_node(conf)
        return True

def main():
    conf = get_config()
    print(f"Watcher Online | Branch: {conf['BRANCH']}")
    
    while True:
        try:
            # This just checks the 'ID' without downloading anything heavy
            remote_check = run(f"git ls-remote origin {conf['BRANCH']}").stdout.split()[0]
            local_sha = run("git rev-parse HEAD").stdout.strip()

            if local_sha != remote_check:
                sync(conf)
                
        except Exception as e:
            print(f"Connection glitch: {e}")
            
        time.sleep(5)

if __name__ == "__main__":

    main()




