import os
import platform
import subprocess
import sys

def clear(): os.system('cls' if os.name == 'nt' else 'clear')

def get_role():
    print("\nRole Selection:")
    print("[1] Raspberry Pi Node (Production - Tracks 'stable')")
    print("[2] Developer (Workspace - Tracks 'dev')")
    
    choice = input("Choice [1/2]: ").strip()
    
    if choice in ["1", "2"]:
        return choice
    
    print("Invalid selection. Please enter '1' or '2'.")
    return get_role() # The recursive call

def secure_config_file(filepath):
    """Hardens file permissions based on OS."""
    try:
        if platform.system() != "Windows":
            os.chmod(filepath, 0o600)
        else:
            user = os.environ.get("USERNAME")
            subprocess.run(["icacls", filepath, "/inheritance:r"], capture_output=True)
            subprocess.run(["icacls", filepath, "/grant:r", f"{user}:(R,W)"], capture_output=True)
    except Exception as e:
        print(f"Warning: Could not harden {filepath}: {e}")

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

def ensure_zenity():
    """Checks for Zenity on Linux and installs it if missing."""
    if platform.system() == "Linux":
        print("Checking for Zenity (GUI Alerts)...")
        if subprocess.run(["which", "zenity"], capture_output=True).returncode != 0:
            print("Zenity not found. Attempting auto-install...")
            try:
                # Assuming Debian/Ubuntu/Raspberry Pi OS
                subprocess.run(["sudo", "apt-get", "update", "-y"], capture_output=True)
                subprocess.run(["sudo", "apt-get", "install", "zenity", "-y"], capture_output=True)
                print("Zenity installed successfully.")
            except Exception as e:
                print(f"Could not install Zenity: {e}. Falling back to terminal alerts.")
        else:
            print("Zenity is already installed.")

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
    
    role_choice = get_role()
    
    branch = "stable" if role_choice == "1" else "dev"
    is_node = "True" if role_choice == "1" else "False"
    
    # Create the config file for permission-based hardening
    with open("config.txt", "w") as f:
        pass

    secure_config_file("config.txt")

    # Save config with the new required keys
    with open("config.txt", "w") as f:
        f.write(f"GITHUB_TOKEN={token}\n") # Required for API calls
        f.write(f"REPO_URL=https://{token}@github.com/{repo_owner}/{repo_name}\n")
        f.write(f"REPO_OWNER={repo_owner}\n")
        f.write(f"REPO_NAME={repo_name}\n")
        f.write(f"BRANCH={branch}\n")
        f.write(f"IS_NODE={is_node}\n")
        f.write(f"OS={platform.system()}\n")

    print(f"\nconfig.txt generated for {repo_owner}/{repo_name}")
    print(f"Tracking '{branch}' branch. Node Mode: {is_node}")

def bootstrap_watcher():
    print("\nSetup complete. Bootstrapping Watcher...")
    
    watcher_script = "watcher.py"
    
    if os.path.exists(watcher_script):
        # Prepare the arguments: the first arg must be the executable path
        args = [sys.executable, watcher_script]
        
        if os.name == 'nt':
            # On Windows, os.execv doesn't behave exactly like Unix 'exec'. 
            # To truly "spawn and forget" without a trace, we use creationflags.
            import subprocess
            subprocess.Popen(
                [sys.executable, watcher_script],
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS
            )
            sys.exit()
        else:
            # Linux/Mac: Replace the current process with the watcher.
            # This code effectively stops here and 'becomes' the watcher_script.
            os.execv(sys.executable, args)
    else:
        print(f"Error: {watcher_script} not found. Launch manually.")

if __name__ == "__main__":
    ensure_git_installed()
    ensure_zenity()
    check_git_identity()
    generate_config()
    bootstrap_watcher()