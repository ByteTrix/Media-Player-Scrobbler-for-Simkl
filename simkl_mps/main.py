"""
Main application module for the Media Player Scrobbler for SIMKL.

Sets up logging, defines the main application class (SimklScrobbler),
handles initialization, monitoring loop, and graceful shutdown.
"""
import time
import sys
import signal
import threading
import pathlib
import logging
from simkl_mps.monitor import Monitor
from simkl_mps.credentials import get_credentials
from simkl_mps.config_manager import get_app_data_dir, initialize_paths, get_setting, APP_NAME
from simkl_mps.watch_history_manager import WatchHistoryManager # Added import

# Import platform-specific tray implementation
# Only import get_tray_app, do not import TrayApp or run_tray_app directly

def get_tray_app():
    """Get the correct tray app implementation and runner based on platform"""
    if sys.platform == 'win32':
        from simkl_mps.tray_win import TrayAppWin as TrayApp, run_tray_app
    elif sys.platform == 'darwin':
        from simkl_mps.tray_mac import TrayAppMac as TrayApp, run_tray_app
    else:  # Linux and other platforms
        from simkl_mps.tray_linux import TrayAppLinux as TrayApp, run_tray_app
    return TrayApp, run_tray_app

class ConfigurationError(Exception):
    """Custom exception for configuration loading errors."""
    pass

# Use the configuration manager to get our app data directory
APP_DATA_DIR = get_app_data_dir()

try:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"CRITICAL: Failed to create application data directory: {e}", file=sys.stderr)
    sys.exit(1)

log_file_path = APP_DATA_DIR / "simkl_mps.log"

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_formatter = logging.Formatter('%(levelname)s: %(message)s')
stream_handler.setFormatter(stream_formatter)

try:
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)-8s] %(name)s: %(message)s')
    file_handler.setFormatter(file_formatter)
except Exception as e:
    print(f"CRITICAL: Failed to configure file logging: {e}", file=sys.stderr)
    file_handler = None

logging.basicConfig(
    level=logging.INFO,
    handlers=[h for h in [stream_handler, file_handler] if h]
)

logger = logging.getLogger(__name__)
logger.info("="*20 + " Application Start " + "="*20)
logger.info(f"Using Application Data Directory: {APP_DATA_DIR}")
logger.info(f"User subdirectory: {get_setting('user_subdir')}")
if file_handler:
    logger.info(f"Logging to file: {log_file_path}")
else:
    logger.warning("File logging is disabled due to setup error.")


def load_configuration():
    """
    Loads necessary credentials using the credentials module.

    Raises:
        ConfigurationError: If essential credentials (Client ID, Client Secret, Access Token) are missing.

    Returns:
        dict: The credentials dictionary containing 'client_id', 'client_secret', 'access_token', etc.
    """
    logger.info("Loading application configuration...")
    creds = get_credentials()
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    access_token = creds.get("access_token")

    if not client_id:
        msg = "Client ID not found. Check installation/build or dev environment."
        logger.critical(f"Configuration Error: {msg}")
        raise ConfigurationError(msg)
    if not client_secret:
        msg = "Client Secret not found. Check installation/build or dev environment."
        logger.critical(f"Configuration Error: {msg}")
        raise ConfigurationError(msg)
    if not access_token:
        msg = "Access Token not found. Please run 'simkl-mps init' to authenticate."
        logger.critical(f"Configuration Error: {msg}")
        raise ConfigurationError(msg)

    logger.info("Application configuration loaded successfully.")
    return creds # Return the whole dictionary

