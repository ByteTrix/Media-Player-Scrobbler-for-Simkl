"""
Test script to launch VLC player with a specific movie file.
This can be used to test the VLC integration with the SIMKL movie tracker.
"""

import os
import subprocess
import sys
import time
import logging
import pathlib

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def find_vlc_path():
    """Find the VLC executable path based on the platform."""
    if sys.platform == 'win32':
        # Common locations on Windows
        vlc_paths = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
        # Check if VLC is in the PATH
        try:
            from shutil import which
            vlc_in_path = which("vlc")
            if vlc_in_path:
                return vlc_in_path
        except Exception as e:
            logger.warning(f"Error checking VLC in PATH: {e}")
        
        # Check common install locations
        for path in vlc_paths:
            if os.path.exists(path):
                return path
    
    elif sys.platform == 'darwin':
        # macOS
        return '/Applications/VLC.app/Contents/MacOS/VLC'
    
    else:
        # Linux
        return 'vlc'  # Assume in PATH
    
    # If we get here, we couldn't find VLC
    logger.warning("Could not find VLC executable. Defaulting to 'vlc' in PATH.")
    return 'vlc'  # Default to "vlc" and hope it's in the PATH

def launch_vlc_with_file(file_path, enable_http=True, http_port=8080, http_password=""):
    """
    Launch VLC with the specified file.
    
    Args:
        file_path: Path to the media file
        enable_http: Whether to enable HTTP interface
        http_port: Port for HTTP interface
        http_password: Password for HTTP interface
    """
    vlc_path = find_vlc_path()
    
    cmd = [vlc_path]
    
    # Enable HTTP interface for the SIMKL tracker to connect
    if enable_http:
        cmd.extend([
            "--extraintf=http",
            f"--http-port={http_port}"
        ])
        if http_password:
            cmd.append(f"--http-password={http_password}")
    
    # Add the file to play
    cmd.append(file_path)
    
    logger.info(f"Launching VLC with command: {' '.join(cmd)}")
    
    try:
        # Launch VLC in a subprocess
        process = subprocess.Popen(cmd)
        logger.info(f"VLC launched with PID: {process.pid}")
        return process
    except Exception as e:
        logger.error(f"Failed to launch VLC: {e}")
        return None

def main():
    # File path to play
    file_path = r"C:\Users\kavin\Downloads\jilla 2014.mp4"
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return
    
    # Enable the HTTP interface with no password for easy connection
    vlc_process = launch_vlc_with_file(
        file_path=file_path,
        enable_http=True,
        http_port=8080,
        http_password=""  # Empty password for easy testing
    )
    
    if vlc_process:
        logger.info(f"VLC is playing: {file_path}")
        logger.info("Press Ctrl+C to exit this script (VLC will continue running)")
        
        try:
            # Keep the script running to watch logs
            while True:
                # Check if VLC is still running
                if vlc_process.poll() is not None:
                    logger.info("VLC has exited")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Test script terminated by user")
    else:
        logger.error("Failed to launch VLC")

if __name__ == "__main__":
    main()