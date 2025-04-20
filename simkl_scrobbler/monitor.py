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
from simkl_scrobbler.window_detection import get_active_window_info, get_all_windows_info
from simkl_scrobbler.movie_scrobbler import MovieScrobbler

# Configure module logging
logger = logging.getLogger(__name__)

# Platform-specific settings
PLATFORM = platform.system().lower()

class Monitor:
    """Continuously monitors windows for movie playback"""

    def __init__(self, app_data_dir, client_id=None, access_token=None, poll_interval=10, testing_mode=False):
        self.app_data_dir = app_data_dir
        self.client_id = client_id
        self.access_token = access_token
        self.poll_interval = poll_interval
        self.testing_mode = testing_mode
        self.running = False
        self.monitor_thread = None
        self.scrobbler = MovieScrobbler(
            app_data_dir=self.app_data_dir,
            client_id=self.client_id,
            access_token=self.access_token,
            testing_mode=self.testing_mode
        )
        self.last_backlog_check = 0
        self.backlog_check_interval = 5 * 60  # Check backlog every 5 minutes
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

        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            # Wait for thread to finish with timeout
            self.monitor_thread.join(timeout=2)
        
        # Stop any active tracking
        if self.scrobbler.currently_tracking:
            self.scrobbler.stop_tracking()
            
        logger.info("Monitor stopped")
        return True

    def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Monitor loop started")
        last_window_info = None
        check_count = 0

        while self.running:
            try:
                # Get active window
                window_info = get_active_window_info()
                
                if not window_info:
                    # If active window detection fails, try getting all windows
                    all_windows = get_all_windows_info()
                    # Find a video player window if any
                    for win in all_windows:
                        from simkl_scrobbler.window_detection import is_video_player
                        if is_video_player(win):
                            window_info = win
                            logger.debug(f"Using video player window from all windows: {win.get('title')}")
                            break

                if window_info:
                    if last_window_info != window_info:
                        logger.debug(f"Active window: {window_info.get('title')} ({window_info.get('process_name')})")
                        last_window_info = window_info

                    # Process window and get scrobble info
                    scrobble_info = self.scrobbler.process_window(window_info)
                    
                    # If we get scrobble info and need to search for the movie
                    if scrobble_info and self.search_callback and not scrobble_info.get("simkl_id"):
                        logger.info(f"Movie needs identification: {scrobble_info.get('title')}")
                        # Call the search callback
                        self.search_callback(scrobble_info.get("title"))
                else:
                    # If no active window detected and we were tracking something, stop tracking
                    if self.scrobbler.currently_tracking:
                        logger.info("No active window detected, stopping tracking")
                        self.scrobbler.stop_tracking()

                # Process backlog periodically
                check_count += 1
                current_time = time.time()
                if current_time - self.last_backlog_check > self.backlog_check_interval:
                    logger.debug("Checking backlog...")
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