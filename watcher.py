import os
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
        print("🛑 Cleaning up folder-associated processes...")
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

def create_github_issue(conf, error_msg):
    """Creates a GitHub issue when a merge conflict occurs."""
    print("📢 Reporting conflict to GitHub Issues...")
    
    url = f"https://api.github.com/repos/{conf['REPO_OWNER']}/{conf['REPO_NAME']}/issues"
    headers = {
        "Authorization": f"token {conf['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": f"⚠️ Merge Conflict on Node: {os.uname()[1] if os.name != 'nt' else 'Main-PC'}",
        "body": f"The Watcher encountered a conflict while syncing **{conf['BRANCH']}**.\n\n**Error Output:**\n```\n{error_msg}\n```\n\n*This issue was generated automatically by the Hive Watcher.*",
        "labels": ["bug", "sync-conflict"]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 201:
            print("✅ Issue created successfully.")
        else:
            print(f"❌ Failed to create issue: {response.status_code}")
    except Exception as e:
        print(f"❌ API Error: {e}")

def sync(conf):
    if conf.get('IS_NODE') == "True":
        # Nodes stay ruthless
        run("git fetch origin")
        run(f"git reset --hard origin/{conf['BRANCH']}")
        relaunch_node(conf)
    else:
        # PC handles merge with Issue reporting
        print("Attempting Merge...")
        result = subprocess.run(f"git pull origin {conf['BRANCH']}", shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("CONFLICT DETECTED!")
            # Trigger the GitHub Issue
            create_github_issue(conf, result.stderr + result.stdout)
        else:
            if "Already up to date" not in result.stdout:
                relaunch_node(conf)

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


