import os
import platform
import subprocess
import sys

def clear(): os.system('cls' if os.name == 'nt' else 'clear')

def secure_config_file(filepath):
    """Sets file permissions so only the owner can read/write."""
    if platform.system() != "Windows":
        # Equivalent to 'chmod 600'
        # Stat constants: S_IRUSR (read owner), S_IWUSR (write owner)
        os.chmod(filepath, 0o600)
        print(f"Permissions set to 600 for {filepath}")
    else:
        # On Windows, we use 'icacls' to mimic chmod 600
        # This removes access for 'Everyone' and 'Users', leaving only the current user
        try:
            user = os.getlogin()
            subprocess.run(["icacls", filepath, "/inheritance:r"], capture_output=True)
            subprocess.run(["icacls", filepath, "/grant:r", f"{user}:(R,W)"], capture_output=True)
            print(f"Windows ACLs secured for {filepath}")
        except:
            print("Windows security hardening skipped (Non-admin or manual config).")

def check_git_identity():
    # Check if name is set
    name = subprocess.run("git config user.name", shell=True, capture_output=True, text=True).stdout.strip()
    # Check if email is set
    email = subprocess.run("git config user.email", shell=True, capture_output=True, text=True).stdout.strip()

    if not name or not email:
        print("GIT identity not set. GIT requires a name and email to commit changes.")
        print("This is not used for GitHub API interactions, just for local commit metadata. You can use any name/email you like.")
        print("However, it must match the format of a valid name/email to match the profile picture on GitHub and avoid commit errors.")
        # You can hardcode your info here for the hackathon to save time
        new_name = input("Enter your GitHub Name: ").strip()
        new_email = input("Enter your GitHub Email: ").strip()
        
        subprocess.run(f'git config user.name "{new_name}"', shell=True)
        subprocess.run(f'git config user.email "{new_email}"', shell=True)
        print(f"Identity set to {new_name} <{new_email}>")

def ensure_git_installed():
    """Checks for Git and installs it silently if missing."""
    # We send output to DEVNULL to keep the terminal clean
    try:
        subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return # Git exists, exit quietly
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Git not found! Starting installation...")
        
        # --- WINDOWS ---
        if os.name == 'nt': 
            try:
                subprocess.run(["winget", "install", "--id", "Git.Git", "-e", "--accept-source-agreements", "--accept-package-agreements"], 
                               stdout=subprocess.DEVNULL, check=True)
                print("Git installed! Please restart your terminal.")
            except:
                print("Winget failed. Install manually: https://git-scm.com/")

        # --- MACOS ---
        elif sys.platform == "darwin":
            try:
                # First, check if Homebrew is there
                subprocess.run(["brew", "--version"], stdout=subprocess.DEVNULL, check=True)
                subprocess.run(["brew", "install", "git"], stdout=subprocess.DEVNULL, check=True)
                print("Git installed via Homebrew! Please restart your terminal.")
            except:
                # If no Brew, use the built-in XCode developer tools installer
                try:
                    print("Launching macOS developer tools installer...")
                    subprocess.run(["xcode-select", "--install"], check=True)
                except:
                    print("macOS install failed. Use: xcode-select --install")

        # --- LINUX ---
        else:
            try:
                subprocess.run(["sudo", "apt-get", "update", "-y"], stdout=subprocess.DEVNULL, check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y", "git"], stdout=subprocess.DEVNULL, check=True)
                print("Git installed via apt! Please restart your terminal.")
            except:
                print("Linux install failed. Use: sudo apt install git")
        
        print()
        sys.exit(0) # Exit after install so user can restart terminal

def generate_config():
    clear()
    # Get the URL and clean it up
    raw_url = input("Private Repo URL (e.g., github.com/user/repo): ").strip()
    # Remove protocol if user included it
    clean_url = raw_url.replace("https://", "").replace("http://", "").replace(".git", "")
    
    # Extract Owner and Repo Name for the GitHub API Issue logic
    # Logic: github.com/owner/repo -> ['github.com', 'owner', 'repo']
    url_parts = clean_url.split('/')
    if len(url_parts) >= 3:
        repo_owner = url_parts[1]
        repo_name = url_parts[2]
    else:
        # Fallback if they just typed 'user/repo'
        repo_owner = url_parts[0]
        repo_name = url_parts[1]

    print("\nNOTE:")
    print("- config.txt is ignored by git")
    print("- Token is stored locally for GitHub integration")
    token = input("GitHub Personal Access Token: ").strip()
    
    print("\nRole Selection:")
    print("[1] Raspberry Pi Node (Production - Tracks 'stable')")
    print("[2] Developer Laptop (Workspace - Tracks 'dev')")
    role_choice = input("Select [1/2]: ")
    
    branch = "stable" if role_choice == "1" else "dev"
    is_node = "True" if role_choice == "1" else "False"
    
    # Save config with the new required keys
    with open("config.txt", "w") as f:
        f.write(f"GITHUB_TOKEN={token}\n") # Required for API calls
        f.write(f"REPO_URL=https://{token}@github.com/{repo_owner}/{repo_name}\n")
        f.write(f"REPO_OWNER={repo_owner}\n") # FIXED: Added this
        f.write(f"REPO_NAME={repo_name}\n")   # FIXED: Added this
        f.write(f"BRANCH={branch}\n")
        f.write(f"IS_NODE={is_node}\n")
        f.write(f"OS={platform.system()}\n")
    
    secure_config_file("config.txt")

    print(f"\nconfig.txt generated for {repo_owner}/{repo_name}")
    print(f"Tracking '{branch}' branch. Node Mode: {is_node}")

def bootstrap_watcher():
    print("\nSetup complete. Bootstrapping Watcher...")
    
    watcher_script = "watcher.py"
    
    if os.path.exists(watcher_script):
        # Use Popen to start the watcher in a separate process
        # so setup.py can finish and close cleanly.
        if os.name == 'nt':
            # Windows: Opens a new terminal window for the watcher
            subprocess.Popen(["start", "cmd", "/k", sys.executable, watcher_script], shell=True)
        else:
            # Linux/Mac: Runs in background
            subprocess.Popen([sys.executable, watcher_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"Watcher is now running in the background.")
    else:
        print(f"Error: {watcher_script} not found. Launch manually.")

if __name__ == "__main__":
    ensure_git_installed()
    check_git_identity()
    generate_config()
    bootstrap_watcher()
