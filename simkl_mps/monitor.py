"""
Monitor module for Media Player Scrobbler for SIMKL.
Handles continuous window monitoring and scrobbling.
"""

import time
import logging
import threading
import platform
from datetime import datetime

from .window_detection import (
    get_active_window_info, 
    get_all_windows_info,
    is_video_player
)
from simkl_mps.movie_scrobbler import MovieScrobbler

logger = logging.getLogger(__name__)

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
        self._lock = threading.RLock()
        self.scrobbler = MovieScrobbler(
            app_data_dir=self.app_data_dir,
            client_id=self.client_id,
            access_token=self.access_token,
            testing_mode=self.testing_mode
        )
        self.last_backlog_check = 0
        self.backlog_check_interval = backlog_check_interval
        self.search_callback = None
        # Add a dictionary to track when we last searched for each title
        self._last_search_attempts = {}
        # Search cooldown period when offline (60 seconds)
        self.offline_search_cooldown = 60

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
            try:
                self.monitor_thread.join(timeout=2)
            except RuntimeError:
                logger.warning("Could not join monitor thread")
        
        with self._lock:
            if self.scrobbler.currently_tracking:
                self.scrobbler.stop_tracking()
        
        logger.info("Monitor stopped")
        return True

    def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Media monitoring service initialized and running")
        # Removed unused check_count variable

        while self.running:
            try:
                found_player = False
                all_windows = get_all_windows_info()
                
                for win in all_windows:
                    if is_video_player(win):
                        window_info = win
                        found_player = True
                        logger.debug(f"Active media player detected: {win.get('title', 'Unknown')}")
                        
                        with self._lock:
                            scrobble_info = self.scrobbler.process_window(window_info)
                        
                        if scrobble_info and self.search_callback and not scrobble_info.get("simkl_id"):
                            title = scrobble_info.get("title", "Unknown")
                            current_time = time.time()
                            
                            # Check if we've recently tried to search for this title
                            last_attempt = self._last_search_attempts.get(title, 0)
                            time_since_last_attempt = current_time - last_attempt
                            
                            # Only attempt search if it hasn't been tried recently during offline mode
                            if time_since_last_attempt >= self.offline_search_cooldown:
                                logger.info(f"Media identification required: '{title}'")
                                # Record this attempt time before calling search
                                self._last_search_attempts[title] = current_time
                                self.search_callback(title)
                            else:
                                # If in cooldown period, don't spam logs with the same message
                                logger.debug(f"Skipping repeated search for '{title}' (cooldown: {int(self.offline_search_cooldown - time_since_last_attempt)}s remaining)")
                        
                        break
                
                if not found_player and self.scrobbler.currently_tracking:
                    logger.info("Media playback ended: No active players detected")
                    with self._lock:
                        self.scrobbler.stop_tracking()

                # check_count was incremented here but removed as unused
                current_time = time.time()
                if current_time - self.last_backlog_check > self.backlog_check_interval:
                    logger.debug("Performing backlog synchronization...")
                    with self._lock:
                        synced_count = self.scrobbler.process_backlog()
                    
                    if synced_count > 0:
                        logger.info(f"Backlog sync completed: {synced_count} items successfully synchronized")
                    self.last_backlog_check = current_time

                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Monitoring service encountered an error: {e}", exc_info=True)
                time.sleep(max(5, self.poll_interval))

        logger.info("Media monitoring service stopped")

    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token
        self.scrobbler.set_credentials(client_id, access_token)

    def cache_movie_info(self, title, simkl_id, movie_name, runtime=None):
        """Cache movie info to avoid repeated searches"""
        self.scrobbler.cache_movie_info(title, simkl_id, movie_name, runtime)