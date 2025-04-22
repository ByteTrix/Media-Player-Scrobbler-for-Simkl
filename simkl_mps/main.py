"""
Main application module for the Simkl Scrobbler.

Sets up logging, defines the main application class (SimklScrobbler),
handles initialization, monitoring loop, and graceful shutdown.
"""
import time
import sys
import signal
import threading
import pathlib
import logging
from .monitor import Monitor
from .simkl_api import search_movie, get_movie_details, is_internet_connected
from .credentials import get_credentials

# --- Constants ---
APP_NAME = "simkl-mps"
USER_SUBDIR = "kavinthangavel" # User-specific subdirectory

# --- Path Setup ---
try:
    APP_DATA_DIR = pathlib.Path.home() / USER_SUBDIR / APP_NAME
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"CRITICAL: Failed to create application data directory: {e}", file=sys.stderr)
    # Fallback or exit depending on severity - exiting for now
    sys.exit(1)

# --- Logging Setup ---
log_file_path = APP_DATA_DIR / "simkl_mps.log"

# Console Handler (Warnings and above)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_formatter = logging.Formatter('%(levelname)s: %(message)s') # Simpler format for console
stream_handler.setFormatter(stream_formatter)

# File Handler (Info and above)
try:
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8') # Append mode
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)-8s] %(name)s: %(message)s')
    file_handler.setFormatter(file_formatter)
except Exception as e:
    print(f"CRITICAL: Failed to configure file logging: {e}", file=sys.stderr)
    file_handler = None # Disable file logging if setup fails

