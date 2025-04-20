import time
import os
import sys
import signal
import threading
import pathlib  # Import pathlib
import hashlib # Add hashlib import
from dotenv import load_dotenv
from .monitor import Monitor # Import Monitor instead of MonitorAwareScrobbler
from .window_detection import get_active_window_info # Import directly
from .simkl_api import search_movie, mark_as_watched, authenticate, get_movie_details, is_internet_connected, DEFAULT_CLIENT_ID
import logging

# Define the application data directory in the user's home folder
APP_NAME = "simkl-scrobbler"
USER_SUBDIR = "kavinthangavel" # As requested by the user
APP_DATA_DIR = pathlib.Path.home() / USER_SUBDIR / APP_NAME
APP_DATA_DIR.mkdir(parents=True, exist_ok=True) # Ensure the directory exists

# Configure logging when the module is loaded
log_file_path = APP_DATA_DIR / "simkl_scrobbler.log"

# Create handlers
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING) # Only show WARNING and above in terminal
stream_handler.setFormatter(logging.Formatter('%(levelname)s - %(name)s - %(message)s')) # Simpler format for terminal

file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO) # Log INFO and above to file
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))

# Configure the root logger
logging.basicConfig(
    level=logging.INFO, # Root logger level captures INFO and above
    handlers=[
        stream_handler, # Add configured stream handler
        file_handler    # Add configured file handler
    ]
)

# Create module-level logger
logger = logging.getLogger(__name__)

logger.info(f"Main application log file configured at: {log_file_path}") # Logged to file only
logger.info(f"Using application data directory: {APP_DATA_DIR}") # Logged to file only

# Default polling interval in seconds (Monitor uses its own default, but keep for reference if needed elsewhere)
# DEFAULT_POLL_INTERVAL = 10

def load_configuration():
    """Load client ID and access token from environment variables or .env file"""
    # Create .env file path in app data directory
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
    
    # Check if .env file exists
    if (env_path.exists()):
        # Load environment variables from .env file
        load_dotenv(env_path)
    
    # Get client ID and access token from environment variables
    client_id = os.getenv("SIMKL_CLIENT_ID")
    access_token = os.getenv("SIMKL_ACCESS_TOKEN")
    
    if not client_id:
        logger.error("Client ID not found. Using default client ID.")
        client_id = DEFAULT_CLIENT_ID

    if not client_id:
        # This case should ideally not happen if DEFAULT_CLIENT_ID is set
        logger.error("Client ID not found even after checking default. Exiting.")
        print("Critical Error: Client ID is missing. Please check installation.")
        sys.exit(1)

    if not access_token:
        logger.info("Access token not found, attempting device authentication...")
        print("Access token not found, attempting device authentication...")
        print("You'll need to authenticate with your Simkl account.")
        access_token = authenticate(client_id)
        if access_token:
            logger.info("Authentication successful.")
            print("Authentication successful. You should run 'simkl-scrobbler init' to save this token.")
            print(f"SIMKL_ACCESS_TOKEN={access_token}")
            # Note: We don't save it here automatically, init command handles saving.
        else:
            logger.error("Authentication failed.")
            print("Authentication failed. Please check your internet connection and ensure you complete the authorization step on Simkl.")
            sys.exit(1)

    return client_id, access_token

