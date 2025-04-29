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

# Import is_internet_connected at the top level for broader use
from simkl_mps.simkl_api import mark_as_watched, is_internet_connected, get_movie_details
from simkl_mps.backlog_cleaner import BacklogCleaner
from simkl_mps.window_detection import parse_movie_title, parse_filename_from_path, is_video_player
from simkl_mps.media_cache import MediaCache
from simkl_mps.utils.constants import PLAYING, PAUSED, STOPPED, DEFAULT_POLL_INTERVAL
from simkl_mps.config_manager import get_setting, DEFAULT_THRESHOLD # Import settings functions
from simkl_mps.watch_history_manager import WatchHistoryManager # Import WatchHistoryManager

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
        # self.last_progress = 0 # Unused attribute removed
        # self.movie_cache = {} # Unused attribute removed (using self.media_cache instead)
        # self.lock = threading.RLock() # Unused lock removed
        self.notification_callback = None

        self.playback_log_path = self.app_data_dir / "playback_log.jsonl"

        self.backlog_cleaner = BacklogCleaner(
            app_data_dir=self.app_data_dir,
            backlog_file="backlog.json" # threshold_days removed in backlog_cleaner.py
        )

        # self.recent_windows = deque(maxlen=10) # Unused attribute removed

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
        self.completion_threshold = get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        self.completed = False
        self.current_position_seconds = 0
        self.total_duration_seconds = None
        self.current_filepath = None # Added to store the last known filepath
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

    def _send_notification(self, title, message, online_only=False, offline_only=False):
        """
        Safely sends a notification if the callback is set, respecting online/offline constraints.
        Note: Delays in notification display might originate from the callback implementation
        itself or the OS notification system, not this method.
        """
        if self.notification_callback:
            should_send = True
            if online_only and not is_internet_connected():
                should_send = False
                logger.debug(f"Notification '{title}' suppressed (Online only).")
            elif offline_only and is_internet_connected():
                should_send = False
                logger.debug(f"Notification '{title}' suppressed (Offline only).")

            if should_send:
                try:
                    # Call the actual notification function provided externally
                    self.notification_callback(title, message)
                    logger.debug(f"Sent notification: '{title}'")
                except Exception as e:
                    logger.error(f"Failed to send notification '{title}': {e}", exc_info=True)

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

        # REMOVED: Periodic "Scrobble Update" notification was here.
        # Logging is sufficient for progress tracking. Notifications focus on key events.

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

            # --- MPC-HC/BE Integration ---
            elif any(player in process_name_lower for player in ['mpc-hc.exe', 'mpc-hc64.exe', 'mpc-be.exe', 'mpc-be64.exe']):
                logger.debug(f"MPC-HC/BE detected: {process_name}")
                from simkl_mps.players.mpc import MPCIntegration # Import the new class

                # Lazily instantiate the integration helper
                if not hasattr(self, '_mpc_integration'):
                    self._mpc_integration = MPCIntegration()

                position, duration = self._mpc_integration.get_position_duration(process_name)

                if position is not None and duration is not None:
                    logger.debug(f"Retrieved position data from MPC: position={position}s, duration={duration}s")
                    # Return directly if successful
                    return position, duration
                else:
                    logger.debug("MPC integration couldn't get position/duration data")
            # --- End MPC-HC/BE Integration ---
            
            # --- MPC-QT Integration ---
            elif 'mpc-qt' in process_name_lower:
                logger.debug(f"MPC-QT detected: {process_name}")
                from simkl_mps.players.mpcqt import MPCQTIntegration
                
                # Lazily instantiate the MPC-QT integration
                if not hasattr(self, '_mpcqt_integration'):
                    self._mpcqt_integration = MPCQTIntegration()
                
                position, duration = self._mpcqt_integration.get_position_duration(process_name)
                
                if position is not None and duration is not None:
                    logger.debug(f"Retrieved position data from MPC-QT: position={position}s, duration={duration}s")
                    # Return directly if successful
                    return position, duration
                else:
                    logger.debug("MPC-QT integration couldn't get position/duration data")
            # --- End MPC-QT Integration ---

            # --- MPV Integration ---
            elif 'mpv' in process_name_lower:
                logger.debug(f"MPV detected: {process_name}")
                from simkl_mps.players.mpv import MPVIntegration # Import the new class

                # Lazily instantiate the MPV integration
                if not hasattr(self, '_mpv_integration'):
                    self._mpv_integration = MPVIntegration()

                position, duration = self._mpv_integration.get_position_duration(process_name)

                if position is not None and duration is not None:
                    logger.debug(f"Retrieved position data from MPV: position={position}s, duration={duration}s")
                    # Return directly if successful
                    return position, duration 
                else:
                    logger.debug("MPV integration couldn't get position/duration data")
            # --- End MPV Integration ---
            
            # --- MPV Wrapper Integration (Celluloid, MPV.net, SMPlayer, etc.) ---
            else:
                # Try to detect MPV wrapper players (need to check this explicitly since they 
                # may not have 'mpv' in the process name)
                from simkl_mps.players.mpv_wrappers import MPVWrapperIntegration
                
                # Lazily instantiate the MPV wrapper integration
                if not hasattr(self, '_mpv_wrapper_integration'):
                    self._mpv_wrapper_integration = MPVWrapperIntegration()
                
                # Check if this is a known MPV wrapper
                if self._mpv_wrapper_integration.is_mpv_wrapper(process_name):
                    logger.debug(f"MPV wrapper player detected: {process_name}")
                    
                    # Get wrapper details for better logging
                    _, wrapper_name, _ = self._mpv_wrapper_integration.get_wrapper_info(process_name)
                    wrapper_display = wrapper_name or process_name
                    
                    position, duration = self._mpv_wrapper_integration.get_position_duration(process_name)
                    
                    if position is not None and duration is not None:
                        logger.debug(f"Retrieved position data from {wrapper_display}: position={position}s, duration={duration}s")
                        # Return directly if successful
                        return position, duration
                    else:
                        logger.debug(f"{wrapper_display} integration couldn't get position/duration data")
            # --- End MPV Wrapper Integration ---

            # General validation (redundant for MPV, kept for safety/other players)
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

    def get_current_filepath(self, process_name):
        """
        Get the current filepath of the media being played from player integrations.
        This is the preferred source for movie identification.
        
        Args:
            process_name (str): The executable name of the player process
            
        Returns:
            str: Full file path of the currently playing media, or None if unavailable
        """
        if not process_name:
            return None
            
        process_name_lower = process_name.lower()
        filepath = None
        
        try:
            # VLC Integration
            if 'vlc' in process_name_lower:
                if not hasattr(self, '_vlc_integration'):
                    from simkl_mps.players import VLCIntegration
                    self._vlc_integration = VLCIntegration()
                    
                # Call get_current_filepath if the integration has it
                if hasattr(self._vlc_integration, 'get_current_filepath'):
                    filepath = self._vlc_integration.get_current_filepath(process_name)
                    if filepath:
                        logger.debug(f"Retrieved filepath from VLC: {filepath}")
                        return filepath
            
            # MPC-HC/BE Integration
            elif any(player in process_name_lower for player in ['mpc-hc.exe', 'mpc-hc64.exe', 'mpc-be.exe', 'mpc-be64.exe']):
                if not hasattr(self, '_mpc_integration'):
                    from simkl_mps.players.mpc import MPCIntegration
                    self._mpc_integration = MPCIntegration()
                    
                # Call get_current_filepath if the integration has it
                if hasattr(self._mpc_integration, 'get_current_filepath'):
                    filepath = self._mpc_integration.get_current_filepath(process_name)
                    if filepath:
                        logger.debug(f"Retrieved filepath from MPC: {filepath}")
                        return filepath
            
            # MPC-QT Integration
            elif 'mpc-qt' in process_name_lower:
                if not hasattr(self, '_mpcqt_integration'):
                    from simkl_mps.players.mpcqt import MPCQTIntegration
                    self._mpcqt_integration = MPCQTIntegration()
                    
                # Call get_current_filepath if the integration has it
                if hasattr(self._mpcqt_integration, 'get_current_filepath'):
                    filepath = self._mpcqt_integration.get_current_filepath(process_name)
                    if filepath:
                        logger.debug(f"Retrieved filepath from MPC-QT: {filepath}")
                        return filepath
            
            # MPV Integration
            elif 'mpv' in process_name_lower:
                if not hasattr(self, '_mpv_integration'):
                    from simkl_mps.players.mpv import MPVIntegration
                    self._mpv_integration = MPVIntegration()
                    
                # Call get_current_filepath if the integration has it
                if hasattr(self._mpv_integration, 'get_current_filepath'):
                    filepath = self._mpv_integration.get_current_filepath(process_name)
                    if filepath:
                        logger.debug(f"Retrieved filepath from MPV: {filepath}")
                        return filepath
            
            # MPV Wrapper Integration
            else:
                if not hasattr(self, '_mpv_wrapper_integration'):
                    from simkl_mps.players.mpv_wrappers import MPVWrapperIntegration
                    self._mpv_wrapper_integration = MPVWrapperIntegration()
                    
                # Check if this is a known MPV wrapper
                if self._mpv_wrapper_integration.is_mpv_wrapper(process_name):
                    # Call get_current_filepath if the integration has it
                    if hasattr(self._mpv_wrapper_integration, 'get_current_filepath'):
                        filepath = self._mpv_wrapper_integration.get_current_filepath(process_name)
                        if filepath:
                            _, wrapper_name, _ = self._mpv_wrapper_integration.get_wrapper_info(process_name)
                            wrapper_display = wrapper_name or process_name
                            logger.debug(f"Retrieved filepath from {wrapper_display}: {filepath}")
                            return filepath
                            
        except Exception as e:
            logger.error(f"Error getting filepath from {process_name}: {e}")
            
        return filepath

    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token

    def process_window(self, window_info):
        """Process the current window and update scrobbling state"""
        # Store the window info for later use when retrieving file paths
        self._last_window_info = window_info
        
        if not is_video_player(window_info):
            if self.currently_tracking:
                logger.info(f"Media playback ended: Player closed or changed")
                self.stop_tracking()
            return None
        
        # First try to get the filepath directly from the player (preferred method)
        process_name = window_info.get('process_name')
        filepath = None
        movie_title = None
        detection_source = "unknown"
        detection_details = None
        
        if process_name:
            # Try to get the current filepath from player integration
            filepath = self.get_current_filepath(process_name)
            
            if filepath:
                # Parse the filename from the filepath using our dedicated function
                movie_title = parse_filename_from_path(filepath)
                if movie_title:
                    detection_source = "filename"
                    detection_details = os.path.basename(filepath)
        
        # If no filepath was available or parsing failed, fall back to window title
        if not movie_title:
            movie_title = parse_movie_title(window_info.get('title', ''))
            if movie_title:
                detection_source = "window_title"
                detection_details = window_info.get('title', '')
        
        # If we still don't have a title, stop tracking and return
        if not movie_title:
            if self.currently_tracking:
                logger.debug(f"Unable to identify media in '{window_info.get('title', '')}'")
                self.stop_tracking()
            return None

        # If we're already tracking a different movie, stop tracking before starting the new one
        if self.currently_tracking and self.currently_tracking != movie_title:
            logger.info(f"Media change detected: '{movie_title}' now playing")
            self.stop_tracking()
             
        # Start tracking the movie if not already tracking
        if not self.currently_tracking:
            # Only log the detection source when we first start tracking
            if detection_source == "filename":
                logger.info(f"Detected movie from filename: '{movie_title}' (from: {detection_details})")
            elif detection_source == "window_title":
                logger.info(f"Detected movie from window title: '{movie_title}'")
            self._start_new_movie(movie_title)
        
        # Update tracking with current window info
        track_info = self._update_tracking(window_info)
        
        return {
            "title": movie_title,
            "simkl_id": self.simkl_id,
            "source": detection_source,
            "detection_details": detection_details
        }

    def _start_new_movie(self, movie_title):
        """Start tracking a new movie"""
        # Additional validation to make sure we don't track generic titles
        if not movie_title or movie_title.lower() in ["audio", "video", "media", "no file"]:
            logger.info(f"Ignoring generic title for tracking: '{movie_title}'")
            return

        logger.info(f"Starting media tracking: '{movie_title}'")
        self.currently_tracking = movie_title
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.watch_time = 0
        self.state = PLAYING
        self.simkl_id = None
        self.movie_name = None
        self.current_filepath = None # Reset filepath on new movie

        # Notify user that tracking has started (Offline Only)
        self._send_notification(
            "Tracking Started",
            f"Started tracking: '{movie_title}'",
            offline_only=True
        )

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
            # Attempt to get position/duration
            pos, dur = self.get_player_position_duration(process_name)
            # Attempt to get and store the filepath on each update
            try:
                filepath = self.get_current_filepath(process_name)
                if filepath:
                    if self.current_filepath != filepath:
                         logger.debug(f"Updated current filepath to: {filepath}")
                         self.current_filepath = filepath
                # else: # Don't clear if not found, keep the last known good one
                #     self.current_filepath = None
            except Exception as e:
                 logger.error(f"Error getting filepath during update: {e}", exc_info=False) # Log less verbosely

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

        # Check for completion threshold every 5 seconds if not already marked complete
        if not self.completed and (current_time - self.last_progress_check > 5):
            completion_pct = self._calculate_percentage(use_position=position_updated)

            if completion_pct and completion_pct >= self.completion_threshold:
                 logger.info(f"Completion threshold ({self.completion_threshold}%) met for '{self.movie_name or self.currently_tracking}'")
                 self._log_playback_event("completion_threshold_reached")

                 # Send notification exactly once when threshold is first met (Offline Only)
                 # Do this *before* attempting to mark as watched
                 self._send_notification(
                     f"Completion Threshold Reached ({self.completion_threshold}%)",
                     f"Movie: '{self.movie_name or self.currently_tracking}'",
                     offline_only=True # Only notify locally if offline when threshold is hit
                 )

                 # Only attempt to mark as watched if we have the Simkl ID
                 if self.simkl_id:
                     logger.info(f"Attempting to mark '{self.movie_name or self.currently_tracking}' (ID: {self.simkl_id}) as watched...")
                     # mark_as_watched handles API call, backlog addition on failure/offline, and sets self.completed
                     self.mark_as_watched(self.simkl_id, self.currently_tracking, self.movie_name)
                 else:
                     # Check if we can get the ID from our cache
                     cached_info = self.media_cache.get(self.currently_tracking)
                     if cached_info and cached_info.get('simkl_id'):
                         cached_simkl_id = cached_info.get('simkl_id')
                         cached_movie_name = cached_info.get('movie_name')
                         logger.info(f"Found Simkl ID {cached_simkl_id} for '{self.currently_tracking}' in cache")
                         
                         # Update the current tracking with the cached info
                         self.simkl_id = cached_simkl_id
                         if cached_movie_name:
                             self.movie_name = cached_movie_name
                             
                         # Now try to mark as watched with the cached ID
                         logger.info(f"Attempting to mark '{self.movie_name or self.currently_tracking}' (ID: {self.simkl_id}) as watched using cached ID...")
                         self.mark_as_watched(self.simkl_id, self.currently_tracking, self.movie_name)
                     else:
                         # If no cached ID and no internet, generate a temporary ID and add to backlog
                         if not is_internet_connected():
                             import uuid
                             temp_id = f"temp_{str(uuid.uuid4())[:8]}"
                             logger.info(f"Offline: Adding '{self.currently_tracking}' to backlog with temporary ID {temp_id}")
                             # Add to backlog for future syncing
                             self.backlog_cleaner.add(temp_id, self.currently_tracking)
                             self.completed = True  # Mark as completed locally
                             
                             # Notify user about offline completion and backlog addition
                             self._send_notification(
                                 "Offline: Added to Backlog",
                                 f"'{self.currently_tracking}' will be identified and marked as watched when back online."
                             )
                             
                             self._log_playback_event("marked_for_backlog_with_temp_id", {"temp_id": temp_id})
                         else:
                             # If online but no ID, just log and wait for identification
                             logger.info(f"Completion threshold met for '{self.currently_tracking}', but Simkl ID not yet known. Deferring mark as watched.")

            # Update the time of the last progress check regardless of outcome
            self.last_progress_check = current_time

        # Determine if a scrobble update should be logged/returned
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
        self.current_filepath = None # Reset filepath on stop

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
        
        # Initialize watch history manager
        if not hasattr(self, 'watch_history'):
            self.watch_history = WatchHistoryManager(self.app_data_dir)
        
        if self.testing_mode:
            logger.info(f"TEST MODE: Simulating marking '{display_title}' (ID: {simkl_id}) as watched")
            self.completed = True
            self._log_playback_event("marked_as_watched_test_mode")

            # Test mode notification - show regardless of connection status
            self._send_notification(
                "Movie Marked as Watched (Test Mode)",
                f"'{display_title}' was marked as watched (test mode)"
            )
            
            # Store in watch history even in test mode
            self._store_in_watch_history(simkl_id, title, movie_name)
            
            return True

        if not self.client_id or not self.access_token:
            logger.error("Cannot mark movie as watched: missing API credentials")
            self._log_playback_event("marked_as_watched_fail_credentials")
            logger.info(f"Adding '{display_title}' (ID: {simkl_id}) to backlog due to missing credentials")
            self.backlog_cleaner.add(simkl_id, title)

            # Error notification - show regardless of connection status
            self._send_notification(
                "Authentication Error",
                f"Could not mark '{display_title}' as watched - missing credentials. Added to backlog."
            )
            return False

        try:
            if not is_internet_connected():
                logger.warning(f"System appears to be offline. Adding '{display_title}' (ID: {simkl_id}) to backlog for future syncing")
                self._log_playback_event("marked_as_watched_offline")
                self.backlog_cleaner.add(simkl_id, title)

                # Offline notification - show only when offline (implicitly handled by context)
                self._send_notification(
                    "Offline: Added to Backlog",
                    f"'{display_title}' will be marked as watched when back online."
                    # No explicit offline_only=True needed as this code path only runs when offline
                )
                
                # Store in local watch history even when offline
                self._store_in_watch_history(simkl_id, title, movie_name)
                
                return False

            # --- Online Scenario ---
            result = mark_as_watched(simkl_id, self.client_id, self.access_token)
            if result:
                logger.info(f"Successfully marked '{display_title}' as watched on Simkl")
                self.completed = True
                self._log_playback_event("marked_as_watched_api_success")
                
                # Store in watch history
                self._store_in_watch_history(simkl_id, title, movie_name)
                
                # Online Success Notification (Online Only)
                self._send_notification(
                    "Movie Marked as Watched",
                    f"'{display_title}' successfully marked as watched on Simkl.",
                    online_only=True
                )
                return True
            else:
                # Online Failure Notification
                logger.warning(f"Failed to mark '{display_title}' as watched online, adding to backlog")
                self._log_playback_event("marked_as_watched_api_fail")
                self.backlog_cleaner.add(simkl_id, title)

                self._send_notification(
                    "Online: Marking Failed",
                    f"Could not mark '{display_title}' online. Added to backlog for retry."
                    # Error notification - show regardless of connection status
                )
                return False
        except Exception as e:
            logger.error(f"Error marking movie as watched: {e}")
            self._log_playback_event("marked_as_watched_api_error", {"error": str(e)})
            logger.info(f"Adding '{display_title}' (ID: {simkl_id}) to backlog due to error: {e}")
            self.backlog_cleaner.add(simkl_id, title)

            # Error notification - show regardless of connection status
            self._send_notification(
                "Error Marking Watched",
                f"An error occurred trying to mark '{display_title}'. Added to backlog. Error: {e}"
            )
            return False
            
    def _store_in_watch_history(self, simkl_id, title, movie_name=None):
        """
        Store watched media information in the local watch history
        
        Args:
            simkl_id: The Simkl ID of the media
            title: Original title from window or filename
            movie_name: Official title from Simkl API (optional)
        """
        try:
            if not hasattr(self, 'watch_history'):
                self.watch_history = WatchHistoryManager(self.app_data_dir)
                
            # Prepare media info dictionary
            media_info = {
                'simkl_id': simkl_id,
                'title': movie_name or title,  # Use official name if available
                'original_title': title,       # Store original title for reference
                'type': 'movie'                # Default type is movie
            }
            
            # Add additional metadata if available
            if self.total_duration_seconds:
                media_info['runtime'] = round(self.total_duration_seconds / 60)  # Convert to minutes
            
            # Use the stored file path if available
            media_file_path = self.current_filepath
            if media_file_path:
                logger.info(f"Using stored filepath for watch history: {media_file_path}")
            else:
                logger.info("No stored filepath available for watch history.")

            # Try to get more details from the media cache
            cached_info = self.media_cache.get(title)
            if cached_info:
                # Add any additional cached metadata
                if 'year' in cached_info:
                    media_info['year'] = cached_info['year']
                if 'overview' in cached_info:
                    media_info['overview'] = cached_info['overview']
                if 'poster' in cached_info: # Check cache for 'poster'
                    media_info['poster'] = cached_info['poster'] # Store as 'poster'
                    
            # If we have API credentials and online, try to get more details
            if self.client_id and self.access_token and is_internet_connected():
                try:
                    details = get_movie_details(simkl_id, self.client_id, self.access_token)
                    if details:
                        # Update with more accurate info from the API
                        if 'title' in details:
                            media_info['title'] = details['title']
                        if 'year' in details:
                            media_info['year'] = details['year']
                        if 'overview' in details:
                            media_info['overview'] = details['overview']
                        if 'runtime' in details:
                            media_info['runtime'] = details['runtime']
                        if 'poster' in details:
                            media_info['poster'] = details['poster'] # Store as 'poster'
                            
                        # Update the media cache with these details for future use
                        cached_data = {
                            "simkl_id": simkl_id,
                            "movie_name": details.get('title', movie_name or title),
                            "year": details.get('year'),
                            "overview": details.get('overview'),
                            "poster": details.get('poster') # Cache as 'poster' for consistency
                        }
                        if 'runtime' in details:
                            cached_data["duration_seconds"] = details['runtime'] * 60
                        self.media_cache.set(title, cached_data)
                except Exception as e:
                    logger.warning(f"Failed to fetch additional details for watch history: {e}")
            
            # Add to watch history, passing the file path if available
            if media_file_path:
                success = self.watch_history.add_entry(media_info, media_file_path=media_file_path)
                logger.info(f"Added '{media_info['title']}' to local watch history with file path")
            else:
                success = self.watch_history.add(media_info)
                logger.info(f"Added '{media_info['title']}' to local watch history without file path")
            
            if not success:
                logger.warning(f"Failed to add '{media_info['title']}' to local watch history")
                
        except Exception as e:
            logger.error(f"Error storing media in watch history: {e}", exc_info=True)

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
        failure_occurred = False # Track if any item failed
        pending = self.backlog_cleaner.get_pending()
        total_attempted = len(pending) # Total items we will try to process

        if not pending:
            # Return detailed status even if empty
            return {'processed': 0, 'attempted': 0, 'failed': False}

        logger.info(f"[Offline Sync] Processing {total_attempted} backlog entries...")
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
                        # Notify user about successful sync from backlog (Online Only)
                        # This process only runs when online anyway, but explicit for clarity
                        self._send_notification(
                            "Synced from Backlog",
                            f"'{title}' successfully synced to Simkl.",
                            online_only=True
                        )
                    else:
                        logger.warning(f"[Offline Sync] Failed to mark '{title}' as watched after resolving ID. Will retry.")
                        failure_occurred = True # Mark failure
                else:
                    logger.warning(f"[Offline Sync] Could not resolve Simkl ID for '{title}'. Will retry.")
                    failure_occurred = True # Mark failure
            elif simkl_id: # Item has a non-temporary ID
                logger.info(f"[Offline Sync] Syncing '{title}' (ID: {simkl_id}) to Simkl...")
                result = mark_as_watched(simkl_id, self.client_id, self.access_token)
                if result:
                    logger.info(f"[Offline Sync] Successfully marked '{title}' as watched on Simkl.")
                    self.backlog_cleaner.remove(simkl_id)
                    success_count += 1
                    # Notify user about successful sync from backlog (Online Only)
                    # This process only runs when online anyway, but explicit for clarity
                    self._send_notification(
                        "Synced from Backlog",
                        f"'{title}' successfully synced to Simkl.",
                        online_only=True
                    )
                else:
                    logger.warning(f"[Offline Sync] Failed to mark '{title}' (ID: {simkl_id}) as watched. Will retry.")
                    failure_occurred = True # Mark failure
            else:
                logger.warning(f"[Offline Sync] Invalid backlog entry: {item}")
                failure_occurred = True # Mark failure

        if success_count > 0:
            logger.info(f"[Offline Sync] Backlog sync complete. {success_count} entries synced.")
        else:
            # Log based on whether attempts were made
            if total_attempted > 0:
                logger.info("[Offline Sync] No entries were successfully synced this cycle (failures occurred or items remain).")
            else:
                 logger.info("[Offline Sync] No backlog entries found to process.")

        return {'processed': success_count, 'attempted': total_attempted, 'failed': failure_occurred}

    def start_offline_sync_thread(self, interval_seconds=120):
        """Start a background thread to periodically sync backlog when online."""
        if hasattr(self, '_offline_sync_thread') and self._offline_sync_thread.is_alive():
            return
            
        import threading
        
        def sync_loop():
            while True:
                try:
                    if is_internet_connected():
                        # Check if there are any pending items before logging
                        pending_items = self.backlog_cleaner.get_pending()
                        if pending_items:
                            logger.info(f"[Offline Sync] Internet detected. Processing {len(pending_items)} backlog items...")
                            result = self.process_backlog()
                            
                            # Handle both dictionary and integer return types
                            if isinstance(result, dict):
                                # New format - dictionary with detailed info
                                processed_count = result.get('processed', 0)
                                attempted_count = result.get('attempted', 0)
                                
                                if processed_count > 0:
                                    logger.info(f"[Offline Sync] Synced {processed_count} of {attempted_count} backlog entries to Simkl.")
                                elif attempted_count > 0:
                                    logger.info(f"[Offline Sync] Attempted to sync {attempted_count} items but none succeeded.")
                            elif result > 0:  # Legacy format - integer count
                                logger.info(f"[Offline Sync] Synced {result} backlog entries to Simkl.")
                        else:
                            # Only log at debug level when no items are in backlog
                            logger.debug("[Offline Sync] No items in backlog to process.")
                    else:
                        logger.debug("[Offline Sync] Still offline. Will retry later.")
                except Exception as e:
                    logger.error(f"[Offline Sync] Error during backlog sync: {e}", exc_info=True)
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

                # Notify only if it's a new identification or update (Online Only)
                if is_new_identification:
                    self._send_notification(
                        "Movie Identified",
                        f"Playing: '{movie_name}'\nSimkl ID: {simkl_id}",
                        online_only=True
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