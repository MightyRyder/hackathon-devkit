import subprocess
import os
import platform

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def nuke_repo():
    # 1. Identify the Target
    branch = "dev"
    if os.path.exists("config.txt"):
        with open("config.txt", "r") as f:
            for line in f:
                if "BRANCH=" in line:
                    branch = line.split("=")[1].strip()
    
    print(f"--- RECOVERY TOOL: Target Branch [origin/{branch}] ---")

    # 2. Show the "Casualty List"
    unstaged = run("git status --short").stdout.strip()
    untracked = run("git clean -nd").stdout.strip() # -n is a dry run

    if not unstaged and not untracked:
        print("Repo is already clean. No reset needed.")
        return

    print("\n[!] The following will be DELETED or OVERWRITTEN:")
    if unstaged: print(f"Unstaged/Modified:\n{unstaged}")
    if untracked: print(f"Untracked Files:\n{untracked}")

    # 3. Confirmation
    print("\n" + "!"*40)
    confirm = input("PROCEED WITH HARD RESET? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted. No changes made.")
        return

    # 4. The Rescue Operation
    print("\n[+] Creating emergency backup (git stash)...")
    run("git stash push -u -m 'Emergency backup before nuke'")

    print("[+] Cleaning repo...")
    run("git merge --abort")  # Use default behavior; fails silently if no merge
    run("git fetch origin")
    
    # The Hard Reset
    reset_res = run(f"git reset --hard origin/{branch}")
    
    # The Clean
    clean_res = run("git clean -fd")

    if reset_res.returncode == 0:
        print(f"[SUCCESS] Repo aligned with origin/{branch}.")
        print("Note: Your old changes are saved in 'git stash list' if you need them.")
    else:
        print(f"[FAILURE] Reset failed: {reset_res.stderr}")

    print("\nGood luck.")

if __name__ == "__main__":
    nuke_repo()