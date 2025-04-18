import time
import os
import sys
import signal
import threading
from dotenv import load_dotenv
from simkl_movie_tracker.media_tracker import get_active_window_info, MonitorAwareScrobbler
from simkl_movie_tracker.simkl_api import search_movie, mark_as_watched, authenticate, get_movie_details
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("simkl_tracker.log")
    ]
)
logger = logging.getLogger(__name__)

# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 10
# How often to process the backlog (in polling cycles)
BACKLOG_PROCESS_INTERVAL = 30

def load_configuration():
    """Loads configuration from .env file and validates required variables."""
    load_dotenv()
    client_id = os.getenv("SIMKL_CLIENT_ID")
    access_token = os.getenv("SIMKL_ACCESS_TOKEN")

    if not client_id:
        print("Error: SIMKL_CLIENT_ID not found in environment variables.")
        print("Please ensure you have a .env file with this value.")
        sys.exit(1)

    if not access_token:
        print("Access token not found, attempting device authentication...")
        access_token = authenticate(client_id)
        if access_token:
            print("Authentication successful. You should add the following line to your .env file to avoid authenticating next time:")
            print(f"SIMKL_ACCESS_TOKEN={access_token}")
        else:
            print("Authentication failed. Please check your client ID and ensure you complete the authorization step on Simkl.")
            sys.exit(1)

    return client_id, access_token

class SimklMovieTracker:
    """Main application class for tracking movies and scrobbling to Simkl"""
    
    def __init__(self):
        self.poll_interval = DEFAULT_POLL_INTERVAL
        self.running = False
        # Use the enhanced MonitorAwareScrobbler instead of basic MovieScrobbler
        self.scrobbler = MonitorAwareScrobbler()
        self.backlog_counter = 0
        self.client_id = None
        self.access_token = None
        
    def initialize(self):
        """Initialize the tracker and authenticate with Simkl"""
        logger.info("Initializing Simkl Movie Tracker...")
        
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
        """Start the movie tracker main loop"""
        if not self.running:
            self.running = True
            logger.info("Starting Simkl Movie Tracker...")
            logger.info("Monitoring for supported video players...")
            logger.info("Supported players: VLC, MPC-HC, Windows Media Player, MPV, etc.")
            logger.info("Movies will be marked as watched after viewing 80% of their estimated duration")
            
            # Only set up signal handlers when running in the main thread
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            
            # Use the enhanced monitoring system instead of the basic polling loop
            self.scrobbler.start_monitoring()
            self._backlog_check_loop()
            
    def stop(self):
        """Stop the movie tracker"""
        if self.running:
            logger.info("Stopping Simkl Movie Tracker...")
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
            
            if movie and 'movie' in movie and 'ids' in movie['movie']:
                simkl_id = movie['movie']['ids'].get('simkl_id')
                movie_name = movie['movie'].get('title', title)
                
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
                    logger.warning(f"Movie found but no Simkl ID available: {movie}")
            else:
                logger.warning(f"No matching movie found for '{title}'")
        
        if simkl_id:
            # Log progress at 10% increments or when we're near completion threshold
            if state == "playing":
                if int(progress) % 10 == 0 or (progress >= 75 and progress < 80) or progress >= 80:
                    logger.info(f"Watching '{movie_name}' - Progress: {progress:.1f}%")
            elif state == "paused":
                logger.info(f"Paused '{movie_name}' at {progress:.1f}%")
            
            # The automatic marking at 80% is now handled in the MovieScrobbler class
            # We no longer need to manually check for the 80% threshold and mark as watched here

def run_as_background_service():
    """Run the tracker as a background service"""
    tracker = SimklMovieTracker()
    if tracker.initialize():
        thread = threading.Thread(target=tracker.start)
        thread.daemon = True
        thread.start()
        return tracker
    return None

def main():
    """Main entry point for the application"""
    tracker = SimklMovieTracker()
    if tracker.initialize():
        tracker.start()
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()