class SimklScrobbler:
    """
    Main application class orchestrating media monitoring and Simkl scrobbling.
    """
    def __init__(self):
        """Initializes the SimklScrobbler instance."""
        self.running = False
        self.client_id = None
        self.access_token = None
        self.monitor = Monitor(app_data_dir=APP_DATA_DIR)
        self.watch_history_manager = None # Added instance variable
        logger.debug("SimklScrobbler instance created.")

    def initialize(self):
        """
        Initializes the scrobbler by loading configuration and processing backlog.

        Returns:
            bool: True if initialization is successful, False otherwise.
        """
        logger.info("Initializing Media Player Scrobbler for SIMKL core components...")
        try:
            # Load configuration - raises ConfigurationError on failure
            creds = load_configuration()
            self.client_id = creds.get("client_id")
            self.access_token = creds.get("access_token")

        except ConfigurationError as e:
             logger.error(f"Initialization failed: {e}")
             # Print user-friendly message based on the specific error
             print(f"ERROR: {e}", file=sys.stderr)
             return False
        except Exception as e:
            # Catch any other unexpected errors during loading
            logger.exception(f"Unexpected error during configuration loading: {e}")
            print(f"CRITICAL ERROR: An unexpected error occurred during initialization. Check logs.", file=sys.stderr)
            return False

        # Set credentials in the monitor using the loaded values
        self.monitor.set_credentials(self.client_id, self.access_token)

        # Initialize Watch History Manager early
        try:
            self.watch_history_manager = WatchHistoryManager(APP_DATA_DIR)
            logger.info("Watch History Manager initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Watch History Manager: {e}", exc_info=True)
            # Non-critical for core scrobbling, log and continue

        logger.info("Media Player Scrobbler for SIMKL core initialization complete.")
        return True

    def start(self):
        """
        Starts the media monitoring process in a separate thread.

        Returns:
            bool: True if the monitor thread starts successfully, False otherwise.
        """
        if self.running:
            logger.warning("Attempted to start scrobbler monitor, but it is already running.")
            return False

        self.running = True
        logger.info("Starting media player monitor...")

        if threading.current_thread() is threading.main_thread():
            logger.debug("Setting up signal handlers (SIGINT, SIGTERM).")
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        else:
             logger.warning("Not running in main thread, skipping signal handler setup.")

        if not self.monitor.start():
             logger.error("Failed to start the monitor thread.")
             self.running = False
             return False

        logger.info("Media player monitor thread started successfully.")

        # Start background backlog sync *after* monitor is running
        logger.info("Starting background backlog synchronization thread...")
        self.monitor.scrobbler.start_offline_sync_thread() # Use default interval

        return True

    def stop(self):
        """Stops the media monitoring thread gracefully."""
        if not self.running:
            logger.info("Stop command received, but scrobbler was not running.")
            return

        logger.info("Initiating scrobbler shutdown...")
        self.running = False
        self.monitor.stop()
        logger.info("Scrobbler shutdown complete.")

    def _signal_handler(self, sig, frame):
        """Handles termination signals (SIGINT, SIGTERM) for graceful shutdown."""
        logger.warning(f"Received signal {signal.Signals(sig).name}. Initiating graceful shutdown...")
        self.stop()

def run_as_background_service():
    """
    Runs the Media Player Scrobbler for SIMKL as a background service.
    
    Similar to main() but designed for daemon/service operation without
    keeping the main thread active with a sleep loop.
    
    Returns:
        SimklScrobbler: The running scrobbler instance for the service manager to control.
    """
    logger.info("Starting Media Player Scrobbler for SIMKL as a background service.")
    scrobbler_instance = SimklScrobbler()
    
    if not scrobbler_instance.initialize():
        logger.critical("Background service initialization failed.")
        return None
        
    if not scrobbler_instance.start():
        logger.critical("Failed to start the scrobbler monitor thread in background mode.")
        return None
        
    logger.info("simkl-mps background service started successfully.")
    return scrobbler_instance

def main():
    """
    Main entry point for running the Media Player Scrobbler for SIMKL directly.

    Initializes and starts the scrobbler, keeping the main thread alive
    until interrupted (e.g., by Ctrl+C).
    """
    logger.info("simkl-mps application starting in foreground mode.")
    scrobbler_instance = SimklScrobbler()

    if not scrobbler_instance.initialize():
        logger.critical("Application initialization failed. Exiting.")
        sys.exit(1)

    if not scrobbler_instance.start():
        logger.critical("Failed to start the scrobbler monitor thread. Exiting.")
        sys.exit(1)

    logger.info("Application running. Press Ctrl+C to stop.")
    
    while scrobbler_instance.running:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt detected in main loop. Initiating shutdown...")
            scrobbler_instance.stop()
            break

    logger.info("simkl-mps application stopped.")
    sys.exit(0)

if __name__ == "__main__":
    main()