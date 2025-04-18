import os
import sys
import time
import logging
import threading
import argparse
from dotenv import load_dotenv

# Import necessary components from our package
from simkl_movie_tracker.media_tracker import MonitorAwareScrobbler
from simkl_movie_tracker.simkl_api import search_movie, get_movie_details

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

class MoviePlaybackSimulator:
    """Simulates movie playback for testing the 80% completion tracking."""
    
    def __init__(self, movie_title, client_id, access_token, use_monitor=False):
        self.movie_title = movie_title
        self.client_id = client_id
        self.access_token = access_token
        self.use_monitor = use_monitor
        
        # Choose between standard scrobbler or monitor-aware scrobbler
        if use_monitor:
            self.scrobbler = MonitorAwareScrobbler(client_id, access_token)
        else:
            # Import here to avoid circular import
            from simkl_movie_tracker.media_tracker import MovieScrobbler
            self.scrobbler = MovieScrobbler(client_id, access_token)
            
        self.simkl_id = None
        self.movie_name = None
        self.runtime = None
        self.marked_as_watched = False
        self.progress_thread = None
    
    def setup(self):
        """Look up the movie and prepare for playback simulation."""
        logger.info(f"Looking up movie: {self.movie_title}")
        
        # Search for the movie
        movie = search_movie(self.movie_title, self.client_id, self.access_token)
        if not movie:
            logger.error(f"Failed to find movie: {self.movie_title}")
            # For testing purposes, create a fake movie if real one not found
            logger.info("Creating test movie data for simulation purposes")
            self._create_test_movie()
            return True
            
        # Verify we have a proper movie result with the required fields
        if 'movie' not in movie:
            # Some API responses might return the movie data directly without the 'movie' wrapper
            if 'ids' in movie and ('title' in movie or 'name' in movie):
                # Restructure to expected format
                movie = {'movie': movie}
            else:
                logger.error(f"Unexpected movie response format: {movie}")
                # For testing purposes, create a fake movie
                self._create_test_movie()
                return True
        
        # Extract movie info
        if 'ids' not in movie['movie']:
            logger.error(f"No IDs found in movie response: {movie}")
            self._create_test_movie()
            return True
            
        self.simkl_id = movie['movie']['ids'].get('simkl_id')
        # Some API responses use 'name' instead of 'title'
        self.movie_name = movie['movie'].get('title', movie['movie'].get('name', self.movie_title))
        
        if not self.simkl_id:
            logger.error(f"No Simkl ID found for movie: {self.movie_title}")
            self._create_test_movie()
            return True
            
        logger.info(f"Found movie: {self.movie_name} (ID: {self.simkl_id})")
        
        # Get detailed info including runtime
        details = get_movie_details(self.simkl_id, self.client_id, self.access_token)
        if details and 'runtime' in details:
            self.runtime = details['runtime']
            logger.info(f"Movie runtime: {self.runtime} minutes")
        else:
            # Use a default runtime for simulation if not available
            self.runtime = 120
            logger.info(f"Runtime not available from API, using default: {self.runtime} minutes")
        
        # Cache the movie info in the scrobbler
        self.scrobbler.cache_movie_info(self.movie_title, self.simkl_id, self.movie_name, self.runtime)
        
        # Set up the scrobbler
        if self.use_monitor:
            # For MonitorAwareScrobbler, we need to simulate a player
            logger.info("Using MonitorAwareScrobbler for testing")
            # We'll simulate the updates directly in simulate_playback
        else:
            # For regular MovieScrobbler
            self._setup_scrobbler_with_real_data()
        
        return True

    def _create_test_movie(self):
        """Create a test movie for simulation when API fails"""
        self.simkl_id = 12345  # Fake ID for testing
        self.movie_name = self.movie_title
        self.runtime = 120
        logger.info(f"Created test movie: {self.movie_name} with runtime {self.runtime} minutes")
        self._setup_scrobbler_with_test_data()
    
    def _setup_scrobbler_with_real_data(self):
        """Set up the scrobbler with real movie data"""
        self.scrobbler.currently_tracking = self.movie_title
        self.scrobbler.simkl_id = self.simkl_id
        self.scrobbler.movie_name = self.movie_name
        self.scrobbler.estimated_duration = self.runtime
        self.scrobbler.state = "playing"
        self.scrobbler.start_time = time.time()
        self.scrobbler.last_update_time = time.time()
        self.scrobbler.watch_time = 0
        self.scrobbler.completed = False
    
    def _setup_scrobbler_with_test_data(self):
        """Set up the scrobbler with test data for when API fails"""
        self.scrobbler.currently_tracking = self.movie_title
        self.scrobbler.simkl_id = self.simkl_id
        self.scrobbler.movie_name = self.movie_name
        self.scrobbler.estimated_duration = self.runtime
        self.scrobbler.state = "playing"
        self.scrobbler.start_time = time.time()
        self.scrobbler.last_update_time = time.time()
        self.scrobbler.watch_time = 0
        self.scrobbler.completed = False
        
    def simulate_playback(self, target_percentage=85, speed_factor=100):
        """
        Simulate movie playback up to the specified percentage.
        
        Args:
            target_percentage: The percentage of the movie to "watch" (default 85%)
            speed_factor: How much faster to simulate playback (default 100x speed)
        """
        if not self.simkl_id or not self.runtime:
            logger.error("Movie not properly set up for simulation")
            return False
            
        # Calculate how long we need to simulate playback
        target_minutes = (self.runtime * target_percentage) / 100
        logger.info(f"Starting playback simulation, target: {target_percentage}% ({target_minutes:.1f} minutes)")
        logger.info(f"Using accelerated simulation at {speed_factor}x speed")
        
        # Monitor progress in a separate thread
        self.progress_thread = threading.Thread(target=self._monitor_progress)
        self.progress_thread.daemon = True
        self.progress_thread.start()
        
        # Simulate playback time passing
        start_time = time.time()
        
        # For super fast testing, just jump straight to near the threshold
        if speed_factor > 50:
            # Jump directly to 75% completion
            initial_jump = (self.runtime * 75) / 100
            logger.info(f"Fast simulation: Jumping directly to 75% ({initial_jump:.1f} minutes)")
            self.scrobbler.watch_time = initial_jump * 60  # Convert to seconds
        
        if self.use_monitor:
            # For MonitorAwareScrobbler, simulate media updates
            logger.info(f"Simulating media player updates for MonitorAwareScrobbler")
            # Create a fake window info for the monitor
            window_info = {
                'title': self.movie_title,
                'process_name': 'vlc.exe',  # Pretend we're using VLC
                'state': 'playing'
            }
            
            # Set testing mode flag for API simulation
            if hasattr(self.scrobbler, 'client_id') and self.scrobbler.client_id == 12345:
                self.scrobbler.testing_mode = True
            
            # Directly update the watch time and process the window periodically
            while self.scrobbler.watch_time / 60 < target_minutes and not self.marked_as_watched:
                # Accelerate time based on speed factor
                elapsed = (time.time() - self.scrobbler.last_update_time) * speed_factor
                self.scrobbler.watch_time += elapsed
                self.scrobbler.last_update_time = time.time()
                
                # Process the window to trigger updates
                scrobble_info = self.scrobbler.process_window(window_info)
                
                # Force testing mode check for completion at each iteration
                if self.scrobbler.watch_time / 60 > (self.runtime * 0.8):
                    # Manually call the monitor process media method to check for completion
                    if hasattr(self.scrobbler, '_process_monitor_media'):
                        media_info = {
                            'title': self.movie_title,
                            'state': 'playing',
                            'player': 'VLC Media Player',
                            'timestamp': time.time()
                        }
                        self.scrobbler._process_monitor_media(media_info)
                
                # Check if we need to mark as watched (80% threshold)
                if self.scrobbler.is_complete(threshold=80) and not self.marked_as_watched:
                    logger.info(f"80% threshold reached, checking if movie was marked as watched")
                    if hasattr(self.scrobbler, 'completed') and self.scrobbler.completed:
                        logger.info(f"✓ Successfully marked '{self.movie_name}' as watched on Simkl")
                        self.marked_as_watched = True
                        break
                
                # Short delay to prevent CPU spinning
                time.sleep(0.1)
        else:
            # For regular MovieScrobbler
            while self.scrobbler.watch_time / 60 < target_minutes and not self.marked_as_watched:
                # Accelerate time based on speed factor
                elapsed = (time.time() - self.scrobbler.last_update_time) * speed_factor
                self.scrobbler.watch_time += elapsed
                self.scrobbler.last_update_time = time.time()
                
                # Check if we need to mark as watched (80% threshold)
                if self.scrobbler.is_complete(threshold=80) and not self.marked_as_watched:
                    logger.info(f"80% threshold reached, marking movie as watched")
                    result = self.scrobbler.mark_as_finished(self.simkl_id, self.movie_name)
                    if result:
                        logger.info(f"✓ Successfully marked '{self.movie_name}' as watched on Simkl")
                        self.marked_as_watched = True
                    else:
                        logger.error(f"Failed to mark movie as watched")
                
                # Short delay to prevent CPU spinning
                time.sleep(0.1)
            
        # Simulation complete
        total_time = time.time() - start_time
        logger.info(f"Playback simulation complete after {total_time:.1f} seconds")
        logger.info(f"Simulated watch time: {self.scrobbler.watch_time/60:.1f} minutes")
        
        if self.progress_thread.is_alive():
            self.progress_thread.join(timeout=1)
            
        return self.marked_as_watched
        
    def _monitor_progress(self):
        """Monitor and log playback progress."""
        last_reported = 0
        
        while True:
            if not self.scrobbler.currently_tracking:
                break
                
            # Calculate current progress
            watched_minutes = self.scrobbler.watch_time / 60
            percentage = min(100, (watched_minutes / self.runtime) * 100)
            
            # Log progress at 10% increments
            current_ten = int(percentage / 10)
            if current_ten > last_reported:
                logger.info(f"Playback progress: {percentage:.1f}% ({watched_minutes:.1f} min of {self.runtime} min)")
                last_reported = current_ten
                
            # Check if we're done
            if percentage >= 100 or self.marked_as_watched:
                break
                
            time.sleep(1)

