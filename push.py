import os
import sys
import subprocess
import time

def get_config():
    conf = {}
    if not os.path.exists("config.txt"):
        print("Error: config.txt not found!")
        sys.exit(1)
    with open("config.txt", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                conf[k.strip()] = v.strip()
    return conf

def push():
    conf = get_config()
    branch = conf.get("BRANCH", "main")
    
    print(f"Checking remote status for {branch}...")

    # STATUS CHECK: Porcelain for the logic, --stat for the user
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True).stdout
    if not status:
        print("No changes detected. Nothing to push.")
        return

    print("\nFiles modified:")
    subprocess.run("git diff --stat", shell=True)
    
    # USER INPUT
    msg = input("\nEnter commit message (or Enter to cancel): ").strip()
    if not msg:
        print("Push aborted.")
        return

    try:
        print("Staging changes...")
        subprocess.run("git add .", shell=True)
        
        # QUOTE-SAFE COMMIT
        # We avoid shell=True here to prevent injection and handle special characters
        subprocess.run(["git", "commit", "-m", msg], capture_output=True)
        
        print(f"Pushing to origin {branch}...")
        # SYNC GUARD: Check if we are behind the remote
        subprocess.run("git fetch origin", shell=True, capture_output=True)
        behind = subprocess.run(f"git rev-list --count HEAD..origin/{branch}", shell=True, capture_output=True, text=True).stdout.strip()
        if behind != "0" and behind != "":
            RED = "\033[91m"
            RESET = "\033[0m"

            print(f"{RED}WARNING: Your branch is behind by {behind} commits.{RESET}")
            print(f"{RED}Run watcher sync (or git pull) before pushing your changes...otherwise, you may overwrite others' work.{RESET}")
            print(f"{RED}Would you still like to push? Enter 'FORCE' to continue: {RESET}")

            time.sleep(3)

            choice = input().strip().upper()
            if choice != 'FORCE':
                print("Push aborted to prevent overwriting remote changes.")
                return
            else:
                result = subprocess.run(f"git push --force origin {branch}", shell=True, capture_output=True, text=True)
        else:
            result = subprocess.run(f"git push origin {branch}", shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Successfully pushed to GitHub.")
        else:
            print(f"Push failed:\n{result.stdout}\n{result.stderr}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    push()