"""
Verification module for Simkl MPS.

This module provides utilities for verifying that the application
was built from source via GitHub Actions.
"""

import os
import json
import hashlib
import datetime
from pathlib import Path
import sys
import logging

logger = logging.getLogger(__name__)

# These values will be populated by the GitHub Actions workflow
BUILD_METADATA = {
    "version": "dev",
    "git_commit": "local",
    "build_time": datetime.datetime.now().isoformat(),
    "build_number": "local",
    "github_workflow": "local",
    "github_run_id": "local",
    "github_run_number": "local"
}

# Try to load build info from file if running in packaged mode
try:
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_dir = Path(sys.executable).parent
        build_info_path = exe_dir / "build_info.json"
        
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