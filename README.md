# hackathon devkit
Designed to enforce a workflow using the following scripts, specifically designed to be used with Debian Raspberry Pi backends

This is very user-friendly and supports private repos

This code has multiple safety guardrails to prevent overwriting others' code in high-speed hackathon environments

setup.py --> Generates `config.txt`, which is required for the other scripts to work. It also handles dependencies

# files

watcher.py --> Must be run in the background. It checks to make sure you're always up to date with the repo

push.py --> Easily allows you to push your changes to GitHub

reset.py --> Hard resets to match w/ the repo in case your local save is broken

frontend/backend --> Upon nodes redownloading the updated repo because of a commit to the stable branch, all the nodes will restart everything in their assigned folder into a seperate tmux session