def load_credentials():
    """Load Simkl API credentials from .env file."""
    load_dotenv()
    client_id = os.getenv("SIMKL_CLIENT_ID")
    access_token = os.getenv("SIMKL_ACCESS_TOKEN")
    
    if not client_id:
        logger.error("SIMKL_CLIENT_ID not found in environment variables")
        sys.exit(1)
        
    return client_id, access_token

def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description="Test movie completion detection")
    parser.add_argument("-t", "--title", help="Movie title to test with", required=True)
    parser.add_argument("-m", "--monitor", help="Use monitor-aware scrobbler", action="store_true")
    parser.add_argument("--test-mode", help="Run in test mode without API calls", action="store_true")
    args = parser.parse_args()
    
    logger.info(f"Testing movie completion for: {args.title}")
    
    client_id, access_token = load_credentials()
    
    if not access_token:
        logger.error("No access token found. Please set up authentication first.")
        sys.exit(1)
        
    # Use the test movie name
    movie_title = args.title
    
    # Create simulator
    simulator = MoviePlaybackSimulator(movie_title, client_id, access_token, use_monitor=args.monitor)
    
    # Test mode doesn't use real API calls
    if args.test_mode:
        logger.info("Running in TEST MODE without real API calls")
        simulator.simkl_id = 12345  # Fake ID for testing
        simulator.movie_name = movie_title
        simulator.runtime = 10  # Use a short runtime for fast testing
        
        if args.monitor:
            # Use monitor-aware scrobbler
            logger.info("Setting up MonitorAwareScrobbler for test mode")
            simulator.use_monitor = True
            # Cache the movie info
            simulator.scrobbler.cache_movie_info(movie_title, simulator.simkl_id, movie_title, simulator.runtime)
        else:
            # Set up the scrobbler with test data
            simulator._setup_scrobbler_with_test_data()
            
        # Run simulation with extra speed
        result = simulator.simulate_playback(target_percentage=85, speed_factor=200)
    else:
        # Normal mode with API calls
        if simulator.setup():
            # Override runtime to be shorter for faster testing
            if simulator.runtime > 10:
                logger.info(f"Reducing runtime from {simulator.runtime} to 10 minutes for fast testing")
                simulator.runtime = 10
                simulator.scrobbler.estimated_duration = 10
            
            result = simulator.simulate_playback(target_percentage=85, speed_factor=100)
        else:
            logger.error("Failed to set up movie playback simulation")
            return
    
    if result:
        logger.info("✓ Test completed successfully - Movie marked as watched")
    else:
        logger.error("✗ Test failed - Movie was not marked as watched")

if __name__ == "__main__":
    main()