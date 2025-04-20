"""
Test script to launch the Simkl Movie Tracker along with VLC player.
This runs both the tracker and VLC to test the integration.
"""

import os
import subprocess
import sys
import time
import logging
import threading

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
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

def launch_simkl_tracker():
    """Launch the Simkl Movie Tracker with detailed logging."""
    logger.info("Launching Simkl Movie Tracker...")
    
    # Set environment variables to enable detailed logging
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"  # Force unbuffered output
    
    try:
        # Launch the tracker in a separate process
        tracker_process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )
        
        # Start a thread to read and log the output from the tracker process
        def log_output():
            for line in tracker_process.stdout:
                logger.info(f"TRACKER: {line.strip()}")
        
        log_thread = threading.Thread(target=log_output, daemon=True)
        log_thread.start()
        
        logger.info(f"Simkl Tracker launched with PID: {tracker_process.pid}")
        return tracker_process
    except Exception as e:
        logger.error(f"Failed to launch Simkl Tracker: {e}")
        return None

def main():
    # File path to play
    file_path = r"C:\Users\kavin\Downloads\jilla 2014.mp4"
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return
    
    # Launch the Simkl Tracker first
    tracker_process = launch_simkl_tracker()
    if not tracker_process:
        logger.error("Failed to launch Simkl Tracker. Aborting test.")
        return
    
    # Wait a bit for the tracker to initialize
    logger.info("Waiting for Simkl Tracker to initialize...")
    time.sleep(3)
    
    # Enable the HTTP interface with no password for easy connection
    vlc_process = launch_vlc_with_file(
        file_path=file_path,
        enable_http=True,
        http_port=8080,
        http_password=""  # Empty password for easy testing
    )
    
    if vlc_process:
        logger.info(f"VLC is playing: {file_path}")
        logger.info("Press Ctrl+C to exit this script (VLC and tracker will be terminated)")
        
        try:
            # Keep the script running to watch logs
            while True:
                # Check if VLC is still running
                if vlc_process.poll() is not None:
                    logger.info("VLC has exited")
                    break
                
                # Check if tracker is still running
                if tracker_process.poll() is not None:
                    logger.info("Simkl Tracker has exited")
                    break
                
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Test script terminated by user")
        finally:
            # Clean up processes
            if vlc_process.poll() is None:
                vlc_process.terminate()
                logger.info("VLC terminated")
            
            if tracker_process.poll() is None:
                tracker_process.terminate()
                logger.info("Simkl Tracker terminated")
    else:
        logger.error("Failed to launch VLC")
        # Terminate tracker if VLC failed to launch
        tracker_process.terminate()
        logger.info("Simkl Tracker terminated due to VLC launch failure")

if __name__ == "__main__":
    main()