class SimklScrobbler:
    """Main application class that coordinates monitoring and Simkl interaction"""

    def __init__(self):
        self.running = False
        self.client_id = None
        self.access_token = None
        # Instantiate the Monitor, passing the app data directory
        self.monitor = Monitor(app_data_dir=APP_DATA_DIR)

    def initialize(self):
        """Initialize the monitor and authenticate with Simkl"""
        # Check for credentials in the correct file
        env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
        
        if env_path.exists():
            load_dotenv(env_path)
            self.client_id = os.getenv("SIMKL_CLIENT_ID")
            self.access_token = os.getenv("SIMKL_ACCESS_TOKEN")
        
        logger.info("Initializing Simkl Scrobbler...")

        self.client_id, self.access_token = load_configuration()

        if not self.client_id or not self.access_token:
            logger.error("Exiting due to configuration/authentication issues.")
            return False

        # Set credentials for the monitor (which passes them to its internal scrobbler)
        self.monitor.set_credentials(self.client_id, self.access_token)

        # Process backlog on startup via monitor's internal scrobbler
        try:
            backlog_count = self.monitor.scrobbler.process_backlog()
            if backlog_count > 0:
                logger.info(f"Processed {backlog_count} items from backlog during startup")
        except Exception as e:
             logger.error(f"Error processing backlog during initialization: {e}", exc_info=True)
             # Decide if this is critical enough to stop initialization

        return True

    def start(self):
        """Start the monitor main loop"""
        if not self.running:
            self.running = True
            logger.info("Starting Simkl Scrobbler...")
            logger.info("Monitoring for supported video players...")
            logger.info("Supported players: VLC, MPC-HC, Windows Media Player, MPV, etc.")
            logger.info("Movies will be marked as watched after viewing 80% of their estimated duration")

            # Only set up signal handlers when running in the main thread
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)

            # Set the search callback for the monitor
            # The monitor will call this when a movie needs identification
            self.monitor.set_search_callback(self._search_and_cache_movie)

            # Start the monitor (runs in its own thread)
            if not self.monitor.start():
                 logger.error("Failed to start the monitor.")
                 self.running = False # Ensure running state is correct
                 return False

            logger.info("Monitor thread started.")
            return True
        else:
            logger.warning("Scrobbler already running.")
            return False


    def stop(self):
        """Stop the monitor"""
        if self.running:
            logger.info("Stopping Monitor...")
            self.running = False
            self.monitor.stop() # Use monitor's stop method
            logger.info("Monitor stopped.")
        else:
             logger.info("Scrobbler was not running.")


    def _signal_handler(self, sig, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        self.stop()

    # Removed _backlog_check_loop - Monitor handles this internally

    # Removed _handle_scrobble_update - Replaced by _search_and_cache_movie callback

    def _search_and_cache_movie(self, title):
        """
        Callback function passed to the Monitor.
        Searches for a movie using the Simkl API and caches the result
        via the monitor's cache_movie_info method.
        """
        if not title:
            logger.warning("Search callback called without title.")
            return
        if not self.client_id or not self.access_token:
             logger.warning(f"Search callback for '{title}' called without credentials.")
             return

        logger.info(f"Search callback triggered for title: {title}")

        # Check internet connection
        if not is_internet_connected():
            logger.warning(f"Cannot search for '{title}' - no internet connection.")
            # MovieScrobbler should handle adding to backlog if needed based on progress
            return

        try:
            # Search for the movie
            movie = search_movie(title, self.client_id, self.access_token)

            if not movie:
                logger.warning(f"No Simkl match found for '{title}' via search callback.")
                # Cache a negative result? Or let MovieScrobbler handle unknown titles?
                # Let MovieScrobbler decide based on its logic.
                return

            # Extract movie details (simplified extraction)
            simkl_id = None
            movie_name = title
            runtime = None

            # Try extracting ID and Title
            ids_dict = movie.get('ids') or movie.get('movie', {}).get('ids')
            if ids_dict:
                simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')

            if simkl_id:
                 movie_name = movie.get('title') or movie.get('movie', {}).get('title', title)
                 logger.info(f"Found Simkl ID: {simkl_id} for '{movie_name}'")

                 # Get runtime details
                 try:
                     details = get_movie_details(simkl_id, self.client_id, self.access_token)
                     if details and 'runtime' in details:
                         runtime = details['runtime']
                         logger.info(f"Retrieved runtime: {runtime} minutes")
                 except Exception as detail_error:
                     logger.error(f"Error getting movie details for ID {simkl_id}: {detail_error}")

                 # Cache the result using the monitor's method
                 self.monitor.cache_movie_info(title, simkl_id, movie_name, runtime)
                 logger.info(f"Cached info for '{title}' -> '{movie_name}' (ID: {simkl_id}, Runtime: {runtime})")

            else:
                logger.warning(f"No Simkl ID found in search result for '{title}' via callback.")

        except Exception as e:
            logger.error(f"Error during search callback for '{title}': {e}", exc_info=True)

def run_as_background_service():
    """Run the scrobbler as a background service (conceptual)"""
    # Note: Actual service implementation requires more platform-specific code (like pywin32)
    # This function provides the core logic start.
    scrobbler_instance = SimklScrobbler()
    if scrobbler_instance.initialize():
        if scrobbler_instance.start():
            logger.info("Scrobbler service started successfully.")
            # In a real service, we'd need to keep the service alive here.
            # Returning the instance might be useful for management.
            return scrobbler_instance
        else:
             logger.error("Failed to start scrobbler monitor in service context.")
             return None
    else:
        logger.error("Failed to initialize scrobbler in service context.")
        return None


def main():
    """Main entry point for the application when run directly"""
    logger.info("Starting Simkl Scrobbler application")
    scrobbler_instance = SimklScrobbler()
    if scrobbler_instance.initialize():
        if scrobbler_instance.start(): # Start the monitor
            # Keep the main thread alive so the daemon monitor thread doesn't exit immediately
            while scrobbler_instance.running: # Check the running flag
                try:
                    # Sleep allows signal handling and keeps CPU usage low
                    time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("KeyboardInterrupt received in main, stopping...")
                    scrobbler_instance.stop()
                    break # Exit the loop cleanly
            logger.info("Main thread exiting.")
        else:
             logger.error("Failed to start the scrobbler monitor.")
             sys.exit(1)
    else:
        logger.error("Failed to initialize the scrobbler.")
        sys.exit(1)

if __name__ == "__main__":
    main()