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
from simkl_mps.media_scrobbler import MediaScrobbler # Updated import

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
        self.scrobbler = MediaScrobbler( # Updated instantiation
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
        # Debug field to track cycles without detection
        self._debug_cycles = 0
        # State tracking for logging verbosity
        self.last_known_player_process = None
        self.last_known_filepath = None
 
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
        
        # Dictionary to track the last processed title for each player to reduce log spam
        last_processed_titles = {}

        while self.running:
            try:
                found_player = False
                all_windows = get_all_windows_info()
                
                # Debug counter
                self._debug_cycles += 1
                if self._debug_cycles % 3 == 0:  # Log every 3rd cycle to avoid spam
                    logger.debug(f"Monitor loop cycle: {self._debug_cycles}, Found {len(all_windows)} windows")
                    
                for win in all_windows:
                    if is_video_player(win):
                        window_info = win
                        process_name = win.get('process_name', '')
                        found_player = True
                        
                        # Log only if the player process is new or changed
                        if process_name != self.last_known_player_process:
                            logger.info(f"Found video player: {process_name} - '{win.get('title', 'Unknown')}'")
                        
                        # Check if we can get filepath directly from the player
                        filepath = self.scrobbler.get_current_filepath(process_name)
                        
                        # Log only if filepath is available AND (filepath changed OR player changed)
                        if filepath and (filepath != self.last_known_filepath or process_name != self.last_known_player_process):
                            logger.info(f"Retrieved filepath from player: {filepath}")
                        elif not filepath and self.last_known_filepath is not None and process_name == self.last_known_player_process:
                            # Log if filepath becomes unavailable for the *same* player (but only if we previously had one)
                            logger.info(f"Filepath no longer available from {process_name}")
                        
                        with self._lock:
                            scrobble_info = self.scrobbler.process_window(window_info)
                        
                        # Check if we got a result and if it's different from the last one for this player
                        if scrobble_info:
                            title = scrobble_info.get("title", "Unknown")
                            source = scrobble_info.get("source", "unknown")
                            
                            # Only log once when we first detect the media or if it changes
                            if process_name not in last_processed_titles or last_processed_titles[process_name] != title:
                                last_processed_titles[process_name] = title
                                logger.debug(f"Active media player detected: {win.get('title', 'Unknown')}")
                                logger.info(f"Detected media '{title}' using {source}")
                            
                            # REMOVED: Redundant search trigger. Scrobbler handles identification internally.
                            # if self.search_callback and not scrobble_info.get("simkl_id"):
                            #     current_time = time.time()
                            #     last_attempt = self._last_search_attempts.get(title, 0)
                            #     time_since_last_attempt = current_time - last_attempt
                            #     if time_since_last_attempt >= self.offline_search_cooldown:
                            #         logger.info(f"Media identification required: '{title}'")
                            #         self._last_search_attempts[title] = current_time
                            #         self.search_callback(title)
                            #     else:
                            #         logger.debug(f"Skipping repeated search for '{title}' (cooldown: {int(self.offline_search_cooldown - time_since_last_attempt)}s remaining)")
                        else:
                            logger.warning(f"No scrobble info returned from process_window for {process_name}")
                        # Update the persistent state *after* processing and logging checks
                        self.last_known_player_process = process_name
                        self.last_known_filepath = filepath
                        break # Found and processed a player, move to next cycle
                
                # Check if player stopped since last cycle
                if not found_player and self.last_known_player_process is not None:
                    logger.info(f"Media playback ended or player '{self.last_known_player_process}' closed.")
                    with self._lock:
                        if self.scrobbler.currently_tracking: # Ensure we only stop if tracking
                            self.scrobbler.stop_tracking()
                        last_processed_titles.clear()  # Clear the processed titles when stopping
                    # Reset persistent state as no player is active now
                    self.last_known_player_process = None
                    self.last_known_filepath = None
                elif not found_player and self._debug_cycles % 10 == 0:
                    # Periodically log if we're not finding any players
                    logger.debug(f"No video players detected (cycle {self._debug_cycles})")

                # Check backlog periodically
                current_time = time.time()
                if current_time - self.last_backlog_check > self.backlog_check_interval:
                    logger.debug("Performing backlog synchronization...")
                    try:
                        with self._lock:
                            synced_result = self.scrobbler.process_backlog()
                        
                        # Handle both int and dict return types for backward compatibility
                        if isinstance(synced_result, dict):
                            # If it's a dictionary, extract the count from it
                            count_value = synced_result.get('count', 0)
                            if count_value > 0:
                                logger.info(f"Backlog sync completed: {count_value} items successfully synchronized")
                        elif isinstance(synced_result, int) and synced_result > 0:
                            # Legacy behavior - synced_result is an integer
                            logger.info(f"Backlog sync completed: {synced_result} items successfully synchronized")
                    except TypeError as e:
                        logger.error(f"[Offline Sync] Error processing backlog result: {e}", exc_info=True)
                    except Exception as e:
                        logger.error(f"[Offline Sync] Error during backlog sync: {e}", exc_info=True)
                    
                    # Always update the last check time even if there was an error
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

    def cache_media_info(self, title, simkl_id, display_name, media_type='movie', season=None, episode=None, year=None, runtime=None):
        """Cache media info to avoid repeated searches for any media type"""
        logger.info(f"Caching media info for '{title}': ID={simkl_id}, Display='{display_name}', Type={media_type}" +
                   (f", Season={season}" if season is not None else "") +
                   (f", Episode={episode}" if episode is not None else ""))
        self.scrobbler.cache_media_info(title, simkl_id, display_name, media_type, season, episode, year, runtime)
        
    def cache_movie_info(self, title, simkl_id, movie_name, runtime=None):
        """Legacy method for backward compatibility, delegates to cache_media_info"""
        logger.debug(f"Using legacy cache_movie_info method for '{movie_name}'")
        self.cache_media_info(title, simkl_id, movie_name, 'movie', runtime=runtime)