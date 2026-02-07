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

def restart_all_apps(conf):
    print("Terminating existing python applications...")
    
    my_pid = os.getpid()
    
    if os.name == 'nt':
        # --- WINDOWS CLEANUP ---
        # Kill all other python processes except this one
        # We use a filter to find python.exe but skip our own PID
        cmd = f'taskkill /F /FI "IMAGENAME eq python.exe" /FI "PID ne {my_pid}"'
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # --- LINUX CLEANUP ---
        try:
            cmd = f"ps -ef | grep python3 | grep -v grep | grep -v {my_pid} | awk '{{print $2}}' | xargs -r kill -9"
            subprocess.run(cmd, shell=True)
        except:
            pass

    # Re-apply systemd restart ONLY if on a Pi Node
    if conf.get('IS_NODE') == "True":
        print("🚀 Restarting Main Node Service...")
        subprocess.run("sudo systemctl restart hackathon-app.service", shell=True)
    
    print("♻️  Refreshing Watcher logic...")
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
        print("📦 Checking dependencies...")
        run(f"{sys.executable} -m pip install -r requirements.txt")
        
    # Pi Node Specific: Restart systemd app
    if conf.get('IS_NODE') == "True":
        print("Restarting Node Service...")
        run("sudo systemctl restart hackathon-app.service")
    
    print("System Ready.")
    
    # Check if the watcher itself was updated; if so, restart it
    restart_all_apps(conf)

def main():
    conf = get_config()
    print(f"Watcher Online | Branch: {conf['BRANCH']}")
    
    while True:
        try:
            run("git fetch origin")
            status = run("git status -uno").stdout
            
            if "behind" in status or "can be fast-forwarded" in status:
                sync(conf)
            
        except Exception as e:
            print(f"Warning: Sync cycle failed: {e}")
            
        time.sleep(20)

if __name__ == "__main__":

    main()
