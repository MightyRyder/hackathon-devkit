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
                # We look for '# hive-start' in the first 2 lines of the file
                try:
                    with open(filename, 'r') as f:
                        header = f.read(100) # Just read the beginning
                    
                    if "# hive-start" in header.lower():
                        print(f"🚀 Starting Hive Service: {filename}")
                        
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

    # 3. Restart watcher
    print("Refreshing Watcher logic...")
    time.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def sync(conf):
    print(f"[{time.strftime('%H:%M:%S')}] Syncing {conf['BRANCH']}...")
    
    # Force remote URL to use the token for auth
    run(f"git remote set-url origin {conf['REPO_URL']}")
    
    # Wipe local changes to prevent merge conflicts
    run("git fetch origin")
    run(f"git reset --hard origin/{conf['BRANCH']}")
    
    # Update libraries if they changed
    if os.path.exists("requirements.txt"):
        print("Checking dependencies...")
        run(f"{sys.executable} -m pip install -r requirements.txt")
    
    print("System Ready.")
    
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






