"""
Movie scrobbler module for Media Player Scrobbler for SIMKL.
Handles movie detection and scrobbling to SIMKL.
"""

import logging
import logging.handlers
import time
import json
import os
import re
import requests
import pathlib
from datetime import datetime, timedelta
import threading
from collections import deque

from .simkl_api import mark_as_watched, is_internet_connected
from .backlog_cleaner import BacklogCleaner
from .window_detection import parse_movie_title, is_video_player
from .media_cache import MediaCache
from .utils.constants import PLAYING, PAUSED, STOPPED, DEFAULT_POLL_INTERVAL

logger = logging.getLogger(__name__)

class MovieScrobbler:
    """Handles the scrobbling of movies to SIMKL"""
    
    def __init__(self, app_data_dir, client_id=None, access_token=None, testing_mode=False):
        self.app_data_dir = app_data_dir
        self.client_id = client_id
        self.access_token = access_token
        self.testing_mode = testing_mode
        self.currently_tracking = None
        self.track_start_time = None
        self.last_progress = 0
        self.movie_cache = {}
        self.lock = threading.RLock()
        self.notification_callback = None
        
        self.playback_log_path = self.app_data_dir / "playback_log.jsonl"
        
        self.backlog_cleaner = BacklogCleaner(
            app_data_dir=self.app_data_dir, 
            backlog_file="backlog.json",
            threshold_days=30
        )
        
        self.recent_windows = deque(maxlen=10)

        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.state = STOPPED
        self.previous_state = STOPPED
        self.estimated_duration = None
        self.simkl_id = None
        self.movie_name = None
        self.last_scrobble_time = 0
        self.media_cache = MediaCache(app_data_dir=self.app_data_dir)
        self.last_progress_check = 0
        self.completion_threshold = 80
        self.completed = False
        self.current_position_seconds = 0
        self.total_duration_seconds = None
        self._last_connection_error_log = {}

        self.playback_log_file = self.app_data_dir / 'playback_log.jsonl'
        self.playback_logger = logging.getLogger('PlaybackLogger')
        self.playback_logger.propagate = False

        if not self.playback_logger.hasHandlers():
            self.playback_logger.setLevel(logging.INFO)
            formatter = logging.Formatter('{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}')
            try:
                handler = logging.handlers.RotatingFileHandler(
                    self.playback_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
                )
                handler.setFormatter(formatter)
                self.playback_logger.addHandler(handler)
                logger.info(f"Successfully configured PlaybackLogger handler for: {self.playback_log_file}")
            except Exception as e:
                logger.error(f"!!! Failed to create RotatingFileHandler for PlaybackLogger at {self.playback_log_file}: {e}", exc_info=True)

    def set_notification_callback(self, callback):
        """Set a callback function for notifications"""
        self.notification_callback = callback

    def _log_playback_event(self, event_type, extra_data=None):
        """Logs a structured playback event to the playback log file."""
        log_entry = {
            "event": event_type,
            "movie_title_raw": self.currently_tracking,
            "movie_name_simkl": self.movie_name,
            "simkl_id": self.simkl_id,
            "state": self.state,
            "watch_time_accumulated_seconds": round(self.watch_time, 2),
            "current_position_seconds": self.current_position_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "estimated_duration_seconds": self.estimated_duration,
            "completion_percent_accumulated": self._calculate_percentage(use_accumulated=True),
            "completion_percent_position": self._calculate_percentage(use_position=True),
            "is_complete_flag": self.completed,
        }
        if extra_data:
            log_entry.update(extra_data)

        try:
            self.playback_logger.info(json.dumps(log_entry))
        except Exception as e:
            logger.error(f"Failed to log playback event: {e} - Data: {log_entry}")

        if event_type == "scrobble_update" and self.notification_callback:
            self.notification_callback(
                "Scrobble Update",
                f"Movie: '{self.movie_name or self.currently_tracking}' (Duration: {self.estimated_duration // 60 if self.estimated_duration else 'Unknown'})\nID: {self.simkl_id or 'N/A'}"
            )

    def get_player_position_duration(self, process_name):
        """
        Get current position and total duration from supported media players via web interfaces.
        This method delegates to player-specific integration modules.
        
        Args:
            process_name (str): The executable name of the player process.
            
        Returns:
            tuple: (current_position_seconds, total_duration_seconds) or (None, None) if unavailable/unsupported.
        """
        position = None
        duration = None
        process_name_lower = process_name.lower() if process_name else ''
        
        try:
            if 'vlc' in process_name_lower:
                logger.debug(f"VLC detected: {process_name}")
                from simkl_mps.players import VLCIntegration
                
                if not hasattr(self, '_vlc_integration'):
                    self._vlc_integration = VLCIntegration()
                
                position, duration = self._vlc_integration.get_position_duration(process_name)
                
                if position is not None and duration is not None:
                    return position, duration
                else:
                    logger.debug("VLC integration couldn't get position/duration data")

            elif any(player in process_name_lower for player in ['mpc-hc.exe', 'mpc-hc64.exe', 'mpc-be.exe', 'mpc-be64.exe']):
                mpc_ports = [13579, 13580, 13581, 13582]
                for port in mpc_ports:
                    player_interface_url = f'http://localhost:{port}/variables.html'
                    try:
                        response = requests.get(player_interface_url, timeout=0.5)
                        if response.status_code == 200:
                            html_content = response.text
                            pos_match = re.search(r'<p id="position">(\d+)</p>', html_content)
                            dur_match = re.search(r'<p id="duration">(\d+)</p>', html_content)
                            file_match = re.search(r'<p id="file">(.*?)</p>', html_content)
                            
                            if file_match:
                                logger.debug(f"MPC is playing file: {file_match.group(1)}")
                            
                            if pos_match and dur_match:
                                position = int(pos_match.group(1)) / 1000.0
                                duration = int(dur_match.group(1)) / 1000.0
                                logger.info(f"Successfully connected to MPC web interface on port {port}")
                                logger.debug(f"Retrieved position data from MPC: position={position}s, duration={duration}s")
                                break
                            else:
                                logger.debug(f"MPC web interface on port {port} responded but position/duration not found")
                    except requests.RequestException:
                        logger.debug(f"MPC web interface not responding on port {port}")
                        continue
            
            elif any(player in process_name_lower for player in ['potplayer.exe', 'potplayermini.exe', 'potplayermini64.exe']):
                logger.debug(f"PotPlayer detected: {process_name}")
                from simkl_mps.players import PotPlayerIntegration
                
                if not hasattr(self, '_potplayer_integration'):
                    self._potplayer_integration = PotPlayerIntegration()
                
                position, duration = self._potplayer_integration.get_position_duration(process_name)
                
                if position is not None and duration is not None:
                    logger.debug(f"Retrieved position data from PotPlayer: position={position}s, duration={duration}s")
                    return position, duration
                else:
                    logger.debug("PotPlayer integration couldn't get position/duration data")

            elif 'mpv' in process_name_lower:
                logger.debug(f"MPV detection - socket communication not fully implemented yet")

            if position is not None and duration is not None:
                if isinstance(position, (int, float)) and isinstance(duration, (int, float)) and duration > 0 and position >= 0:
                    position = min(position, duration)
                    return round(position, 2), round(duration, 2)
                else:
                    logger.debug(f"Invalid position/duration data received from {process_name}: pos={position}, dur={duration}")
                    return None, None

        except requests.exceptions.RequestException as e:
            now = time.time()
            last_log_time = self._last_connection_error_log.get(process_name, 0)
            if now - last_log_time > 60:
                logger.warning(f"Could not connect to {process_name} web interface. Error: {str(e)}")
                self._last_connection_error_log[process_name] = now
        except Exception as e:
            logger.error(f"Error processing player ({process_name}) interface data: {e}")

        return None, None

    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token

    def process_window(self, window_info):
        """Process the current window and update scrobbling state"""
        if not is_video_player(window_info):
            if self.currently_tracking:
                logger.info(f"Media playback ended: Player closed or changed")
                self.stop_tracking()
            return None

        movie_title = parse_movie_title(window_info.get('title', ''))
        if not movie_title:
            if self.currently_tracking:
                 logger.debug(f"Unable to identify media in '{window_info.get('title', '')}'")
                 self.stop_tracking()
            return None

        if self.currently_tracking and self.currently_tracking != movie_title:
             logger.info(f"Media change detected: '{movie_title}' now playing")
             self.stop_tracking()
             
        if not self.currently_tracking:
            self._start_new_movie(movie_title)
            
        self._update_tracking(window_info)
        
        return {
            "title": movie_title,
            "simkl_id": self.simkl_id
        }

    def _start_new_movie(self, movie_title):
        """Start tracking a new movie"""
        logger.info(f"Starting media tracking: '{movie_title}'")
        self.currently_tracking = movie_title
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.watch_time = 0
        self.state = PLAYING
        self.simkl_id = None
        self.movie_name = None

    def _update_tracking(self, window_info=None):
        """Update tracking for the current movie, including position and duration if possible."""
        current_time = time.time()
        
        # Update watch time for active movie
        if self.state == PLAYING and self.last_update_time:
            elapsed = current_time - self.last_update_time
            if elapsed > 0 and elapsed < 30:  # Sanity check
                self.watch_time += elapsed
        
        self.last_update_time = current_time

        if not self.currently_tracking or not self.last_update_time:
            return None

        process_name = window_info.get('process_name') if window_info else None
        pos, dur = None, None
        if process_name:
            pos, dur = self.get_player_position_duration(process_name)

        position_updated = False
        if pos is not None and dur is not None and dur > 0:
             if self.total_duration_seconds is None or abs(self.total_duration_seconds - dur) > 1:
                 logger.info(f"Updating total duration from {self.total_duration_seconds}s to {dur}s based on player info.")
                 self.total_duration_seconds = dur
                 self.estimated_duration = dur

             time_diff = current_time - self.last_update_time
             if time_diff > 0.1 and self.state == PLAYING:
                 pos_diff = pos - self.current_position_seconds
                 if abs(pos_diff - time_diff) > 2.0:
                      logger.info(f"Seek detected: Position changed by {pos_diff:.1f}s in {time_diff:.1f}s (Expected ~{time_diff:.1f}s).")
                      self._log_playback_event("seek", {"previous_position_seconds": round(self.current_position_seconds, 2), "new_position_seconds": pos})

             self.current_position_seconds = pos
             position_updated = True

        if self._detect_pause(window_info):
            new_state = PAUSED
        else:
            new_state = PLAYING

        elapsed = current_time - self.last_update_time
        if elapsed < 0: elapsed = 0
        if elapsed > 60:
            logger.warning(f"Large time gap detected ({elapsed:.1f}s), capping at 10 seconds for accumulated time.")
            elapsed = 10

        if self.state == PLAYING:
            self.watch_time += elapsed

        state_changed = (new_state != self.state)
        if state_changed:
            logger.info(f"Playback state changed: {self.state} -> {new_state}")
            self.previous_state = self.state
            self.state = new_state
            self._log_playback_event("state_change", {"previous_state": self.previous_state})

        self.last_update_time = current_time

        percentage = self._calculate_percentage(use_position=position_updated)

        log_progress = state_changed or position_updated or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        if log_progress:
             self._log_playback_event("progress_update")

        if not self.completed and (current_time - self.last_progress_check > 5):
            completion_pct = self._calculate_percentage(use_position=position_updated)
            
            if completion_pct and completion_pct >= self.completion_threshold:
                 logger.info(f"Completion threshold ({self.completion_threshold}%) met for '{self.movie_name or self.currently_tracking}'")
                 self._log_playback_event("completion_threshold_reached")
                 
                 if self.simkl_id:
                     self.mark_as_watched(self.simkl_id, self.movie_name or self.currently_tracking)
                 else:
                     temp_id = f"temp_{self.currently_tracking}_{int(time.time())}"
                     logger.warning(f"No Simkl ID for '{self.currently_tracking}'. Adding to backlog with temp ID.")
                     self.backlog_cleaner.add(temp_id, self.currently_tracking)
                     self.completed = True
            
            self.last_progress_check = current_time 

        should_scrobble = state_changed or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        if should_scrobble:
            self.last_scrobble_time = current_time
            self._log_playback_event("scrobble_update")
            return {
                "title": self.currently_tracking,
                "movie_name": self.movie_name,
                "simkl_id": self.simkl_id,
                "state": self.state,
                "progress": percentage,
                "watched_seconds": round(self.watch_time, 2),
                "current_position_seconds": self.current_position_seconds,
                "total_duration_seconds": self.total_duration_seconds,
                "estimated_duration_seconds": self.estimated_duration
            }

        if is_internet_connected():
            self._reset_no_internet_log()

        return None

    def _calculate_percentage(self, use_position=False, use_accumulated=False):
        """Calculates completion percentage. Prefers position/duration if use_position is True and data is valid."""
        percentage = None
        if use_position and self.current_position_seconds is not None and self.total_duration_seconds is not None and self.total_duration_seconds > 0:
            percentage = min(100, (self.current_position_seconds / self.total_duration_seconds) * 100)
        elif (use_accumulated or not use_position) and self.total_duration_seconds is not None and self.total_duration_seconds > 0:
             percentage = min(100, (self.watch_time / self.total_duration_seconds) * 100)

        return percentage

    def _detect_pause(self, window_info):
        """Detect if playback is paused based on window title."""
        if window_info and window_info.get('title'):
            title_lower = window_info['title'].lower()
            if "paused" in title_lower:
                return True
        return False

    def stop_tracking(self):
        """Stop tracking the current movie"""
        if not self.currently_tracking:
            return

        final_state = self.state
        final_pos = self.current_position_seconds
        final_watch_time = self.watch_time
        if self.is_complete():
             logger.info(f"Tracking stopped for '{self.movie_name or self.currently_tracking}' after completion threshold was met.")

        final_scrobble_info = {
            "title": self.currently_tracking,
            "movie_name": self.movie_name,
            "simkl_id": self.simkl_id,
            "state": STOPPED,
            "progress": self._calculate_percentage(use_position=True) or self._calculate_percentage(use_accumulated=True),
            "watched_seconds": round(final_watch_time, 2),
            "current_position_seconds": final_pos,
            "total_duration_seconds": self.total_duration_seconds,
            "estimated_duration_seconds": self.estimated_duration
            }

        self._log_playback_event("stop_tracking", extra_data={"final_state": final_state, "final_position": final_pos, "final_watch_time": final_watch_time})

        logger.debug(f"Resetting tracking state for {self.currently_tracking}")
        self.currently_tracking = None
        self.state = STOPPED
        self.previous_state = self.state
        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.current_position_seconds = 0
        self.total_duration_seconds = None
        self.estimated_duration = None
        self.simkl_id = None
        self.movie_name = None
        self.completed = False

        return final_scrobble_info

    def mark_as_watched(self, simkl_id, title, movie_name=None):
        """
        Mark a movie as watched on SIMKL or add to backlog if offline.
        Sets self.completed on success. Can be called either automatically when 
        completion threshold is reached, or manually.
        
        Args:
            simkl_id: The Simkl ID for the movie
            title: Movie title (raw title or window title)
            movie_name: Official movie name from Simkl (optional)
        
        Returns:
            bool: True if successfully marked as watched, False otherwise
        """
        display_title = movie_name or title
        
        if self.testing_mode:
            logger.info(f"TEST MODE: Simulating marking '{display_title}' (ID: {simkl_id}) as watched")
            self.completed = True
            self._log_playback_event("marked_as_watched_test_mode")
            
            if self.notification_callback:
                self.notification_callback(
                    "Movie Marked as Watched (Test Mode)", 
                    f"'{display_title}' was marked as watched (test mode)"
                )
            return True

        if not self.client_id or not self.access_token:
            logger.error("Cannot mark movie as watched: missing API credentials")
            self._log_playback_event("marked_as_watched_fail_credentials")
            logger.info(f"Adding '{display_title}' (ID: {simkl_id}) to backlog due to missing credentials")
            self.backlog_cleaner.add(simkl_id, title)
            
            if self.notification_callback:
                self.notification_callback(
                    "Authentication Error", 
                    f"Could not mark '{display_title}' as watched - missing credentials"
                )
            return False

        try:
            if not is_internet_connected():
                logger.warning(f"System appears to be offline. Adding '{display_title}' (ID: {simkl_id}) to backlog for future syncing")
                self._log_playback_event("marked_as_watched_offline")
                self.backlog_cleaner.add(simkl_id, title)
                
                if self.notification_callback:
                    self.notification_callback(
                        "Added to Offline Queue", 
                        f"'{display_title}' will be marked as watched when back online"
                    )
                return False
            
            result = mark_as_watched(simkl_id, self.client_id, self.access_token)
            if result:
                logger.info(f"Successfully marked '{display_title}' as watched on Simkl")
                self.completed = True
                self._log_playback_event("marked_as_watched_api_success")
                
                if self.notification_callback:
                    self.notification_callback(
                        "Movie Marked as Watched", 
                        f"'{display_title}' was successfully marked as watched on Simkl"
                    )
                return True
            else:
                logger.warning(f"Failed to mark '{display_title}' as watched, adding to backlog")
                self._log_playback_event("marked_as_watched_api_fail")
                self.backlog_cleaner.add(simkl_id, title)
                
                if self.notification_callback:
                    self.notification_callback(
                        "Marking Failed", 
                        f"Failed to mark '{display_title}' as watched, added to backlog for retry"
                    )
                return False
        except Exception as e:
            logger.error(f"Error marking movie as watched: {e}")
            self._log_playback_event("marked_as_watched_api_error", {"error": str(e)})
            logger.info(f"Adding '{display_title}' (ID: {simkl_id}) to backlog due to error: {e}")
            self.backlog_cleaner.add(simkl_id, title)
            
            if self.notification_callback:
                self.notification_callback(
                    "Error", 
                    f"Error marking '{display_title}' as watched: {e}"
                )
            return False

    def process_backlog(self):
        """Process pending backlog items, resolving temp IDs if needed."""
        if not self.client_id or not self.access_token:
            logger.warning("[Offline Sync] Missing credentials, cannot process backlog.")
            return 0
            
        from simkl_mps.simkl_api import mark_as_watched, search_movie, is_internet_connected
        
        if not is_internet_connected():
            logger.info("[Offline Sync] No internet connection. Backlog sync deferred.")
            return 0
            
        success_count = 0
        pending = self.backlog_cleaner.get_pending()
        
        if not pending:
            logger.info("[Offline Sync] No backlog entries to sync.")
            return 0
            
        logger.info(f"[Offline Sync] Processing {len(pending)} backlog entries...")
        items_to_process = list(pending)
        
        for item in items_to_process:
            simkl_id = item.get("simkl_id")
            title = item.get("title", "Unknown")
            
            if simkl_id and isinstance(simkl_id, str) and simkl_id.startswith("temp_"):
                logger.info(f"[Offline Sync] Resolving temp ID for '{title}'...")
                movie_result = search_movie(title, self.client_id, self.access_token)
                real_simkl_id = None
                
                if movie_result:
                    if 'movie' in movie_result and 'ids' in movie_result['movie']:
                        ids = movie_result['movie']['ids']
                        real_simkl_id = ids.get('simkl') or ids.get('simkl_id')
                    elif 'ids' in movie_result:
                        ids = movie_result['ids']
                        real_simkl_id = ids.get('simkl') or ids.get('simkl_id')
                        
                if real_simkl_id:
                    logger.info(f"[Offline Sync] Resolved '{title}' to Simkl ID {real_simkl_id}. Marking as watched...")
                    result = mark_as_watched(real_simkl_id, self.client_id, self.access_token)
                    if result:
                        logger.info(f"[Offline Sync] Successfully marked '{title}' as watched on Simkl.")
                        self.backlog_cleaner.remove(simkl_id)
                        success_count += 1
                    else:
                        logger.warning(f"[Offline Sync] Failed to mark '{title}' as watched. Will retry.")
                else:
                    logger.warning(f"[Offline Sync] Could not resolve Simkl ID for '{title}'. Will retry.")
            elif simkl_id:
                logger.info(f"[Offline Sync] Syncing '{title}' (ID: {simkl_id}) to Simkl...")
                result = mark_as_watched(simkl_id, self.client_id, self.access_token)
                if result:
                    logger.info(f"[Offline Sync] Successfully marked '{title}' as watched on Simkl.")
                    self.backlog_cleaner.remove(simkl_id)
                    success_count += 1
                else:
                    logger.warning(f"[Offline Sync] Failed to mark '{title}' as watched. Will retry.")
            else:
                logger.warning(f"[Offline Sync] Invalid backlog entry: {item}")
                
        if success_count > 0:
            logger.info(f"[Offline Sync] Backlog sync complete. {success_count} entries synced.")
        else:
            logger.info("[Offline Sync] No entries were synced this cycle.")
            
        return success_count

    def start_offline_sync_thread(self, interval_seconds=120):
        """Start a background thread to periodically sync backlog when online."""
        if hasattr(self, '_offline_sync_thread') and self._offline_sync_thread.is_alive():
            return
            
        import threading
        
        def sync_loop():
            while True:
                try:
                    if is_internet_connected():
                        logger.info("[Offline Sync] Internet detected. Processing backlog...")
                        synced = self.process_backlog()
                        if synced > 0:
                            logger.info(f"[Offline Sync] Synced {synced} backlog entries to Simkl.")
                    else:
                        logger.debug("[Offline Sync] Still offline. Will retry later.")
                except Exception as e:
                    logger.error(f"[Offline Sync] Error during backlog sync: {e}")
                time.sleep(interval_seconds)
                
        self._offline_sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._offline_sync_thread.start()

    def cache_movie_info(self, title, simkl_id, movie_name, runtime=None):
        """
        Cache movie info to avoid repeated searches. Prioritizes known duration.

        Args:
            title: Original movie title from window
            simkl_id: Simkl ID of the movie
            movie_name: Official movie name from Simkl
            runtime: Movie runtime in minutes from Simkl API (optional)
        """
        if title and simkl_id:
            cached_data = {
                "simkl_id": simkl_id,
                "movie_name": movie_name
            }

            api_duration_seconds = None
            if runtime:
                api_duration_seconds = runtime * 60

            current_cached_info = self.media_cache.get(title)
            existing_cached_duration = current_cached_info.get("duration_seconds") if current_cached_info else None

            duration_to_cache = self.total_duration_seconds if self.total_duration_seconds is not None else api_duration_seconds
            if duration_to_cache is None:
                duration_to_cache = existing_cached_duration

            if duration_to_cache:
                cached_data["duration_seconds"] = duration_to_cache
                logger.info(f"Caching duration information: {duration_to_cache} seconds for '{movie_name}'")
            else:
                logger.info(f"No duration information available to cache for '{movie_name}'")

            self.media_cache.set(title, cached_data)

            if self.currently_tracking == title:
                is_new_identification = self.simkl_id != simkl_id or self.movie_name != movie_name
                
                self.simkl_id = simkl_id
                self.movie_name = movie_name

                if is_new_identification and self.notification_callback:
                    self.notification_callback(
                        "Movie Identified", 
                        f"Playing: '{movie_name}'\nSimkl ID: {simkl_id}"
                    )

                if duration_to_cache is not None and self.total_duration_seconds != duration_to_cache:
                     if self.total_duration_seconds is None:
                          logger.info(f"Updating known duration from None to {duration_to_cache}s based on cache/API info")
                          self.total_duration_seconds = duration_to_cache
                          self.estimated_duration = duration_to_cache

    def is_complete(self, threshold=None):
        """Check if the movie is considered watched (default: based on instance threshold), prioritizing position."""
        if not self.currently_tracking:
            return False

        if self.completed:
            return True

        if threshold is None:
            threshold = self.completion_threshold

        percentage = self._calculate_percentage(use_position=True)
        if percentage is None:
             percentage = self._calculate_percentage(use_accumulated=True)

        if percentage is None:
            return False

        is_past_threshold = percentage >= threshold

        return is_past_threshold

    def _log_no_internet_once(self, context):
        """Log a warning about no internet only once per context until connection is restored."""
        if not hasattr(self, '_no_internet_logged'):
            self._no_internet_logged = {}
        if not self._no_internet_logged.get(context, False):
            logger.warning(f"No internet connection. {context}")
            self._no_internet_logged[context] = True

    def _reset_no_internet_log(self):
        if hasattr(self, '_no_internet_logged'):
            self._no_internet_logged = {}