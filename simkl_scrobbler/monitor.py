"""
Monitor module for SIMKL Scrobbler.
Handles continuous window monitoring and scrobbling.
"""

import time
import logging
import threading
import platform
from datetime import datetime

# Import from our own modules
from simkl_scrobbler.window_detection import (
    get_active_window_info, 
    get_all_windows_info,
    is_video_player  # Move this import here
)
from simkl_scrobbler.movie_scrobbler import MovieScrobbler

# Configure module logging
logger = logging.getLogger(__name__)

# Platform-specific settings
PLATFORM = platform.system().lower()

class Monitor:
    """Continuously monitors windows for movie playback"""

    def __init__(self, app_data_dir, client_id=None, access_token=None, poll_interval=10, 
                 testing_mode=False, backlog_check_interval=300):
        self.app_data_dir = app_data_dir
        self.client_id = client_id
        self.access_token = access_token
        self.poll_interval = poll_interval
        self.testing_mode = testing_mode
        self.running = False
        self.monitor_thread = None
        self._lock = threading.RLock()  # Add a lock for thread safety
        self.scrobbler = MovieScrobbler(
            app_data_dir=self.app_data_dir,
            client_id=self.client_id,
            access_token=self.access_token,
            testing_mode=self.testing_mode
        )
        self.last_backlog_check = 0
        self.backlog_check_interval = backlog_check_interval  # Configurable parameter
        self.search_callback = None  # Callback for movie search

    def set_search_callback(self, callback):
        """Set the callback function for movie search"""
        self.search_callback = callback

    def start(self):
        """Start monitoring"""
        if self.running:
            logger.warning("Monitor already running")
            return False

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Monitor started")
        return True

    def stop(self):
        """Stop monitoring"""
        if not self.running:
            logger.warning("Monitor not running")
            return False

        # Set the flag first
        self.running = False
        
        # Then handle the thread
        if self.monitor_thread and self.monitor_thread.is_alive():
            try:
                # Wait for thread to finish with timeout
                self.monitor_thread.join(timeout=2)
            except RuntimeError:
                logger.warning("Could not join monitor thread")
        
        # Stop any active tracking with the lock to prevent race conditions
        with self._lock:
            if self.scrobbler.currently_tracking:
                self.scrobbler.stop_tracking()
        
        logger.info("Monitor stopped")
        return True

    def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Monitor loop started")
        check_count = 0

        while self.running:
            try:
                # First get all windows and find video player windows
                found_player = False
                all_windows = get_all_windows_info()
                
                # Find a video player window if any
                for win in all_windows:
                    if is_video_player(win):
                        window_info = win
                        found_player = True
                        logger.debug(f"Found video player window: {win.get('title', 'Unknown')}")
                        
                        # Process this player window
                        with self._lock:  # Use lock when accessing shared resources
                            scrobble_info = self.scrobbler.process_window(window_info)
                        
                        # If we get scrobble info and need to search for the movie
                        if scrobble_info and self.search_callback and not scrobble_info.get("simkl_id"):
                            title = scrobble_info.get("title", "Unknown")
                            logger.info(f"Movie needs identification: {title}")
                            # Call the search callback
                            self.search_callback(title)
                        
                        # We found and processed a player, no need to check further
                        break
                
                # Only stop tracking if no player window found
                if not found_player and self.scrobbler.currently_tracking:
                    logger.info("No player window detected among all windows, stopping tracking")
                    with self._lock:
                        self.scrobbler.stop_tracking()

                # Process backlog periodically
                check_count += 1
                current_time = time.time()
                if current_time - self.last_backlog_check > self.backlog_check_interval:
                    logger.debug("Checking backlog...")
                    with self._lock:
                        synced_count = self.scrobbler.process_backlog()
                    
                    if synced_count > 0:
                        logger.info(f"Synced {synced_count} items from backlog")
                    self.last_backlog_check = current_time

                # Sleep until next poll
                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                # Sleep a bit longer on error to avoid spamming logs
                time.sleep(max(5, self.poll_interval))

        logger.info("Monitor loop exited")

    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token
        self.scrobbler.set_credentials(client_id, access_token)

    def cache_movie_info(self, title, simkl_id, movie_name, runtime=None):
        """Cache movie info to avoid repeated searches"""
        self.scrobbler.cache_movie_info(title, simkl_id, movie_name, runtime)