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
from simkl_mps.simkl_api import search_movie, search_file, get_movie_details, is_internet_connected
from simkl_mps.credentials import get_credentials
from simkl_mps.config_manager import get_app_data_dir, initialize_paths, get_setting, APP_NAME
from simkl_mps.watch_history_manager import WatchHistoryManager # Added import

# Import platform-specific tray implementation
def get_tray_app():
    """Get the correct tray app implementation based on platform"""
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

        self.monitor.set_search_callback(self._search_and_cache_movie)

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

    def _search_and_cache_movie(self, title):
        """
        Callback function provided to the Monitor for media identification.

        Searches Simkl for the title, retrieves details, and caches the information
        via the Monitor's scrobbler. Works for movies, TV shows, and anime.

        Args:
            title (str): The media title extracted by the monitor.
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
            # Check if we have filepath information in the scrobbler
            filepath = self.monitor.scrobbler.current_filepath
            current_media_type = self.monitor.scrobbler.media_type
            
            # First attempt: If we have a filepath, try search_file API which works better for TV/anime
            if filepath:
                logger.info(f"Search Callback: Attempting file-based search for '{title}' using filepath: {filepath}")
                import os
                filename = os.path.basename(filepath)
                search_result = search_file(filepath, self.client_id)
                
                if search_result:
                    logger.info(f"Search Callback: File search returned: {search_result}")
                    # Process file search result
                    self._process_file_search_result(title, search_result, filepath)
                    return
                    
            # Fallback to movie search (can also return shows sometimes)
            search_result = search_movie(title, self.client_id, self.access_token)
            if not search_result:
                logger.warning(f"Search Callback: No Simkl match found for '{title}'.")
                return

            # Extract Simkl ID and official title
            simkl_id = None
            display_name = title # Default to original title
            runtime_minutes = None
            media_type = 'movie'  # Default type

            # Handle different possible structures of the search result
            if 'movie' in search_result:
                # Standard movie result
                ids_dict = search_result.get('movie', {}).get('ids')
                if ids_dict:
                    simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')
                    display_name = search_result.get('movie', {}).get('title', title)
                    media_type = 'movie'
            elif 'show' in search_result:
                # TV show result
                ids_dict = search_result.get('show', {}).get('ids')
                if ids_dict:
                    simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')
                    display_name = search_result.get('show', {}).get('title', title)
                    media_type = search_result.get('show', {}).get('type', 'show')
                    
                # Extract episode info if available
                season = None
                episode = None
                if 'episode' in search_result:
                    season = search_result['episode'].get('season')
                    episode = search_result['episode'].get('number')
            elif 'ids' in search_result:
                # Direct ID structure
                ids_dict = search_result.get('ids')
                if ids_dict:
                    simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')
                    display_name = search_result.get('title', title)
                    media_type = search_result.get('type', 'movie')

            if simkl_id:
                logger.info(f"Search Callback: Found Simkl ID {simkl_id} for '{display_name}' (Type: {media_type}).")
                
                # Fetch detailed information (including runtime) for movies
                if media_type == 'movie':
                    try:
                        details = get_movie_details(simkl_id, self.client_id, self.access_token)
                        if details:
                            runtime_minutes = details.get('runtime')
                            if runtime_minutes:
                                logger.info(f"Search Callback: Retrieved runtime: {runtime_minutes} minutes for movie ID {simkl_id}.")
                            else:
                                logger.warning(f"Search Callback: Runtime missing or zero in details for movie ID {simkl_id}.")
                        else:
                            logger.warning(f"Search Callback: Could not retrieve details for movie ID {simkl_id}.")
                    except Exception as detail_error:
                        logger.error(f"Search Callback: Error fetching details for movie ID {simkl_id}: {detail_error}", exc_info=True)

                # Cache the found information based on media type
                if media_type in ['show', 'anime'] and 'season' in locals() and 'episode' in locals() and season is not None and episode is not None:
                    # TV Show/Anime with episode information
                    self.monitor.cache_media_info(title, simkl_id, display_name, media_type, season, episode)
                    logger.info(f"Search Callback: Cached {media_type} info: '{title}' -> '{display_name}' S{season}E{episode} (ID: {simkl_id})")
                else:
                    # Movie or show without episode info
                    self.monitor.cache_media_info(title, simkl_id, display_name, media_type, runtime=runtime_minutes)
                    logger.info(f"Search Callback: Cached {media_type} info: '{title}' -> '{display_name}' (ID: {simkl_id})")
            else:
                logger.warning(f"Search Callback: No Simkl ID could be extracted from search result for '{title}'.")

        except Exception as e:
            # Catch unexpected errors during the API interaction or processing
            logger.exception(f"Search Callback: Unexpected error during search/cache for '{title}': {e}")
            
    def _process_file_search_result(self, title, result, filepath):
        """
        Process the results from search_file API and cache appropriately.
        
        Args:
            title (str): Original title
            result (dict): Result from search_file API
            filepath (str): File path that was searched
        """
        try:
            media_info = None
            media_type = 'movie'  # Default
            simkl_id = None
            display_name = title
            
            # Extract correct fields based on result type
            if 'movie' in result:
                media_info = result['movie']
                media_type = 'movie'
            elif 'show' in result:
                media_info = result['show']
                media_type = media_info.get('type', 'show')  # Could be 'show' or 'anime'
            
            if not media_info or not 'ids' in media_info:
                logger.warning(f"File search: Invalid or incomplete result for '{filepath}'")
                return
                
            simkl_id = media_info['ids'].get('simkl')
            if not simkl_id:
                logger.warning(f"File search: No Simkl ID in result for '{filepath}'")
                return
                
            display_name = media_info.get('title', title)
            year = media_info.get('year')
            
            # Extract episode details if available
            season = None
            episode = None
            if 'episode' in result:
                season = result['episode'].get('season')
                episode = result['episode'].get('number')
            
            # Get runtime for movies
            runtime_minutes = None
            if media_type == 'movie':
                try:
                    details = get_movie_details(simkl_id, self.client_id, self.access_token)
                    if details:
                        runtime_minutes = details.get('runtime')
                except Exception as e:
                    logger.error(f"Error getting movie details for ID {simkl_id}: {e}")
            
            # Cache the information
            if media_type in ['show', 'anime'] and season is not None and episode is not None:
                self.monitor.cache_media_info(title, simkl_id, display_name, media_type, season, episode, year)
                logger.info(f"File search: Cached {media_type} '{display_name}' S{season}E{episode} (ID: {simkl_id})")
            else:
                self.monitor.cache_media_info(title, simkl_id, display_name, media_type, runtime=runtime_minutes, year=year)
                logger.info(f"File search: Cached {media_type} '{display_name}' (ID: {simkl_id})")
                
        except Exception as e:
            logger.error(f"Error processing file search result: {e}", exc_info=True)

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