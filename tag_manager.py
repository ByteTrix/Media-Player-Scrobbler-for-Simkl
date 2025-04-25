#!/usr/bin/env python3
"""
Tag Manager for Media Player Scrobbler for SIMKL

This script helps create and verify GPG-signed Git tags for releases.
It ensures proper provenance for GitHub releases through verified tags.

Features:
- Creates GPG-signed tags for better security and verification
- Verifies tags to ensure they're properly signed
- Handles pushing tags to the remote repository
- Works across platforms (Windows, macOS, Linux)

Usage Examples:
  # Create a signed tag for the current version from pyproject.toml
  python tag_manager.py create
  
  # Create a signed tag with a custom message
  python tag_manager.py create -m "Release v2.0.3 with bug fixes"
  
  # Verify that a tag is properly signed
  python tag_manager.py verify v2.0.3
  
  # Force recreate an existing tag
  python tag_manager.py create --force
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

def get_current_version() -> str:
    """Get the current version from pyproject.toml"""
    try:
        # Import tomli only when needed
        try:
            import tomli
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "tomli"])
            import tomli
            
        pyproject_path = Path(__file__).parent / "pyproject.toml"
        
        with open(pyproject_path, "rb") as f:
            data = tomli.load(f)
        
        # Try both poetry and PEP 621 style
        if "tool" in data and "poetry" in data["tool"]:
            return data["tool"]["poetry"]["version"]
        elif "project" in data:
            return data["project"]["version"]
        else:
            print("Error: Version not found in pyproject.toml")
            sys.exit(1)
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}")
        sys.exit(1)

def run_command(cmd: str, exit_on_error: bool = True) -> Optional[str]:
    """Run a shell command with error handling"""
    try:
        print(f"Running: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        if exit_on_error:
            sys.exit(e.returncode)
        return None

def is_gpg_available() -> bool:
    """Check if GPG is available for signing tags"""
    try:
        result = subprocess.run(
            "git config --get user.signingkey",
            shell=True,
            check=False,
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False

def setup_gpg_on_windows() -> bool:
    """Set up GPG on Windows systems"""
    # Common GPG installation paths on Windows
    gpg_paths = [
        r"C:\Program Files\GnuPG\bin",
        r"C:\Program Files (x86)\GnuPG\bin",
        r"C:\Program Files\Git\usr\bin"
    ]
    
    for path in gpg_paths:
        gpg_exe = os.path.join(path, "gpg.exe")
        if os.path.exists(gpg_exe):
            # Add to PATH for this process
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + path
            
            # Configure Git to use this GPG
            try:
                subprocess.run(
                    f'git config --global gpg.program "{gpg_exe}"',
                    shell=True,
                    check=True,
                    capture_output=True,
                    text=True
                )
                return True
            except Exception:
                continue
    
    return False

def tag_exists(tag: str) -> Tuple[bool, bool]:
    """Check if a tag exists locally and remotely."""
    # Check if tag exists locally
    local_tag = subprocess.run(
        f"git tag -l {tag}",
        shell=True,
        capture_output=True,
        text=True
    )
    local_exists = bool(local_tag.stdout.strip())
    
    # Check if tag exists remotely
    remote_tag = subprocess.run(
        f"git ls-remote --tags origin {tag}",
        shell=True,
        capture_output=True,
        text=True
    )
    remote_exists = bool(remote_tag.stdout.strip())
    
    return local_exists, remote_exists

def delete_tag(tag: str) -> Tuple[bool, bool]:
    """Delete a tag locally and remotely."""
    local_success = True
    remote_success = True
    
    try:
        # Delete local tag
        subprocess.run(
            f"git tag -d {tag}",
            shell=True,
            check=True
        )
    except Exception as e:
        print(f"Error deleting local tag: {e}")
        local_success = False
    
    try:
        # Delete remote tag
        subprocess.run(
            f"git push origin :refs/tags/{tag}",
            shell=True,
            check=True
        )
    except Exception as e:
        print(f"Error deleting remote tag: {e}")
        remote_success = False
    
    return local_success, remote_success

def create_tag(args):
    """Create a GPG-signed Git tag"""
    # Get the version from pyproject.toml
    version = get_current_version()
    tag_name = f"v{version}"
    
    # Get the tag message
    if args.message:
        tag_message = args.message
    else:
        tag_message = f"Release version {version}"
    
    # Check if tag already exists
    local_tag_exists, remote_tag_exists = tag_exists(tag_name)
    if (local_tag_exists or remote_tag_exists) and not args.force:
        print(f"⚠️ Tag {tag_name} already exists. Use --force to recreate it.")
        return 1
    
    # Delete existing tag if force is set
    if (local_tag_exists or remote_tag_exists) and args.force:
        print(f"Deleting existing tag: {tag_name}")
        local_success, remote_success = delete_tag(tag_name)
        if not local_success or not remote_success:
            print(f"⚠️ Failed to delete existing tag {tag_name}")
            return 1
    
    # Check if GPG is available for signing
    can_sign = is_gpg_available()
    
    # On Windows, try to set up GPG if not available
    if not can_sign and os.name == 'nt':
        print("GPG signing not available. Attempting to configure GPG...")
        can_sign = setup_gpg_on_windows()
    
    if not can_sign:
        print("\n⚠️ GPG signing key not configured. Tags will not be verified on GitHub.")
        print("To set up GPG signing:")
        print("1. Create a GPG key: gpg --full-generate-key")
        print("2. Get your key ID: gpg --list-secret-keys --keyid-format=long")
        print("3. Configure Git: git config --global user.signingkey YOUR_KEY_ID")
        print("4. Add your GPG public key to GitHub")
        
        # Ask if user wants to continue with unsigned tag
        if not args.force:
            response = input("\nContinue with unsigned tag? (y/n): ")
            if response.lower() != 'y':
                print("Aborting tag creation.")
                return 1
    
    # Create the tag
    if can_sign:
        print(f"Creating signed tag {tag_name}...")
        run_command(f'git tag -s {tag_name} -m "{tag_message}"')
    else:
        print(f"Creating unsigned tag {tag_name}...")
        run_command(f'git tag -a {tag_name} -m "{tag_message}"')
    
    # Push the tag if requested
    if args.push:
        print(f"Pushing tag {tag_name} to remote...")
        run_command(f"git push origin {tag_name}")
    
    if can_sign:
        print(f"\n✅ Signed tag {tag_name} created successfully!")
        print("This signed tag will help GitHub display the 'Verified' badge on releases.")
    else:
        print(f"\n✅ Tag {tag_name} created successfully!")
        print("Note: This tag is not GPG-signed and won't show as verified on GitHub.")
    
    return 0

def verify_tag(args):
    """Verify a GPG signature on a Git tag"""
    tag_name = args.tag_name
    if not tag_name.startswith('v'):
        tag_name = f"v{tag_name}"
    
    # Check if the tag exists
    local_exists, _ = tag_exists(tag_name)
    if not local_exists:
        print(f"⚠️ Tag {tag_name} does not exist locally.")
        print(f"Attempting to fetch from remote...")
        run_command("git fetch --tags", exit_on_error=False)
        
        local_exists, _ = tag_exists(tag_name)
        if not local_exists:
            print(f"⚠️ Tag {tag_name} not found.")
            return 1
    
    # Verify the tag signature
    try:
        result = subprocess.run(
            f"git verify-tag {tag_name}",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"\n✅ Tag {tag_name} has a valid signature!")
            print(result.stderr)  # GPG outputs verification info to stderr
            return 0
        else:
            print(f"\n⚠️ Tag {tag_name} does not have a valid signature!")
            print(result.stderr)
            return 1
    except Exception as e:
        print(f"Error verifying tag: {e}")
        return 1

def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description="Create and verify GPG-signed Git tags",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a signed Git tag")
    create_parser.add_argument("-m", "--message", help="Custom tag message")
    create_parser.add_argument("--force", action="store_true", help="Force recreate existing tag")
    create_parser.add_argument("--push", action="store_true", help="Push tag to remote after creation")
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify a Git tag signature")
    verify_parser.add_argument("tag_name", help="Tag name to verify (with or without v prefix)")
    
    args = parser.parse_args()
    
    if args.command == "create":
        return create_tag(args)
    elif args.command == "verify":
        return verify_tag(args)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())