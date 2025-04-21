"""
Peogram to create tag and build release
"""

import subprocess
import sys
import toml

def get_version():
    data = toml.load("pyproject.toml")
    try:
        return data["tool"]["poetry"]["version"]
    except KeyError:
        print("Version not found in pyproject.toml")
        sys.exit(1)

def run(cmd):
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        sys.exit(result.returncode)

if __name__ == "__main__":
    version = get_version()
    tag = f"v{version}"
    commit_msg = f"enhancement: bump version to {tag}"

    print(f"Staging all changes...")
    run("git add .")

    print(f"Committing with message: '{commit_msg}'")
    run(f'git commit -m "{commit_msg}" || echo "Nothing to commit."')

    print(f"Pushing commit to origin...")
    run("git push origin HEAD")

    print(f"Tagging version: {tag}")
    run(f"git tag {tag}")

    print(f"Pushing tag {tag} to origin...")
    run(f"git push origin {tag}")

    print(f"Tag {tag} created and pushed to origin.")
