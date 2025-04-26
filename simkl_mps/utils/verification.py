"""
Verification module for Simkl MPS.

This module provides utilities for verifying that the application
was built from source via GitHub Actions.
"""

import sys
import os
import json
import time
import logging
import platform
import hashlib
from pathlib import Path

# Import platform-specific dependencies
PLATFORM = platform.system().lower()
if PLATFORM == 'windows':
    try:
        import win32api
    except ImportError:
        pass

logger = logging.getLogger(__name__)

# Default build metadata (used if build_info.json is not found)
BUILD_METADATA = {
    "version": "2.0.0", 
    "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    "git_commit": "local",
    "github_workflow": "local",
    "github_run_id": "local"
}

# Try to load build metadata from file
if getattr(sys, 'frozen', False):
    # Running from frozen/bundled app
    app_dir = Path(sys.executable).parent
    build_info_path = app_dir / "build_info.json"
    
    try:
        if build_info_path.exists():
            try:
                with open(build_info_path, 'r') as f:
                    BUILD_METADATA.update(json.load(f))
                logger.info(f"Loaded build information from {build_info_path}")
            except Exception as e:
                logger.error(f"Error loading build info: {e}")
    except Exception as e:
        logger.error(f"Error checking for build info: {e}")

def get_verification_info():
    """Get formatted verification information for display."""
    return {
        "Application Version": BUILD_METADATA["version"],
        "Build Time": BUILD_METADATA["build_time"],
        "Git Commit": BUILD_METADATA["git_commit"],
        "GitHub Workflow": BUILD_METADATA["github_workflow"],
        "GitHub Run ID": BUILD_METADATA["github_run_id"],
        "GitHub Run URL": f"https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/actions/runs/{BUILD_METADATA['github_run_id']}" 
        if BUILD_METADATA["github_run_id"] != "local" else "Local Build"
    }

def calculate_checksum(filepath):
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating checksum: {e}")
        return "Error calculating checksum"

def get_executable_checksum():
    """Get the SHA256 checksum of the current executable."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_path = Path(sys.executable)
        return calculate_checksum(exe_path)
    else:
        # Running in development mode
        return "Development build - no executable to checksum"