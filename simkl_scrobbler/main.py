import time
import os
import sys
import signal
import threading
import pathlib  # Import pathlib
from dotenv import load_dotenv
from .media_tracker import get_active_window_info, MonitorAwareScrobbler
from .simkl_api import search_movie, mark_as_watched, authenticate, get_movie_details
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
logger = logging.getLogger(__name__)
logger.info(f"Main application log file configured at: {log_file_path}") # Logged to file only
logger.info(f"Using application data directory: {APP_DATA_DIR}") # Logged to file only

# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 10
# How often to process the backlog (in polling cycles)
BACKLOG_PROCESS_INTERVAL = 30

def load_configuration():
    """Loads configuration from .env file and validates required variables."""
    # Load .env file ONLY from the application data directory
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
    if env_path.exists():
        logger.info(f"Loading configuration from: {env_path}")
        load_dotenv(env_path)
    else:
        logger.warning(f"Configuration file not found at: {env_path}")
        # No fallback, proceed without loading if not found
    
    # Import the default client ID from simkl_api module
    from .simkl_api import DEFAULT_CLIENT_ID
    
    # Get client ID from environment or use default
    client_id = os.getenv("SIMKL_CLIENT_ID", DEFAULT_CLIENT_ID)
    access_token = os.getenv("SIMKL_ACCESS_TOKEN")

    if not client_id:
        logger.error("Client ID not found. Using default client ID.")
        client_id = DEFAULT_CLIENT_ID

    if not access_token:
        logger.info("Access token not found, attempting device authentication...")
        print("Access token not found, attempting device authentication...")
        print("You'll need to authenticate with your Simkl account.")
        access_token = authenticate(client_id)
        if access_token:
            logger.info("Authentication successful.")
            print("Authentication successful. You should run 'simkl-scrobbler init' to save this token.")
            print(f"SIMKL_ACCESS_TOKEN={access_token}")
        else:
            logger.error("Authentication failed.")
            print("Authentication failed. Please check your internet connection and ensure you complete the authorization step on Simkl.")
            sys.exit(1)

    return client_id, access_token

