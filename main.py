import time
import os
import sys
import signal
import threading
from dotenv import load_dotenv
# Update imports to use the new scrobbler functionality
from simkl_movie_tracker.media_tracker import get_active_window_info, parse_movie_title, MovieScrobbler
# Import API functions
from simkl_movie_tracker.simkl_api import search_movie, mark_as_watched, authenticate
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
    load_dotenv() # Load variables from .env file into environment
    client_id = os.getenv("SIMKL_CLIENT_ID")
    access_token = os.getenv("SIMKL_ACCESS_TOKEN") # Check if already exists

    # Only client_id is essential to start the auth flow
    if not client_id:
        print("Error: SIMKL_CLIENT_ID not found in environment variables.")
        print("Please ensure you have a .env file with this value.")
        sys.exit(1) # Exit if essential config is missing

    # If no access token, try to authenticate using device flow
    if not access_token:
        print("Access token not found, attempting device authentication...")
        # Call the new authenticate function which only needs client_id
        access_token = authenticate(client_id)
        if access_token:
            print("Authentication successful. You should add the following line to your .env file to avoid authenticating next time:")
            print(f"SIMKL_ACCESS_TOKEN={access_token}")
            # Note: We are not automatically saving it back to .env here for simplicity/security.
        else:
            print("Authentication failed. Please check your client ID and ensure you complete the authorization step on Simkl.")
            sys.exit(1) # Exit if authentication fails

    # Return client_id and the obtained/loaded access_token
    return client_id, access_token

class SimklMovieTracker:
    """Main application class for tracking movies and scrobbling to Simkl"""
    
    def __init__(self):
        self.poll_interval = DEFAULT_POLL_INTERVAL
        self.running = False
        self.scrobbler = MovieScrobbler()
        self.backlog_counter = 0
        self.client_id = None
        self.access_token = None
        
    def initialize(self):
        """Initialize the tracker and authenticate with Simkl"""
        logger.info("Initializing Simkl Movie Tracker...")
        
        # Load API credentials
        self.client_id, self.access_token = load_configuration()
        
        if not self.client_id or not self.access_token:
            logger.error("Exiting due to configuration/authentication issues.")
            return False
            
        # Set credentials in the scrobbler
        self.scrobbler.set_credentials(self.client_id, self.access_token)
        
        # Process any pending backlog items
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
            
            # Setup signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            # Start the main polling loop
            self._polling_loop()
            
    def stop(self):
        """Stop the movie tracker"""
        if self.running:
            logger.info("Stopping Simkl Movie Tracker...")
            self.running = False
            
    def _signal_handler(self, sig, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        self.stop()
        
    def _polling_loop(self):
        """Main polling loop for tracking movies"""
        while self.running:
            try:
                # Get the current active window
                window_info = get_active_window_info()
                
                # Process the window with the scrobbler
                scrobble_info = self.scrobbler.process_window(window_info)
                
                # Handle scrobbling updates if needed
                if scrobble_info:
                    self._handle_scrobble_update(scrobble_info)
                    
                # Periodically process the backlog
                self.backlog_counter += 1
                if self.backlog_counter >= BACKLOG_PROCESS_INTERVAL:
                    backlog_count = self.scrobbler.process_backlog()
                    if backlog_count > 0:
                        logger.info(f"Processed {backlog_count} items from backlog")
                    self.backlog_counter = 0
                    
                # Sleep until next poll
                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                # Don't crash the app, just continue with the next iteration
                time.sleep(self.poll_interval)
                
    def _handle_scrobble_update(self, scrobble_info):
        """Handle a scrobble update from the tracker"""
        title = scrobble_info.get("title")
        simkl_id = scrobble_info.get("simkl_id")
        movie_name = scrobble_info.get("movie_name", title)
        state = scrobble_info.get("state")
        progress = scrobble_info.get("progress", 0)
        
        # If we don't have a Simkl ID yet, search for the movie
        if not simkl_id and title:
            logger.info(f"Searching for movie: {title}")
            movie = search_movie(title, self.client_id, self.access_token)
            
            if movie and 'movie' in movie and 'ids' in movie['movie']:
                simkl_id = movie['movie']['ids'].get('simkl_id')
                movie_name = movie['movie'].get('title', title)
                
                if simkl_id:
                    logger.info(f"Found movie: '{movie_name}' (ID: {simkl_id})")
                    
                    # Get detailed movie info including runtime
                    from simkl_movie_tracker.simkl_api import get_movie_details
                    movie_details = get_movie_details(simkl_id, self.client_id, self.access_token)
                    
                    # Extract runtime if available
                    runtime = None
                    if movie_details and 'runtime' in movie_details:
                        runtime = movie_details['runtime']
                        logger.info(f"Retrieved actual runtime: {runtime} minutes")
                    
                    # Cache the movie info for future use
                    cache_data = {
                        "simkl_id": simkl_id,
                        "movie_name": movie_name
                    }
                    
                    if runtime:
                        cache_data["runtime"] = runtime
                    
                    self.scrobbler.cache_movie_info(title, simkl_id, movie_name)
                    
                    # If we got runtime info, update the scrobbler's estimated duration
                    if runtime and hasattr(self.scrobbler, 'estimated_duration'):
                        self.scrobbler.estimated_duration = runtime
                else:
                    logger.warning(f"Movie found but no Simkl ID available: {movie}")
            else:
                logger.warning(f"No matching movie found for '{title}'")
        
        # Log the current state and progress
        if simkl_id:
            # Only log every 10% or on state changes to reduce spam
            if state == "playing" and (int(progress) % 10 == 0 or int(progress) >= 80):
                logger.info(f"Watching '{movie_name}' - Progress: {progress:.1f}%")
            elif state == "paused":
                logger.info(f"Paused '{movie_name}' at {progress:.1f}%")
                
            # If progress is over 80%, mark as watched
            if progress >= 80 and state != "stopped":
                logger.info(f"Progress {progress:.1f}% reached threshold (80%) for '{movie_name}'")
                self.scrobbler.mark_as_finished(simkl_id, movie_name)

def run_as_background_service():
    """Run the tracker as a background service"""
    tracker = SimklMovieTracker()
    if tracker.initialize():
        # Start in a background thread
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