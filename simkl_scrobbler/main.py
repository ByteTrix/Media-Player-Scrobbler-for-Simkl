import time
import os
import sys
import signal
import threading
from dotenv import load_dotenv
from .media_tracker import get_active_window_info, MonitorAwareScrobbler
from .simkl_api import search_movie, mark_as_watched, authenticate, get_movie_details
import logging

# Configure logging when the module is loaded
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("simkl_scrobbler.log", mode='w')
    ]
)
logger = logging.getLogger(__name__)

# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 10
# How often to process the backlog (in polling cycles)
BACKLOG_PROCESS_INTERVAL = 30

def load_configuration():
    """Loads configuration from .env file and validates required variables."""
    # First try to load from user home directory
    user_env_path = os.path.join(os.path.expanduser("~"), ".simkl_scrobbler.env")
    if os.path.exists(user_env_path):
        load_dotenv(user_env_path)
    else:
        # Fallback to local .env file
        load_dotenv()
    
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
        self.scrobbler = MonitorAwareScrobbler()
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
                # Try fallback search (the API module already does this, but we could add more here)
        
        if simkl_id:
            # Log progress at 10% increments or when we're near completion threshold
            if state == "playing":
                if int(progress) % 10 == 0 or (progress >= 75 and progress < 80) or progress >= 80:
                    logger.info(f"Watching '{movie_name}' - Progress: {progress:.1f}%")
            elif state == "paused":
                logger.info(f"Paused '{movie_name}' at {progress:.1f}%")

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