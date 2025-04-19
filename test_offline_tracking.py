import os
import sys
import time
import logging
import threading
from datetime import datetime

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.abspath(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from simkl_movie_tracker.media_tracker import MonitorAwareScrobbler
from simkl_movie_tracker.simkl_api import is_internet_connected

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("offline_test.log", mode='w')
    ]
)
logger = logging.getLogger()

def simulate_movie_watch(scrobbler, movie_title="Test Movie (2023)", simkl_id=12345, duration=120):
    """Simulate watching a movie to test offline tracking"""
    logger.info(f"Starting to simulate watching: {movie_title}")
    
    # Create a fake window info to pass to the scrobbler
    fake_window = {
        'title': f"{movie_title} - VLC media player",
        'process_name': 'vlc.exe',
        'hwnd': 12345  # Fake HWND
    }
    
    # Start tracking this movie
    scrobbler.process_window(fake_window)
    
    # Cache movie info
    scrobbler.cache_movie_info(movie_title, simkl_id, movie_title, duration//60)
    
    # Simulate movie playback for 2 minutes (at 10x speed for testing)
    total_watch_time = 0
    while total_watch_time < duration and scrobbler.currently_tracking:
        # Update every second but simulate 10 seconds of playback
        scrobbler.current_position_seconds += 10
        scrobbler.watch_time += 10
        total_watch_time += 10
        
        # Process window again to trigger progress checks
        scrobbler.process_window(fake_window)
        
        # Display progress
        if total_watch_time % 20 == 0:
            percentage = scrobbler._calculate_percentage()
            logger.info(f"Simulated progress: {percentage:.1f}% of {movie_title}")
        
        # Sleep briefly to avoid hogging the CPU
        time.sleep(1)
    
    # Complete the movie (should trigger marking as finished)
    logger.info(f"Completed watching: {movie_title}")
    
    # Stop tracking
    scrobbler.stop_tracking()

def test_offline_tracking():
    """Test that movies are properly tracked when offline and synced when online"""
    
    # Initialize the scrobbler
    scrobbler = MonitorAwareScrobbler()
    scrobbler.set_poll_interval(5)
    
    # Use test credentials
    scrobbler.set_credentials("test_client_id", "test_access_token")

    # Clear any existing backlog
    scrobbler.backlog.clear()
    logger.info("Cleared existing backlog for testing")
    
    # Override is_internet_connected to simulate offline state
    import simkl_movie_tracker.simkl_api
    original_is_connected = simkl_movie_tracker.simkl_api.is_internet_connected
    
    # Start with offline mode
    simkl_movie_tracker.simkl_api.is_internet_connected = lambda: False
    logger.info("SIMULATING OFFLINE MODE - Internet connectivity check will return False")
    
    # Check the backlog count before starting
    initial_backlog_count = len(scrobbler.backlog.get_pending())
    logger.info(f"Initial backlog count: {initial_backlog_count}")
    
    # Simulate watching 3 movies while offline
    movie_data = [
        {"title": "Test Movie 1 (2023)", "simkl_id": 12345, "duration": 120},
        {"title": "Test Movie 2 (2023)", "simkl_id": 54321, "duration": 90},
        {"title": "Test Movie 3 (2023)", "simkl_id": 98765, "duration": 150}
    ]
    
    for movie in movie_data:
        simulate_movie_watch(scrobbler, movie["title"], movie["simkl_id"], movie["duration"])
        # Brief pause between movies
        time.sleep(2)
    
    # Check the backlog after watching
    offline_backlog_count = len(scrobbler.backlog.get_pending())
    logger.info(f"Backlog count after watching movies offline: {offline_backlog_count}")
    logger.info(f"Backlog contents: {scrobbler.backlog.get_pending()}")
    
    # Now simulate coming back online
    logger.info("\nSIMULATING COMING BACK ONLINE")
    simkl_movie_tracker.simkl_api.is_internet_connected = lambda: True
    logger.info("Internet connectivity check will now return True")
    
    # Override mark_as_watched to avoid actual API calls
    original_mark_as_watched = simkl_movie_tracker.simkl_api.mark_as_watched
    simkl_movie_tracker.simkl_api.mark_as_watched = lambda simkl_id, client_id, access_token: True
    
    # Process the backlog
    logger.info("Processing backlog...")
    synced_count = scrobbler.process_backlog()
    
    # Check results
    final_backlog_count = len(scrobbler.backlog.get_pending())
    logger.info(f"Synced {synced_count} movies from backlog")
    logger.info(f"Final backlog count: {final_backlog_count}")
    logger.info(f"Remaining backlog contents: {scrobbler.backlog.get_pending()}")
    
    # Restore original functions
    simkl_movie_tracker.simkl_api.is_internet_connected = original_is_connected
    simkl_movie_tracker.simkl_api.mark_as_watched = original_mark_as_watched
    
    # Report success/failure
    if initial_backlog_count == 0 and offline_backlog_count > 0 and final_backlog_count == 0:
        logger.info("\n✅ TEST PASSED: Movies were correctly added to backlog when offline and synced when online")
    else:
        logger.info("\n❌ TEST FAILED: Offline tracking did not work as expected")
        
    logger.info("Test complete")

if __name__ == "__main__":
    logger.info("Starting offline tracking test")
    logger.info("=" * 50)
    
    test_offline_tracking()