class SimklScrobbler:
    """Main application class for tracking movies and scrobbling to Simkl"""
    
    def __init__(self):
        self.poll_interval = DEFAULT_POLL_INTERVAL
        self.running = False
        # Pass the app data directory to the scrobbler
        self.scrobbler = MonitorAwareScrobbler(app_data_dir=APP_DATA_DIR)
        self.backlog_counter = 0
        self.client_id = None
        self.access_token = None
        
    def initialize(self):
        """Initialize the scrobbler and authenticate with Simkl"""
        logger.info("Initializing Simkl Scrobbler...")
        
        self.client_id, self.access_token = load_configuration()
        
        if not self.client_id or not self.access_token:
            logger.error("Exiting due to configuration/authentication issues.")
            return False
            
        self.scrobbler.set_credentials(self.client_id, self.access_token)
        
        backlog_count = self.scrobbler.process_backlog()
        if backlog_count > 0:
            logger.info(f"Processed {backlog_count} items from backlog during startup")
            
        return True
        
    def start(self):
        """Start the movie scrobbler main loop"""
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
            
            # Register the scrobble callback function
            self.scrobbler.set_scrobble_callback(self._handle_scrobble_update)
            
            # Use the enhanced monitoring system
            self.scrobbler.start_monitoring()
            self._backlog_check_loop()
            
    def stop(self):
        """Stop the movie scrobbler"""
        if self.running:
            logger.info("Stopping Simkl Scrobbler...")
            self.running = False
            self.scrobbler.stop_monitoring()
    
    def _signal_handler(self, sig, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        self.stop()
        
    def _backlog_check_loop(self):
        """Loop to periodically check for backlogged items to sync"""
        while self.running:
            try:
                time.sleep(self.poll_interval * BACKLOG_PROCESS_INTERVAL)
                
                if not self.running:
                    break
                    
                backlog_count = self.scrobbler.process_backlog()
                if backlog_count > 0:
                    logger.info(f"Processed {backlog_count} items from backlog")
                    
            except Exception as e:
                logger.error(f"Error in backlog check loop: {e}")
                time.sleep(self.poll_interval)
                
    def _handle_scrobble_update(self, scrobble_info):
        """Handle a scrobble update from the tracker"""
        title = scrobble_info.get("title")
        simkl_id = scrobble_info.get("simkl_id")
        movie_name = scrobble_info.get("movie_name", title)
        state = scrobble_info.get("state")
        progress = scrobble_info.get("progress", 0)
        
        if not simkl_id and title:
            logger.info(f"Searching for movie: {title}")
            movie = search_movie(title, self.client_id, self.access_token)
            
            if movie:
                # The search_movie function can return results in different formats
                # Let's handle both possible structures
                
                # If it has a 'movie' key, use that structure
                if 'movie' in movie:
                    movie_data = movie['movie']
                    
                    # Check for IDs in the movie data
                    if 'ids' in movie_data:
                        ids = movie_data['ids']
                        # Try both possible ID keys
                        simkl_id = ids.get('simkl')
                        if not simkl_id:
                            simkl_id = ids.get('simkl_id')
                        
                        movie_name = movie_data.get('title', title)
                    else:
                        # If no IDs section, check if the top level has an ID
                        simkl_id = movie_data.get('simkl_id')
                        movie_name = movie_data.get('title', title)
                        
                # If no 'movie' key, the result might be the movie object directly        
                else:
                    # Try to get ID from the top level
                    simkl_id = movie.get('simkl_id')
                    
                    # Or check if there's an 'ids' section
                    if 'ids' in movie:
                        ids = movie['ids']
                        if not simkl_id:
                            simkl_id = ids.get('simkl')
                        if not simkl_id:
                            simkl_id = ids.get('simkl_id')
                            
                    movie_name = movie.get('title', title)
                
                if simkl_id:
                    logger.info(f"Found movie: '{movie_name}' (ID: {simkl_id})")
                    
                    movie_details = get_movie_details(simkl_id, self.client_id, self.access_token)
                    
                    runtime = None
                    if movie_details and 'runtime' in movie_details:
                        runtime = movie_details['runtime']
                        logger.info(f"Retrieved actual runtime: {runtime} minutes")
                    
                    # Cache the movie info with the runtime
                    self.scrobbler.cache_movie_info(title, simkl_id, movie_name, runtime)
                else:
                    logger.warning(f"Movie found but no Simkl ID available in any expected format: {movie}")
            else:
                logger.warning(f"No matching movie found for '{title}'")
                
                # Check if there's an available duration and significant progress (indicating a likely movie)
                duration = scrobble_info.get("total_duration_seconds")
                watched_seconds = scrobble_info.get("watched_seconds", 0)
                watched_enough = False
                
                # If we have duration info, check if watched enough to consider adding to backlog
                if duration and duration > 0:
                    watched_pct = (watched_seconds / duration) * 100
                    watched_enough = watched_pct >= 80
                elif watched_seconds > 600:  # Over 10 minutes watched is significant even without knowing total length
                    watched_enough = True
                
                # Import here to avoid circular imports
                from .simkl_api import is_internet_connected
                
                # If no internet connection and watched enough, add to backlog
                if not is_internet_connected() and watched_enough:
                    logger.info(f"No internet connection, adding '{title}' to backlog for future syncing")
                    
                    # Generate a temporary simkl_id to use until we can get the real one
                    # We'll use "temp_" prefix followed by a hash of the title to make it unique
                    import hashlib
                    temp_id = f"temp_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                    
                    # Store in backlog for future processing
                    self.scrobbler.backlog.add(temp_id, title)
                elif not is_internet_connected():
                    logger.info(f"No internet connection, but not enough progress to add '{title}' to backlog yet")
        
        if simkl_id:
            # Log progress at 10% increments or when we're near completion threshold
            if state == "playing":
                if int(progress) % 10 == 0 or (progress >= 75 and progress < 80) or progress >= 80:
                    logger.info(f"Watching '{movie_name}' - Progress: {progress:.1f}%")
            elif state == "paused":
                logger.info(f"Paused '{movie_name}' at {progress:.1f}%")
                
        # If watching is at completion threshold but no internet, add to backlog
        if progress and progress >= 80 and not simkl_id:
            from .simkl_api import is_internet_connected
            if not is_internet_connected():
                import hashlib
                temp_id = f"temp_{hashlib.md5(title.encode()).hexdigest()[:8]}"
                
                # Check if this movie is already in backlog
                existing_items = [item for item in self.scrobbler.backlog.get_pending() 
                                 if item.get("title") == title]
                
                if not existing_items:
                    logger.info(f"Movie '{title}' completed, adding to backlog for future syncing when online")
                    self.scrobbler.backlog.add(temp_id, title)

def run_as_background_service():
    """Run the scrobbler as a background service"""
    scrobbler = SimklScrobbler()
    if scrobbler.initialize():
        thread = threading.Thread(target=scrobbler.start)
        thread.daemon = True
        thread.start()
        return scrobbler
    return None

def main():
    """Main entry point for the application"""
    logger.info("Starting Simkl Scrobbler application")
    scrobbler = SimklScrobbler()
    if scrobbler.initialize():
        scrobbler.start()
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()