# Configure Root Logger
logging.basicConfig(
    level=logging.INFO, # Capture INFO level and above
    handlers=[h for h in [stream_handler, file_handler] if h] # Add handlers if they exist
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

    Exits the application with a critical error if essential credentials
    (Client ID, Client Secret, Access Token) are missing.

    Returns:
        tuple[str, str]: A tuple containing the client_id and access_token.
    """
    logger.info("Loading application configuration...")
    creds = get_credentials()
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    access_token = creds.get("access_token")

    # Validate essential credentials
    if not client_id:
        logger.critical("Configuration Error: Client ID not found. This might indicate a build issue.")
        print("CRITICAL ERROR: Application Client ID is missing. Please check the installation or build process.", file=sys.stderr)
        sys.exit(1)
    if not client_secret:
        logger.critical("Configuration Error: Client Secret not found. This might indicate a build issue.")
        print("CRITICAL ERROR: Application Client Secret is missing. Please check the installation or build process.", file=sys.stderr)
        sys.exit(1)
    if not access_token:
        logger.critical("Configuration Error: Access Token not found. Please run initialization.")
        print("ERROR: Access Token is missing. Please run 'simkl-mps init' to authenticate.", file=sys.stderr)
        sys.exit(1)

    logger.info("Application configuration loaded successfully.")
    return client_id, access_token

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
        logger.info("Initializing Simkl Scrobbler core components...")
        try:
            self.client_id, self.access_token = load_configuration()
        except SystemExit: # Catch exit from load_configuration
             logger.error("Initialization failed due to configuration errors.")
             return False
        except Exception as e:
            logger.exception(f"Unexpected error during configuration loading: {e}")
            return False

        # Pass credentials to the monitor instance
        self.monitor.set_credentials(self.client_id, self.access_token)
        logger.debug("Credentials set for monitor.")

        # Process any pending items from previous runs
        logger.info("Processing scrobble backlog...")
        try:
            backlog_count = self.monitor.scrobbler.process_backlog()
            if backlog_count > 0:
                logger.info(f"Successfully processed {backlog_count} items from the backlog.")
        except Exception as e:
             logger.error(f"Error processing backlog during initialization: {e}", exc_info=True)
             # Continue initialization even if backlog processing fails

        logger.info("Simkl Scrobbler initialization complete.")
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

        # Setup signal handling only in the main thread
        if threading.current_thread() is threading.main_thread():
            logger.debug("Setting up signal handlers (SIGINT, SIGTERM).")
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        else:
             logger.warning("Not running in main thread, skipping signal handler setup.")

        # Provide the callback for movie identification
        self.monitor.set_search_callback(self._search_and_cache_movie)

        # Start the monitor thread
        if not self.monitor.start():
             logger.error("Failed to start the monitor thread.")
             self.running = False # Reset running state
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
        self.monitor.stop() # Signal the monitor thread to stop
        logger.info("Scrobbler shutdown complete.")

    def _signal_handler(self, sig, frame):
        """Handles termination signals (SIGINT, SIGTERM) for graceful shutdown."""
        logger.warning(f"Received signal {signal.Signals(sig).name}. Initiating graceful shutdown...")
        self.stop()
        # Optionally force exit if shutdown hangs, though monitor should handle it
        # sys.exit(0)

    def _search_and_cache_movie(self, title):
        """
        Callback function provided to the Monitor for movie identification.

        Searches Simkl for the movie title, retrieves details (like runtime),
        and caches the information via the Monitor.

        Args:
            title (str): The movie title extracted by the monitor.
        """
        if not title:
            logger.warning("Monitor Callback: Received empty title for search.")
            return
        # Ensure credentials are still valid (might not be necessary if init succeeded)
        if not self.client_id or not self.access_token:
             logger.error(f"Monitor Callback: Missing credentials when searching for '{title}'.")
             return

        logger.info(f"Monitor Callback: Searching Simkl for title: '{title}'")

        if not is_internet_connected():
            logger.warning(f"Monitor Callback: Cannot search for '{title}', no internet connection.")
            # Let the monitor/scrobbler handle potential backlog addition
            return

        try:
            # Perform the primary search
            movie = search_movie(title, self.client_id, self.access_token)
            if not movie:
                logger.warning(f"Monitor Callback: No Simkl match found for '{title}'.")
                # Potentially cache a negative result or let scrobbler handle unknown
                return

            # Extract key information
            simkl_id = None
            movie_name = title # Default to original title
            runtime = None

            ids_dict = movie.get('ids') or movie.get('movie', {}).get('ids')
            if ids_dict:
                simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')

            if simkl_id:
                 # Use title from Simkl if available
                 movie_name = movie.get('title') or movie.get('movie', {}).get('title', title)
                 logger.info(f"Monitor Callback: Found Simkl ID {simkl_id} for '{movie_name}'. Fetching details...")

                 # Get additional details like runtime
                 try:
                     details = get_movie_details(simkl_id, self.client_id, self.access_token)
                     if details and 'runtime' in details:
                         runtime = details.get('runtime') # Use .get for safety
                         if runtime:
                             logger.info(f"Monitor Callback: Retrieved runtime: {runtime} minutes for ID {simkl_id}.")
                         else:
                              logger.warning(f"Monitor Callback: Runtime is present but empty/zero for ID {simkl_id}.")
                     else:
                          logger.warning(f"Monitor Callback: Could not retrieve runtime details for ID {simkl_id}.")
                 except Exception as detail_error:
                     logger.error(f"Monitor Callback: Error fetching details for ID {simkl_id}: {detail_error}", exc_info=True)

                 # Cache the gathered information via the monitor
                 self.monitor.cache_movie_info(title, simkl_id, movie_name, runtime)
                 logger.info(f"Monitor Callback: Cached info for '{title}' -> '{movie_name}' (ID: {simkl_id}, Runtime: {runtime})")
            else:
                logger.warning(f"Monitor Callback: No Simkl ID could be extracted for '{title}'.")
        except Exception as e:
            logger.exception(f"Monitor Callback: Unexpected error during search/cache for '{title}': {e}")

def run_as_background_service():
    """
    Runs the Simkl Scrobbler as a background service.
    
    Similar to main() but designed for daemon/service operation without
    keeping the main thread active with a sleep loop.
    
    Returns:
        SimklScrobbler: The running scrobbler instance for the service manager to control.
    """
    logger.info("Starting Simkl Scrobbler as a background service.")
    scrobbler_instance = SimklScrobbler()
    
    if not scrobbler_instance.initialize():
        logger.critical("Background service initialization failed.")
        return None
        
    if not scrobbler_instance.start():
        logger.critical("Failed to start the scrobbler monitor thread in background mode.")
        return None
        
    logger.info("Simkl Scrobbler background service started successfully.")
    return scrobbler_instance

def main():
    """
    Main entry point for running the Simkl Scrobbler directly.

    Initializes and starts the scrobbler, keeping the main thread alive
    until interrupted (e.g., by Ctrl+C).
    """
    logger.info("Simkl Scrobbler application starting in foreground mode.")
    scrobbler_instance = SimklScrobbler()

    if not scrobbler_instance.initialize():
        logger.critical("Application initialization failed. Exiting.")
        sys.exit(1)

    if not scrobbler_instance.start():
        logger.critical("Failed to start the scrobbler monitor thread. Exiting.")
        sys.exit(1)

    logger.info("Application running. Press Ctrl+C to stop.")
    # Keep main thread alive while monitor runs in background
    while scrobbler_instance.running:
        try:
            time.sleep(1) # Keep CPU usage low, allow signal handling
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt detected in main loop. Initiating shutdown...")
            scrobbler_instance.stop()
            break # Exit loop after stop is called

    logger.info("Simkl Scrobbler application stopped.")
    sys.exit(0) # Explicitly exit with success code

if __name__ == "__main__":
    main()