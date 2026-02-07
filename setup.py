import os
import platform
import subprocess
import sys

def clear(): os.system('cls' if os.name == 'nt' else 'clear')

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

    print(f"\n✅ config.txt generated for {repo_owner}/{repo_name}")
    print(f"Tracking '{branch}' branch. Node Mode: {is_node}")

if __name__ == "__main__":
    ensure_git_installed()
    generate_config()
