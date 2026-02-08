import os
import sys
import subprocess

def check_git_identity():
    # Check if name is set
    name = subprocess.run("git config user.name", shell=True, capture_output=True, text=True).stdout.strip()
    # Check if email is set
    email = subprocess.run("git config user.email", shell=True, capture_output=True, text=True).stdout.strip()

    if not name or not email:
        print("GIT identity not set. GIT requires a name and email to commit changes.")
        # You can hardcode your info here for the hackathon to save time
        new_name = input("Enter your GitHub Name: ").strip()
        new_email = input("Enter your GitHub Email: ").strip()
        
        subprocess.run(f'git config user.name "{new_name}"', shell=True)
        subprocess.run(f'git config user.email "{new_email}"', shell=True)
        print(f"Identity set to {new_name} <{new_email}>")

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

    check_git_identity()
    
    print(f"Checking remote status for {branch}...")
    
    # 1. SYNC GUARD: Check if we are behind the remote
    subprocess.run("git fetch origin", shell=True, capture_output=True)
    behind = subprocess.run(
        f"git rev-list --count HEAD..origin/{branch}",
        shell=True, capture_output=True, text=True
    ).stdout.strip()

    if behind != "0" and behind != "":
        print(f"FAILED: Your branch is behind by {behind} commits.")
        print("Run watcher sync (or git pull) before pushing your changes.")
        return

    # 2. STATUS CHECK: Porcelain for the logic, --stat for the user
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True).stdout
    if not status:
        print("No changes detected. Nothing to push.")
        return

    print("\nFiles modified:")
    subprocess.run("git diff --stat", shell=True)
    
    # 3. USER INPUT
    msg = input("\nEnter commit message (or Enter to cancel): ").strip()
    if not msg:
        print("Push aborted.")
        return

    try:
        print("Staging changes...")
        subprocess.run("git add .", shell=True)
        
        # 4. QUOTE-SAFE COMMIT
        # We avoid shell=True here to prevent injection and handle special characters
        subprocess.run(["git", "commit", "-m", msg], capture_output=True)
        
        print(f"Pushing to origin {branch}...")
        result = subprocess.run(f"git push origin {branch}", shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Successfully pushed to GitHub.")
        else:
            print(f"Push failed: {result.stderr}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    push()