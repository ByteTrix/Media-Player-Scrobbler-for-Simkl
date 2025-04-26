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
from simkl_mps.simkl_api import search_movie, get_movie_details, is_internet_connected
from simkl_mps.credentials import get_credentials

# Import platform-specific tray implementation
def get_tray_app():
    """Get the correct tray app implementation based on platform"""
    if sys.platform == 'win32':
        from simkl_mps.tray_app import TrayApp, run_tray_app
    elif sys.platform == 'darwin':
        from simkl_mps.tray_mac import TrayApp, run_tray_app
    else:  # Linux and other platforms
        from simkl_mps.tray_linux import TrayApp, run_tray_app
    return TrayApp, run_tray_app

class ConfigurationError(Exception):
    """Custom exception for configuration loading errors."""
    pass

APP_NAME = "simkl-mps"
USER_SUBDIR = "kavinthangavel"

try:
    APP_DATA_DIR = pathlib.Path.home() / USER_SUBDIR / APP_NAME
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

        logger.info("Processing scrobble backlog...")
        try:
            backlog_count = self.monitor.scrobbler.process_backlog()
            if backlog_count > 0:
                logger.info(f"Successfully processed {backlog_count} items from the backlog.")
        except Exception as e:
             logger.error(f"Error processing backlog during initialization: {e}", exc_info=True)

        logger.info("Media Player Scrobbler for SIMKL initialization complete.")
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

        self.monitor.set_search_callback(self._search_and_cache_movie)

        if not self.monitor.start():
             logger.error("Failed to start the monitor thread.")
             self.running = False
             return False

        logger.info("Media player monitor thread started successfully.")
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

    def _search_and_cache_movie(self, title):
        """
        Callback function provided to the Monitor for movie identification.

        Searches Simkl for the movie title, retrieves details (like runtime),
        and caches the information via the Monitor's scrobbler.

        Args:
            title (str): The movie title extracted by the monitor.
        """
        if not title:
            logger.warning("Search Callback: Received empty title.")
            return
            
        # Check for generic titles that should be ignored
        if title.lower() in ["audio", "video", "media", "no file"]:
            return

        logger.info(f"Search Callback: Identifying title: '{title}'")

        if not is_internet_connected():
            # Logged within is_internet_connected if it fails multiple times
            logger.debug(f"Search Callback: Cannot search for '{title}', no internet connection.")
            return

        try:
            # Search for the movie using the API
            search_result = search_movie(title, self.client_id, self.access_token)
            if not search_result:
                logger.warning(f"Search Callback: No Simkl match found for '{title}'.")
                # Optionally cache the negative result to avoid repeated searches?
                # self.monitor.cache_movie_info(title, None, None, None) # Consider adding this
                return

            # Extract Simkl ID and official title
            simkl_id = None
            movie_name = title # Default to original title
            runtime_minutes = None

            # Handle different possible structures of the search result
            ids_dict = search_result.get('ids') or search_result.get('movie', {}).get('ids')
            if ids_dict:
                simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')

                if simkl_id:
                    # Use the title from the Simkl result if available
                    movie_name = search_result.get('title') or search_result.get('movie', {}).get('title', title)
                    logger.info(f"Search Callback: Found Simkl ID {simkl_id} for '{movie_name}'. Fetching details...")

                    # Fetch detailed information (including runtime)
                    try:
                        details = get_movie_details(simkl_id, self.client_id, self.access_token)
                        if details:
                            runtime_minutes = details.get('runtime')
                            if runtime_minutes:
                                logger.info(f"Search Callback: Retrieved runtime: {runtime_minutes} minutes for ID {simkl_id}.")
                            else:
                                logger.warning(f"Search Callback: Runtime missing or zero in details for ID {simkl_id}.")
                        else:
                            logger.warning(f"Search Callback: Could not retrieve details for ID {simkl_id}.")
                    except Exception as detail_error:
                        logger.error(f"Search Callback: Error fetching details for ID {simkl_id}: {detail_error}", exc_info=True)

                    # Cache the found information (original title -> simkl info)
                    self.monitor.cache_movie_info(title, simkl_id, movie_name, runtime_minutes)
                    logger.info(f"Search Callback: Cached info: '{title}' -> '{movie_name}' (ID: {simkl_id}, Runtime: {runtime_minutes})")
                else:
                    logger.warning(f"Search Callback: No Simkl ID could be extracted from search result for '{title}'.")
                    # Optionally cache negative result here too
                    # self.monitor.cache_movie_info(title, None, None, None)

        except Exception as e:
            # Catch unexpected errors during the API interaction or processing
            logger.exception(f"Search Callback: Unexpected error during search/cache for '{title}': {e}")

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