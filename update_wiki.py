#!/usr/bin/env python3
"""
Script to update wiki_temp files from docs and push changes to the repository.
This script:
1. Copies all markdown files from docs/ to wiki_temp/ with proper naming
2. Commits and pushes changes to the wiki repository
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime

# Configuration
DOCS_DIR = "docs"
WIKI_DIR = "wiki_temp"

# File mapping from docs/ to wiki_temp/
FILE_MAPPING = {
    "index.md": "Home.md",
    "configuration.md": "Configuration.md",
    "development.md": "Development.md",
    "installation.md": "Installation.md",
    "media-players.md": "Media-Players.md",
    "todo.md": "To-do.md",
    "troubleshooting.md": "Troubleshooting.md",
    "usage.md": "Usage.md",
}


def run_command(cmd, cwd=None):
    """Run a shell command and handle errors."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, 
                            capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error executing command: {cmd}")
        print(f"Output: {result.stdout}")
        print(f"Error: {result.stderr}")
        sys.exit(result.returncode)
    
    return result.stdout.strip()


def update_wiki_files():
    """Copy docs files to wiki_temp with appropriate names."""
    print("\n=== Updating Wiki Files ===")
    
    # Ensure both directories exist
    if not os.path.isdir(DOCS_DIR):
        print(f"Error: {DOCS_DIR} directory not found.")
        sys.exit(1)
    
    if not os.path.isdir(WIKI_DIR):
        print(f"Error: {WIKI_DIR} directory not found.")
        sys.exit(1)
    
    # Copy each file
    for source_file, target_file in FILE_MAPPING.items():
        source_path = os.path.join(DOCS_DIR, source_file)
        target_path = os.path.join(WIKI_DIR, target_file)
        
        if not os.path.exists(source_path):
            print(f"Warning: Source file {source_path} not found. Skipping.")
            continue
        
        shutil.copy2(source_path, target_path)
        print(f"Updated: {target_file}")


def push_wiki_changes():
    """Commit and push changes to the wiki repository."""
    print("\n=== Pushing Wiki Changes ===")
    
    # Check if there are changes to commit
    git_status = run_command("git status --porcelain", cwd=WIKI_DIR)
    
    if not git_status:
        print("No changes to commit.")
        return
    
    # Create commit message with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_message = f"docs: update wiki documentation ({timestamp})"
    
    # Add, commit and push changes
    run_command("git add .", cwd=WIKI_DIR)
    run_command(f'git commit -m "{commit_message}"', cwd=WIKI_DIR)
    run_command("git push", cwd=WIKI_DIR)
    
    print(f"Successfully pushed wiki changes with message: {commit_message}")


if __name__ == "__main__":
    print("=== Wiki Update Automation Tool ===")
    update_wiki_files()
    push_wiki_changes()
    print("\n=== Wiki Update Complete ===")