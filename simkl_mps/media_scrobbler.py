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
from difflib import SequenceMatcher # Add import for fuzzy matching
from datetime import datetime, timedelta
import threading
from collections import deque
from requests.exceptions import RequestException # Added for specific error handling

# Import necessary functions and libraries
from simkl_mps.simkl_api import (
    is_internet_connected,
    get_movie_details,
    search_file,
    add_to_history,
    search_movie
)
from simkl_mps.backlog_cleaner import BacklogCleaner
from simkl_mps.window_detection import parse_movie_title, parse_filename_from_path, is_video_player
from simkl_mps.media_cache import MediaCache
# --- Add guessit import ---
logger = logging.getLogger(__name__)  # Make sure logger is defined before using it
try:
    import guessit
except ImportError:
    logger.error("The 'guessit' library is required for episode detection. Please install it: pip install guessit")
    guessit = None
# --- End guessit import ---
from simkl_mps.utils.constants import PLAYING, PAUSED, STOPPED, DEFAULT_POLL_INTERVAL
from simkl_mps.config_manager import get_setting, DEFAULT_THRESHOLD # Import settings functions
from simkl_mps.watch_history_manager import WatchHistoryManager # Import WatchHistoryManager

# Removed redundant logger definition

class MediaScrobbler: # Renamed class
    """Handles the scrobbling of media (movies, episodes) to SIMKL"""
    
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
        self.current_filepath = None # Store the last known filepath
        self.media_type = None # 'movie', 'episode' (from guessit), 'show', 'anime' (from simkl)
        self.season = None # Season number for episodes
        self.episode = None # Episode number for episodes
        self.last_backlog_attempt_time = {} # Track last offline sync attempt per item {cache_key: timestamp}
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
                logger.debug(f"Unable to identify media in '{window_info.get('title', '')}' or from filepath.")
                self.stop_tracking()
            return None

        # --- Media Type Identification using Guessit (if filepath available) ---
        identified_type = 'movie' # Default assumption
        guessit_info = None
        if filepath and guessit:
            try:
                # Use guessit on the filename for better results
                filename = os.path.basename(filepath)
                guessit_info = guessit.guessit(filename)
                identified_type = guessit_info.get('type', 'movie') # 'movie' or 'episode'
                logger.debug(f"Guessit identified type: '{identified_type}' from '{filename}'. Info: {guessit_info}")
            except Exception as e:
                logger.warning(f"Guessit failed to parse '{filepath}': {e}")
        # --- End Guessit Identification ---

        # If we're already tracking a different movie, stop tracking before starting the new one
        if self.currently_tracking and self.currently_tracking != movie_title:
            logger.info(f"Media change detected: '{movie_title}' now playing")
            self.stop_tracking()
             
        # Start tracking the media if not already tracking
        if not self.currently_tracking:
            # Log detection source and type
            log_prefix = f"Detected {identified_type}"
            if detection_source == "filename":
                 logger.info(f"{log_prefix} from filename: '{movie_title}' (from: {detection_details})")
            elif detection_source == "window_title":
                 logger.info(f"{log_prefix} from window title: '{movie_title}'")
            else:
                 logger.info(f"Starting tracking for '{movie_title}' (type: {identified_type})")

            self._start_new_movie(movie_title)
            self.media_type = identified_type # Store initial type from guessit
            self.current_filepath = filepath # Store filepath at start

            # --- Initial API Lookup based on Type ---
            if identified_type == 'episode' and filepath:
                # If it's an episode, try search_file immediately
                logger.info(f"Attempting Simkl file search for episode: {filepath}")
                # Pass guessit_info for offline fallback
                self._identify_media_from_filepath(filepath, guessit_info)
            elif identified_type == 'movie':
                # For movies, attempt identification immediately
                logger.info(f"Movie detected. Attempting Simkl identification now for '{movie_title}'.")
                # Pre-check cache first
                cache_key = os.path.basename(filepath).lower() if filepath else movie_title.lower()
                cached_info = self.media_cache.get(cache_key)
                if cached_info and cached_info.get('simkl_id'):
                    logger.info(f"Found cached info for movie '{movie_title}': ID {cached_info['simkl_id']}")
                    self.simkl_id = cached_info.get('simkl_id')
                    self.movie_name = cached_info.get('movie_name', movie_title) # Use cached official name
                    self.media_type = cached_info.get('type', 'movie') # Update type if cached
                    if 'duration_seconds' in cached_info and self.total_duration_seconds is None:
                        self.total_duration_seconds = cached_info['duration_seconds']
                        self.estimated_duration = self.total_duration_seconds
                        logger.info(f"Set duration from cache: {self.total_duration_seconds}s")
                # If not in cache, trigger online identification
                elif is_internet_connected():
                     self._identify_movie(movie_title)
                else:
                     logger.info("Offline: Movie identification deferred.")
            # --- End Initial API Lookup ---
        
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
        self.movie_name = None # This will store movie title or show title
        self.current_filepath = None # Reset filepath on new media
        self.media_type = None # Reset type
        self.season = None # Reset season
        self.episode = None # Reset episode

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
                         self.current_filepath = filepath
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

        # --- Attempt Identification if needed ---
        # If we don't have a Simkl ID yet, try to identify the media
        if not self.simkl_id and self.currently_tracking:
            # Use filename as cache key if filepath exists, otherwise use original title
            lookup_key = os.path.basename(self.current_filepath).lower() if self.current_filepath else self.currently_tracking.lower()
            cached_info = self.media_cache.get(lookup_key)

            if cached_info and cached_info.get('simkl_id'):
                 logger.info(f"Found cached info for '{lookup_key}' during update: ID {cached_info['simkl_id']}")
                 self.simkl_id = cached_info.get('simkl_id')
                 self.movie_name = cached_info.get('movie_name')
                 self.media_type = cached_info.get('type')
                 self.season = cached_info.get('season')
                 self.episode = cached_info.get('episode')
                 if 'duration_seconds' in cached_info and self.total_duration_seconds is None:
                     self.total_duration_seconds = cached_info['duration_seconds']
                     self.estimated_duration = self.total_duration_seconds
                     logger.info(f"Set duration from cache: {self.total_duration_seconds}s")
            elif is_internet_connected(): # Only attempt online identification if not found in cache and online
                if self.media_type == 'episode' and self.current_filepath:
                    # Try identifying episode via filepath if not already done or failed
                    self._identify_media_from_filepath(self.current_filepath)
                elif self.media_type == 'movie':
                     # Try identifying movie via title search if not already done or failed
                     self._identify_movie(self.currently_tracking)
            # If identification was successful, self.simkl_id will now be set

        # --- Log Progress ---
        log_progress = state_changed or position_updated or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        if log_progress:
             self._log_playback_event("progress_update")

        # --- Check Completion Threshold ---
        if not self.completed and (current_time - self.last_progress_check > 5):
            completion_pct = self._calculate_percentage(use_position=position_updated)

            if completion_pct and completion_pct >= self.completion_threshold:
                 display_title = self.movie_name or self.currently_tracking
                 logger.info(f"Completion threshold ({self.completion_threshold}%) met for '{display_title}'")
                 self._log_playback_event("completion_threshold_reached")

                 # Attempt to add to history (handles ID check, API call, backlog)
                 # This method will set self.completed on success or backlog addition
                 # Notifications for backlog addition are handled within _attempt_add_to_history.
                 self._attempt_add_to_history()

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
        self.media_type = None # Reset type
        self.season = None # Reset season
        self.episode = None # Reset episode

        return final_scrobble_info

    def _identify_media_from_filepath(self, filepath, guessit_info=None):
        """
        Identifies media (movie or episode) using the Simkl /search/file endpoint
        and updates the scrobbler's state. Handles offline fallback using guessit.

        Args:
            filepath (str): The full path to the media file.
            guessit_info (dict, optional): Pre-parsed guessit info for fallback.
        """
        if not self.client_id:
            logger.warning("Cannot identify media from filepath: Missing Client ID.")
            return

        # Use filename as cache key for file searches
        cache_key = os.path.basename(filepath).lower() if filepath else self.currently_tracking.lower()
        cached_info = self.media_cache.get(cache_key)

        # Check cache first
        if cached_info and cached_info.get('simkl_id'):
            logger.info(f"Found cached info for file '{cache_key}': ID {cached_info['simkl_id']}")
            self.simkl_id = cached_info.get('simkl_id')
            self.movie_name = cached_info.get('movie_name') # Show/Movie Title
            self.media_type = cached_info.get('type') # movie, show, anime
            self.season = cached_info.get('season')
            self.episode = cached_info.get('episode')
            if 'duration_seconds' in cached_info and self.total_duration_seconds is None:
                 self.total_duration_seconds = cached_info['duration_seconds']
                 self.estimated_duration = self.total_duration_seconds
                 logger.info(f"Set duration from cache: {self.total_duration_seconds}s")
                 
            # Send notification if it's a new identification for the current tracking item
            if self.currently_tracking and self.movie_name and self.simkl_id:
                 display_text = f"Playing: '{self.movie_name}'"
                 if self.media_type != 'movie' and self.season is not None and self.episode is not None:
                     display_text += f" S{self.season}E{self.episode}"
                 elif self.media_type == 'anime' and self.episode is not None:
                     display_text += f" E{self.episode}"
                 elif self.media_type == 'movie' and cached_info.get('year'):
                     display_text += f" ({cached_info.get('year')})"

                 self._send_notification(
                     f"{self.media_type.capitalize()} Identified (Cache)",
                     display_text,
                     online_only=True
                 )
            return

        # Handle offline case with fallback
        if not is_internet_connected():
            logger.warning(f"Offline: Cannot identify '{filepath or cache_key}' via Simkl API.")
            # Use guessit fallback when offline
            if guessit and (guessit_info or filepath):
                try:
                    # Use passed guessit_info or generate from filepath
                    info = guessit_info or (guessit.guessit(os.path.basename(filepath)) if filepath else None)
                    
                    if isinstance(info, dict) and info.get('title'):
                        self.media_type = info.get('type', 'episode')
                        self.movie_name = info.get('title')
                        self.season = info.get('season')
                        self.episode = info.get('episode')
                        
                        logger.info(f"Using guessit fallback: Title='{self.movie_name}', Type='{self.media_type}',"
                                    f"{f' S={self.season}' if self.season is not None else ''}"
                                    f"{f', E={self.episode}' if self.episode is not None else ''}")
                        
                        # Cache the guessit data
                        self.media_cache.set(cache_key, {
                            "type": self.media_type,
                            "movie_name": self.movie_name,
                            "season": self.season,
                            "episode": self.episode,
                            "source": "guessit_fallback",
                            "original_filepath": filepath
                        })
                        
                        self._send_notification(
                            "Offline Media Detection",
                            f"Using Filename Data: '{self.movie_name}'" + 
                            (f" S{self.season}E{self.episode}" if self.media_type == 'episode' and 
                             self.season is not None and self.episode is not None else "")
                        )
                    else:
                        logger.warning(f"Guessit couldn't extract valid title from '{filepath}'")
                except Exception as e:
                    logger.error(f"Error using guessit fallback: {e}")
            else:
                logger.warning("No guessit info available for offline fallback.")
            return

        # --- Online Identification using search_file API ---
        if not filepath:
            logger.warning("Online identification skipped: Filepath is missing.")
            return

        try:
            logger.info(f"Querying Simkl API with file: {filepath}")
            result = search_file(filepath, self.client_id)

        except RequestException as e:
            logger.warning(f"Network error during Simkl file identification for '{filepath}': {e}")
            # Check if the initial type detected was 'episode' before adding to backlog
            # This aligns with the requirement to only backlog failed *episode* searches
            if self.media_type == 'episode':
                 self.backlog_cleaner.add(filepath, os.path.basename(filepath), additional_data={"type": "episode", "original_filepath": filepath})
            # Use guessit fallback even if network error occurred, if info is available
            if guessit_info:
                logger.info(f"Using guessit fallback data for '{filepath}' due to network error.")
                self._store_guessit_fallback_data(filepath, guessit_info)
            return # Stop further processing in this function after network error

        except Exception as e:
            logger.error(f"Error during Simkl file identification for '{filepath}': {e}", exc_info=True)
            # Also use guessit fallback on other exceptions if info is available
            if guessit_info:
                logger.info(f"Using guessit fallback data for '{filepath}' due to unexpected error.")
                self._store_guessit_fallback_data(filepath, guessit_info)
            return # Stop further processing

        # --- Process successful API result ---
        if result:
            if not result: # This check seems redundant now after the try/except, but kept for safety
                logger.info(f"Simkl /search/file did not find a match for '{filepath}'.")
                # Store guessit fallback if API didn't find results
                if guessit_info:
                    logger.info(f"Storing guessit fallback data for '{filepath}'")
                    self._store_guessit_fallback_data(filepath, guessit_info)
                return
                
            # Extract media information based on the result type
            if 'show' in result:
                media_info = result['show']
                simkl_type = media_info.get('type', 'show')  # Could be 'anime'
                is_show_or_anime = True
                
                # Get extended show/anime details
                show_id = media_info['ids']['simkl']
                extended_details = None
                if self.access_token:  # Need access token for extended details
                    try:
                        from simkl_mps.simkl_api import get_show_details
                        logger.info(f"Fetching extended details for {simkl_type} ID: {show_id}")
                        extended_details = get_show_details(show_id, self.client_id, self.access_token)
                        if extended_details:
                            logger.info(f"Successfully retrieved extended details for '{media_info.get('title')}'")
                            # Update media_info with extended details
                            if 'overview' not in media_info and 'overview' in extended_details:
                                media_info['overview'] = extended_details['overview']
                            if 'poster' not in media_info and 'poster' in extended_details:
                                media_info['poster'] = extended_details['poster']
                            if 'year' not in media_info and 'year' in extended_details:
                                media_info['year'] = extended_details['year']
                    except Exception as e:
                        logger.warning(f"Error fetching extended details for show ID {show_id}: {e}")
            elif 'movie' in result:
                media_info = result['movie']
                simkl_type = 'movie'
                is_show_or_anime = False
            else:
                logger.warning(f"Simkl /search/file response missing expected fields: {result}")
                return

            if not (media_info and 'ids' in media_info and media_info['ids'].get('simkl')):
                logger.warning(f"Simkl /search/file found a result but no valid Simkl ID was present.")
                return
                
            # Set basic media info
            self.simkl_id = media_info['ids']['simkl']
            self.movie_name = media_info.get('title', self.currently_tracking)
            self.media_type = simkl_type

            # Extract episode details according to API docs
            episode_details = result.get('episode', {})
            logger.debug(f"Episode details from Simkl: {episode_details}")
            
            # Process multipart episodes 
            is_multipart = episode_details.get('multipart', False)
            if is_multipart:
                logger.info(f"Detected multipart episode file (multipart={is_multipart})")
            
            # Extract season and episode directly from API fields
            self.season = None
            if 'season' in episode_details:
                try:
                    self.season = int(episode_details['season'])
                    logger.debug(f"Found season {self.season}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse season from value: {episode_details['season']}")
            
            self.episode = None
            if 'episode' in episode_details:
                try:
                    self.episode = int(episode_details['episode'])
                    logger.debug(f"Found episode {self.episode}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse episode from value: {episode_details['episode']}")
            
            # Log identification results
            if self.media_type in ['show', 'anime']:
                if self.season is not None and self.episode is not None:
                    logger.info(f"Identified: {self.media_type} '{self.movie_name}' S{self.season}E{self.episode}")
                elif self.episode is not None:
                    logger.info(f"Identified anime '{self.movie_name}' E{self.episode} (no season)")
                else:
                    logger.warning(f"No episode information found for '{self.movie_name}'")
            
            year = media_info.get('year')
            logger.info(f"Simkl identified '{filepath}' as: Type='{self.media_type}', Title='{self.movie_name}', ID={self.simkl_id}" +
                        (f", S{self.season}" if self.season is not None else "") +
                        (f", E{self.episode}" if self.episode is not None else ""))

            # Prepare data for caching
            # Extract desired details
            simkl_id_val = media_info.get('ids', {}).get('simkl')
            imdb_id_val = media_info.get('ids', {}).get('imdb')
            overview_val = media_info.get('overview') or episode_details.get('overview')
            poster_path = media_info.get('poster')
            poster_url_val = f"https://simkl.in/posters/{poster_path}_m.jpg" if poster_path else None

            # Build the cleaned ids dictionary
            cleaned_ids = {}
            if simkl_id_val:
                cleaned_ids['simkl'] = simkl_id_val
            if imdb_id_val:
                cleaned_ids['imdb'] = imdb_id_val

            # Prepare refined data for caching
            cached_data = {
                "simkl_id": self.simkl_id,  # Add top-level simkl_id for backward compatibility
                "movie_name": self.movie_name,
                "type": self.media_type,
                "year": year,
                "ids": cleaned_ids, # Store only cleaned IDs
                "overview": overview_val,
                "poster_url": poster_url_val,
                "source": "simkl_search_file",
                "original_filepath": filepath
                # Duration/Runtime handled below
            }
            
            # Add TV/anime specific fields
            if self.season is not None:
                cached_data["season"] = self.season
            if self.episode is not None:
                cached_data["episode"] = self.episode
            
            # Extract runtime/duration
            duration_seconds = None
            if 'runtime' in episode_details:
                try:
                    duration_seconds = int(episode_details['runtime']) * 60
                    logger.info(f"Duration from episode details: {duration_seconds}s")
                except (ValueError, TypeError):
                    pass
            elif 'runtime' in media_info:
                try:
                    duration_seconds = int(media_info['runtime']) * 60
                    logger.info(f"Duration from media details: {duration_seconds}s")
                except (ValueError, TypeError):
                    pass

            # Add duration_seconds if available
            if duration_seconds:
                cached_data["duration_seconds"] = duration_seconds
                if self.total_duration_seconds is None: # Update instance variable if needed
                    self.total_duration_seconds = duration_seconds
                    self.estimated_duration = duration_seconds

            # Save to cache
            self.media_cache.set(cache_key, cached_data)

            # Send user notification
            display_text = f"Playing: '{self.movie_name}'"
            if self.media_type != 'movie' and self.season is not None and self.episode is not None:
                display_text += f" S{self.season}E{self.episode}"
            elif self.media_type == 'anime' and self.episode is not None:
                display_text += f" E{self.episode}"
            elif self.media_type == 'movie' and year:
                display_text += f" ({year})"

            self._send_notification(
                f"{self.media_type.capitalize()} Identified",
                display_text,
                online_only=True
            )

        else: # Handle the case where API call was successful but returned no result
            logger.info(f"Simkl /search/file did not find a match for '{filepath}'.")
            # Store guessit fallback if API didn't find results
            if guessit_info:
                logger.info(f"Storing guessit fallback data for '{filepath}' after no Simkl match.")
                self._store_guessit_fallback_data(filepath, guessit_info)

    def _identify_movie(self, title_to_search):
        """
        Identifies a movie using Simkl /search/movie by processing a list of candidates
        and updates state. No fallback to file search for movies.
        """
        if not self.client_id or not self.access_token:
            logger.warning("Cannot identify movie: Missing Client ID or Access Token.")
            return

        # Use original title for movie cache key
        cache_key = title_to_search.lower()
        cached_info = self.media_cache.get(cache_key)
        if cached_info and cached_info.get('simkl_id'):
            logger.info(f"Found cached info for movie '{title_to_search}': ID {cached_info['simkl_id']}")
            self.simkl_id = cached_info.get('simkl_id')
            self.movie_name = cached_info.get('movie_name', title_to_search)
            self.media_type = cached_info.get('type', 'movie') # Update type if cached
            if 'duration_seconds' in cached_info and self.total_duration_seconds is None:
                self.total_duration_seconds = cached_info['duration_seconds']
                self.estimated_duration = self.total_duration_seconds
                logger.info(f"Set duration from cache: {self.total_duration_seconds}s")
            # Send notification if it's a new identification for the current tracking item
            if self.currently_tracking == title_to_search and self.movie_name and self.simkl_id:
                 display_text = f"Playing: '{self.movie_name}'"
                 if cached_info.get('year'):
                     display_text += f" ({cached_info.get('year')})"
                 self._send_notification(
                     "Movie Identified (Cache)",
                     display_text,
                     online_only=True
                 )
            return

        if not is_internet_connected():
            logger.warning(f"Offline: Cannot identify movie '{title_to_search}' via Simkl API. Adding to backlog for identification.")
            # Add to backlog for later identification
            id_for_backlog = f"identify_{cache_key}" # Unique prefix for identification tasks
            backlog_added = self.backlog_cleaner.add(
                id_for_backlog,
                title_to_search,
                additional_data={
                    "type": "identification_pending", # Special type
                    "original_title": title_to_search,
                    "media_type_guess": "movie", # Assume movie for now
                    "original_filepath": self.current_filepath # Store filepath if available
                }
            )
            # Send notification if added to backlog
            if backlog_added:
                 self._send_notification(
                     "Offline: Added Movie for Identification",
                     f"'{title_to_search}' will be identified when back online.",
                     offline_only=True
                 )
            return # Stop further processing in this function when offline

        logger.info(f"Attempting Simkl movie search for: '{title_to_search}'")

        try:
            # Call the API function which should return a list of candidates
            results = search_movie(title_to_search, self.client_id, self.access_token)

            # --- Process the result (could be list or dict) ---
            movie_info = None
            if isinstance(results, list) and len(results) > 0:
                # If it's a list, use the first valid dictionary element
                if isinstance(results[0], dict):
                    logger.info(f"Found {len(results)} results for '{title_to_search}'. Using the first result.")
                    movie_info = results[0]
                else:
                    logger.warning(f"First element in results list is not a dictionary: {results[0]}. Identification failed.")
            elif isinstance(results, dict):
                # If it's already a dictionary, use it directly
                logger.info(f"Found single result (dictionary) for '{title_to_search}'. Using it.")
                movie_info = results
            else:
                 # Handle empty list or other unexpected types
                 if isinstance(results, list) and len(results) == 0:
                     logger.warning(f"Simkl movie search for '{title_to_search}' returned no results. Identification failed.")
                 else:
                     logger.warning(f"Simkl movie search for '{title_to_search}' returned unexpected data format: {type(results)}. Identification failed.")

            # --- Process the selected movie_info if found ---
            if movie_info:
                # Extract the actual movie object if needed
                if 'movie' in movie_info:
                    movie_info = movie_info['movie']
                
                # Extract simkl_id correctly
                self.simkl_id = movie_info.get('ids', {}).get('simkl_id') or movie_info.get('ids', {}).get('simkl')
                self.movie_name = movie_info.get('title', title_to_search)
                self.media_type = 'movie' # Explicitly set type
                year = movie_info.get('year')
                runtime = movie_info.get('runtime') # Runtime in minutes

                if not self.simkl_id:
                     logger.warning(f"Selected result for '{title_to_search}' is missing a Simkl ID. Identification failed.")
                     return # Stop processing if ID is missing

                logger.info(f"Simkl identified: '{self.movie_name}' ({year}), ID={self.simkl_id}, Runtime={runtime}min")
                
                # Try to get additional details if not already present
                try:
                    # First check if we need to get more details
                    need_details = not movie_info.get('overview') or not movie_info.get('ids', {}).get('imdb')
                    
                    if need_details:
                        logger.info(f"Fetching additional details for movie ID {self.simkl_id}")
                        details = get_movie_details(self.simkl_id, self.client_id, self.access_token)
                        if details:
                            # Merge additional details
                            if 'overview' in details and not movie_info.get('overview'):
                                movie_info['overview'] = details['overview']
                            if 'ids' in details and 'imdb' in details['ids'] and not movie_info.get('ids', {}).get('imdb'):
                                if 'ids' not in movie_info:
                                    movie_info['ids'] = {}
                                movie_info['ids']['imdb'] = details['ids']['imdb']
                            if 'runtime' in details and not runtime:
                                runtime = details['runtime']
                except Exception as e:
                    logger.warning(f"Error fetching additional movie details: {e}")

                # Extract desired details
                simkl_id_val = self.simkl_id  # Use the value we already extracted
                imdb_id_val = movie_info.get('ids', {}).get('imdb')
                overview_val = movie_info.get('overview')
                poster_path = movie_info.get('poster')
                poster_url_val = f"https://simkl.in/posters/{poster_path}_m.jpg" if poster_path else None

                # Build the cleaned ids dictionary
                cleaned_ids = {}
                if simkl_id_val:
                    cleaned_ids['simkl'] = simkl_id_val
                if imdb_id_val:
                    cleaned_ids['imdb'] = imdb_id_val

                # Prepare refined data for caching
                cached_data = {
                    "simkl_id": simkl_id_val,  # Keep top-level simkl_id for backward compatibility
                    "movie_name": self.movie_name,
                    "type": self.media_type,
                    "year": year,
                    "ids": cleaned_ids, # Store cleaned IDs
                    "overview": overview_val,
                    "poster_url": poster_url_val,
                    "source": "simkl_search_movie" # Unified source
                    # Duration/Runtime handled below
                }
                # Add duration_seconds if available from runtime
                duration_seconds = None
                if runtime:
                    try:
                        duration_seconds = int(runtime) * 60
                        cached_data["duration_seconds"] = duration_seconds
                    except (ValueError, TypeError):
                         logger.warning("Could not parse runtime from movie details.")

                if duration_seconds and self.total_duration_seconds is None: # Update instance variable if needed
                    self.total_duration_seconds = duration_seconds
                    self.estimated_duration = duration_seconds
                    logger.info(f"Set duration from Simkl movie details: {self.total_duration_seconds}s")

                self.media_cache.set(cache_key, cached_data) # Use original title for movie cache key

                # Send notification
                display_text = f"Playing: '{self.movie_name}'"
                if year:
                    display_text += f" ({year})"
                self._send_notification(
                    "Movie Identified",
                    display_text,
                    online_only=True
                )
            # else: # No need for else here, handled by the initial checks
            #     # Tracking continues without ID if movie_info is None
            #     pass

        except Exception as e:
            logger.error(f"Error during Simkl movie identification for '{title_to_search}': {e}", exc_info=True)

    def _attempt_add_to_history(self):
        """
        Attempts to add the currently tracked media to Simkl history or backlog.
        Handles different media types, offline scenarios, and prevents rapid retries.
        Sets self.completed on success or when added to backlog.
        """
        display_title = self.movie_name or self.currently_tracking
        cache_key = os.path.basename(self.current_filepath).lower() if self.current_filepath else self.currently_tracking.lower()
        current_time = time.time()
        cooldown_period = 300 # 5 minutes cooldown for backlog attempts

        # --- Check 1: Already completed? ---
        if self.completed:
            logger.debug(f"'{display_title}' already marked as complete or backlogged. Skipping history add attempt.")
            return False

        # --- Check 2: Recently attempted backlog add? (Offline bug fix) ---
        last_attempt = self.last_backlog_attempt_time.get(cache_key)
        if last_attempt and (current_time - last_attempt < cooldown_period):
            logger.info(f"Recently attempted to backlog '{display_title}'. Cooldown active. Skipping history add attempt.")
            # Ensure completed flag is set if we are in cooldown after a backlog add
            self.completed = True
            return False # Don't proceed, but considered handled (in backlog)

        # --- Check 3: Credentials ---
        if not self.client_id or not self.access_token:
            logger.error(f"Cannot add '{display_title}' to history: missing API credentials.")
            # Add to backlog even without credentials if ID is known
            if self.simkl_id:
                logger.info(f"Adding '{display_title}' (ID: {self.simkl_id}) to backlog due to missing credentials.")
                # Store enough info for backlog processing later (modify backlog add if needed)
                # Using existing backlog format: simkl_id and title
                backlog_data = {
                    "simkl_id": self.simkl_id,
                    "title": display_title,
                    "type": self.media_type
                }
                
                # Add TV/anime specific data
                if self.media_type in ['show', 'anime']:
                    if self.season is not None:
                        backlog_data["season"] = self.season
                    if self.episode is not None:
                        backlog_data["episode"] = self.episode
                
                self.backlog_cleaner.add(self.simkl_id, display_title, additional_data=backlog_data) 
                self.last_backlog_attempt_time[cache_key] = current_time # Mark attempt time
                self.completed = True # Mark as completed locally
                self._log_playback_event("added_to_backlog_credentials", {"simkl_id": self.simkl_id})
                self._send_notification(
                    "Authentication Error",
                    f"Could not sync '{display_title}' - missing credentials. Added to backlog."
                )
            else:
                 logger.error(f"Cannot add '{display_title}' to backlog: missing Simkl ID and credentials.")
            return False

        # --- Check 4: Identification ---
        # Ensure we have an ID or fallback info before proceeding
        if not self.simkl_id:
            # Check cache for guessit fallback info if ID is missing
            cached_info = self.media_cache.get(cache_key)
            if cached_info and cached_info.get("source") == "guessit_fallback":
                logger.info(f"'{display_title}' has no Simkl ID, using guessit fallback info for backlog.")
                
                # Use filepath as the primary key for guessit backlog items if available
                backlog_key = self.current_filepath if self.current_filepath else f"guessit_{cache_key}"
                
                # Store title derived from guessit (without suffix)
                guessit_title = cached_info.get("movie_name", display_title)
                
                # Build backlog data with episode info and original filepath
                backlog_data = {
                    "title": guessit_title, # Removed "(Guessit Fallback)" suffix
                    "type": cached_info.get("type", "episode"),
                    "original_filepath": self.current_filepath # Ensure filepath is stored
                }
                
                # Add TV/anime specific data from guessit
                if cached_info.get("season") is not None:
                    backlog_data["season"] = cached_info["season"]
                if cached_info.get("episode") is not None:
                    backlog_data["episode"] = cached_info["episode"]
                
                logger.info(f"Adding guessit fallback item to backlog with key: '{backlog_key}'")
                self.backlog_cleaner.add(backlog_key, backlog_data["title"], additional_data=backlog_data)
                self.last_backlog_attempt_time[cache_key] = current_time # Still use cache_key for cooldown tracking
                self.completed = True
                self._log_playback_event("added_to_backlog_guessit", {"guessit_title": guessit_title, "backlog_key": backlog_key})
                self._send_notification(
                    "Offline: Added to Backlog (Guessit)",
                    f"'{guessit_title}' will be identified and synced later."
                )
                # DO NOT store guessit info in watch history locally yet
                # self._store_in_watch_history(temp_id, self.currently_tracking, guessit_title) # Removed call
                return False # Added to backlog
            elif not is_internet_connected():
                # No ID, no fallback, and offline - add with temp ID
                import uuid
                temp_id = f"temp_{str(uuid.uuid4())[:8]}" # Corrected indentation
                logger.info(f"Offline and unidentified: Adding '{display_title}' to backlog with temporary ID {temp_id}")
                # Build minimal backlog data for temp ID case
                backlog_data = { # Corrected indentation
                     "simkl_id": temp_id, # Use temp_id as the identifier
                     "title": display_title,
                     "type": self.media_type or 'unknown', # Use known type or default
                     "season": self.season,
                     "episode": self.episode,
                     "original_filepath": self.current_filepath # Store filepath if known
                 }
                self.backlog_cleaner.add(temp_id, display_title, additional_data=backlog_data) # Fixed indentation
                self.last_backlog_attempt_time[cache_key] = current_time # Fixed indentation
                self.completed = True # Fixed indentation
                self._log_playback_event("added_to_backlog_temp_id", {"temp_id": temp_id}) # Fixed indentation
                self._send_notification( # Fixed indentation
                     "Offline: Added to Backlog (Temp ID)",
                     f"'{display_title}' will be identified and synced later.")
                 # DO NOT store with temp ID in local history yet
                 # self._store_in_watch_history(temp_id, self.currently_tracking, display_title) # Removed call
                return False # Fixed indentation

            else:
                # Online but no ID and no fallback - log and wait
                logger.info(f"Cannot add '{display_title}' to history yet: Simkl ID not known. Will retry identification.")
                return False

        # --- Check 5: Internet Connection ---
        if not is_internet_connected():
            logger.warning(f"System appears to be offline. Adding '{display_title}' (ID: {self.simkl_id}) to backlog.")
            
            # Build backlog data with media type info
            backlog_data = {
                "simkl_id": self.simkl_id,
                "title": display_title,
                "type": self.media_type
            }
            
            # Add TV/anime specific data
            if self.media_type in ['show', 'anime']:
                if self.season is not None:
                    backlog_data["season"] = self.season
                if self.episode is not None:
                    backlog_data["episode"] = self.episode
            
            self.backlog_cleaner.add(self.simkl_id, display_title, additional_data=backlog_data)
            self.last_backlog_attempt_time[cache_key] = current_time # Mark attempt time
            self.completed = True # Mark as completed locally
            self._log_playback_event("added_to_backlog_offline", {"simkl_id": self.simkl_id})
            self._send_notification(
                "Offline: Added to Backlog",
                f"'{display_title}' will be synced when back online."
            )
            # DO NOT store in local history when offline yet
            # self._store_in_watch_history(self.simkl_id, self.currently_tracking, self.movie_name) # Removed call
            return False # Added to backlog

        # --- Before constructing payload, check if we need to get season/episode from cache or extract from filename ---
        # If we have a simkl_id but missing season/episode for TV shows, try to get from cache or extract from filename
        if self.media_type in ['show', 'anime'] and (self.season is None or self.episode is None):
            # First check if cached info has the season/episode
            cached_info = self.media_cache.get(cache_key)
            if cached_info:
                logger.info(f"Looking for missing season/episode in cache for '{display_title}'")
                
                # If season is missing, try to get from cache
                if self.season is None and 'season' in cached_info:
                    self.season = cached_info['season']
                    logger.info(f"Retrieved season {self.season} from cache for '{display_title}'")
                
                # If episode is missing, try to get from cache
                if self.episode is None and 'episode' in cached_info:
                    self.episode = cached_info['episode']
                    logger.info(f"Retrieved episode {self.episode} from cache for '{display_title}'")
            
            # If still missing season or episode, try to extract from filename using regex
            if self.season is None or self.episode is None:
                if self.current_filepath:
                    filename = os.path.basename(self.current_filepath)
                    
                    # Common season/episode patterns
                    patterns = [
                        r'[sS](\d{1,2})[eE](\d{1,4})',  # S01E01, s1e1
                        r'(\d{1,2})x(\d{2})',           # 1x01
                        r'[sS](\d{1,2}) - (\d{1,4})',   # S01 - 01
                        r'[sS](\d{1,2})\.?(\d{1,4})',   # S01.01 or S0101
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, filename)
                        if match:
                            extracted_season = int(match.group(1))
                            extracted_episode = int(match.group(2))
                            
                            if self.season is None:
                                self.season = extracted_season
                                
                                # Update cache with season if found
                                if cached_info:
                                    cached_info['season'] = self.season
                                    self.media_cache.set(cache_key, cached_info)
                            
                            if self.episode is None:
                                self.episode = extracted_episode
                                
                                # Update cache with episode if found
                                if cached_info:
                                    cached_info['episode'] = self.episode
                                    self.media_cache.set(cache_key, cached_info)
                            
                            break
                else:
                    # Try extracting from currently_tracking title
                    if self.currently_tracking:
                        for pattern in patterns:
                            match = re.search(pattern, self.currently_tracking)
                            if match:
                                extracted_season = int(match.group(1))
                                extracted_episode = int(match.group(2))
                                
                                if self.season is None:
                                    self.season = extracted_season
                                
                                if self.episode is None:
                                    self.episode = extracted_episode
                                
                                break

        # --- Construct Payload ---
        payload = {}
        item_ids = {"simkl": int(self.simkl_id)} # Ensure ID is integer

        if self.media_type == 'movie':
            payload = {"movies": [{"ids": item_ids}]}
            log_item_desc = f"movie '{display_title}' (ID: {self.simkl_id})"
        elif self.media_type == 'show': # TV Show
            if self.season is not None and self.episode is not None:
                payload = {
                    "shows": [{
                        "ids": item_ids,
                        "seasons": [{"number": int(self.season), "episodes": [{"number": int(self.episode)}]}] # Ensure ints
                    }]
                }
                log_item_desc = f"show '{display_title}' S{self.season}E{self.episode} (ID: {self.simkl_id})"
            else:
                return False # Cannot form valid payload
        elif self.media_type == 'anime':
            if self.episode is not None:
                 # Anime uses a different structure (no seasons in payload)
                payload = {
                    "shows": [{ # Still uses 'shows' key for anime
                        "ids": item_ids,
                        "episodes": [{"number": int(self.episode)}] # Ensure int
                    }]
                }
                log_item_desc = f"anime '{display_title}' E{self.episode} (ID: {self.simkl_id})"
            else:
                return False # Cannot form valid payload
        else:
            return False

        # --- Attempt API Call ---
        try:
            result = add_to_history(payload, self.client_id, self.access_token)
            if result:
                self.completed = True
                self._log_playback_event("added_to_history_success", {"simkl_id": self.simkl_id, "type": self.media_type})
                self._store_in_watch_history(self.simkl_id, self.currently_tracking, self.movie_name)
                self._send_notification(
                    f"{self.media_type.capitalize()} Synced",
                    f"'{display_title}' added to Simkl history.",
                    online_only=True
                )
                # Clear any previous backlog attempt time on success
                if cache_key in self.last_backlog_attempt_time:
                    del self.last_backlog_attempt_time[cache_key]
                return True
            else:
                # API call failed (but was attempted online)
                logger.warning(f"Failed to add {log_item_desc} to Simkl history online, adding to backlog.")
                
                # Build backlog data with media type info
                backlog_data = {
                    "simkl_id": self.simkl_id,
                    "title": display_title,
                    "type": self.media_type
                }
                
                # Add TV/anime specific data
                if self.media_type in ['show', 'anime']:
                    if self.season is not None:
                        backlog_data["season"] = self.season
                    if self.episode is not None:
                        backlog_data["episode"] = self.episode
                
                self.backlog_cleaner.add(self.simkl_id, display_title, additional_data=backlog_data)
                self.last_backlog_attempt_time[cache_key] = current_time # Mark attempt time
                self.completed = True # Mark as completed locally
                self._log_playback_event("added_to_backlog_api_fail", {"simkl_id": self.simkl_id})
                self._send_notification(
                    "Online Sync Failed",
                    f"Could not sync '{display_title}' online. Added to backlog."
                )
                return False # Added to backlog due to API failure
        except Exception as e:
            # Catch any unexpected errors during the API call
            logger.error(f"Unexpected error adding {log_item_desc} to history: {e}", exc_info=True)
            logger.info(f"Adding {log_item_desc} to backlog due to unexpected error.")
            
            # Build backlog data with media type info
            backlog_data = {
                "simkl_id": self.simkl_id,
                "title": display_title,
                "type": self.media_type
            }
            
            # Add TV/anime specific data
            if self.media_type in ['show', 'anime']:
                if self.season is not None:
                    backlog_data["season"] = self.season
                if self.episode is not None:
                    backlog_data["episode"] = self.episode
            
            self.backlog_cleaner.add(self.simkl_id, display_title, additional_data=backlog_data)
            self.last_backlog_attempt_time[cache_key] = current_time # Mark attempt time
            self.completed = True # Mark as completed locally
            self._log_playback_event("added_to_backlog_exception", {"simkl_id": self.simkl_id, "error": str(e)})
            self._send_notification(
                "Sync Error",
                f"Error syncing '{display_title}'. Added to backlog."
            )
            return False # Added to backlog due to exception

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
            
            # Use the stored file path if available
            media_file_path = self.current_filepath
            if media_file_path:
                logger.debug(f"Using stored filepath for watch history: {media_file_path}")

            # Get data from media cache first - this is our primary source
            # Try filename key first if filepath exists
            cached_info = None
            if self.current_filepath:
                filename_cache_key = os.path.basename(self.current_filepath).lower()
                cached_info = self.media_cache.get(filename_cache_key)

            # If filename key didn't work or no filepath, try title key
            if not cached_info and title:
                title_cache_key = title.lower()
                # Avoid redundant lookup if keys are the same
                if not self.current_filepath or filename_cache_key != title_cache_key:
                    cached_info = self.media_cache.get(title_cache_key)
            
            # Prepare base media info dictionary
            media_info = {
                'simkl_id': simkl_id,
                'title': movie_name or title, # Use official name if available
                'original_title': title,      # Always store original detected title
                'type': self.media_type or 'movie' # Use identified type or default
            }

            # If we have the latest cached data, use it to populate details
            if cached_info:
                cached_info = cached_info # Use the re-fetched data

                # Copy details from cache
                if 'movie_name' in cached_info and cached_info['movie_name']:
                    media_info['title'] = cached_info['movie_name']
                media_info['year'] = cached_info.get('year')
                media_info['poster_url'] = cached_info.get('poster_url')
                media_info['overview'] = cached_info.get('overview')

                # Handle IDs from cache
                if 'ids' in cached_info and isinstance(cached_info.get('ids'), dict):
                    media_info['ids'] = cached_info['ids'].copy()
                    if 'imdb' in cached_info['ids']:
                        media_info['imdb_id'] = cached_info['ids']['imdb']
                else:
                    media_info['ids'] = {'simkl': simkl_id} # Fallback if cache['ids'] is bad

                # Handle Runtime from cache
                if 'duration_seconds' in cached_info and cached_info['duration_seconds']:
                    media_info['runtime'] = round(cached_info['duration_seconds'] / 60)
                elif self.total_duration_seconds: # Fallback to instance duration if not in cache
                    media_info['runtime'] = round(self.total_duration_seconds / 60)

            # --- Ensure Season/Episode are set directly from instance attributes ---
            # This happens *after* potentially loading from cache, ensuring the latest
            # scrobbler state for S/E is passed to the history manager.
            if media_info['type'] in ['show', 'anime']:
                media_info['season'] = self.season # Use current instance value (can be None)
                media_info['episode'] = self.episode # Use current instance value (can be None)
            # --- End Season/Episode ---

            # --- Fallbacks for essential fields if not populated from cache ---
            if 'ids' not in media_info: # Ensure IDs dict exists
                 media_info['ids'] = {'simkl': simkl_id}
            if 'runtime' not in media_info and self.total_duration_seconds: # Ensure runtime exists if possible
                 media_info['runtime'] = round(self.total_duration_seconds / 60)
            # --- End Fallbacks ---

            # Double-check that critical fields have been transferred

            # Add to watch history, passing the file path if available
            if media_file_path:
                success = self.watch_history.add_entry(media_info, media_file_path=media_file_path)
            else:
                success = self.watch_history.add_entry(media_info)
            
            if not success:
                logger.warning(f"Failed to add '{media_info['title']}' to local watch history")
                
        except Exception as e:
            logger.error(f"Error storing media in watch history: {e}", exc_info=True)

    def process_backlog(self):
        """
        Process pending backlog items with retry logic and error handling.
        Attempts to resolve temporary IDs and sync items to Simkl history.
        """
        MAX_ATTEMPTS = 5 # Max attempts before giving up on an item
        BASE_RETRY_DELAY_SECONDS = 60 # Initial delay (1 minute)

        if not self.client_id or not self.access_token:
            logger.warning("[Offline Sync] Missing credentials, cannot process backlog.")
            return {'processed': 0, 'attempted': 0, 'failed': True, 'reason': 'Missing credentials'}

        # Import here to avoid circular dependency issues if called early
        from simkl_mps.simkl_api import add_to_history, search_movie, search_file, is_internet_connected

        if not is_internet_connected():
            logger.info("[Offline Sync] No internet connection. Backlog sync deferred.")
            return {'processed': 0, 'attempted': 0, 'failed': False, 'reason': 'Offline'}

        pending_items = self.backlog_cleaner.get_pending() # Get dict of items
        if not pending_items:
            return {'processed': 0, 'attempted': 0, 'failed': False, 'reason': 'No items'}

        logger.info(f"[Offline Sync] Processing {len(pending_items)} backlog entries...")

        success_count = 0
        items_attempted_this_cycle = 0
        failure_occurred_this_cycle = False
        current_time = time.time()

        # Iterate through a copy of keys to allow modification during iteration
        item_keys_to_process = list(pending_items.keys())

        for item_key in item_keys_to_process:
            item_data = pending_items.get(item_key) # Get current data for the key

            # --- Basic Item Validation ---
            if not isinstance(item_data, dict):
                logger.warning(f"[Offline Sync] Skipping invalid backlog item (expected dict, got {type(item_data)}) for key: {item_key}")
                failure_occurred_this_cycle = True
                continue

            original_id = item_data.get("simkl_id") # Could be real ID, temp_ ID, or guessit_ ID
            title = item_data.get("title", "Unknown Title")
            attempt_count = item_data.get("attempt_count", 0)
            last_attempt_ts = item_data.get("last_attempt_timestamp")

            # --- Check Max Attempts ---
            if attempt_count >= MAX_ATTEMPTS:
                logger.warning(f"[Offline Sync] Skipping item '{title}' (ID: {item_key}) - Max attempts ({MAX_ATTEMPTS}) reached.")
                # Optionally remove permanently failed items after max attempts? For now, just skip.
                # self.backlog_cleaner.remove(item_key)
                continue

            # --- Check Retry Delay (Exponential Backoff) ---
            if last_attempt_ts:
                retry_delay = BASE_RETRY_DELAY_SECONDS * (2 ** attempt_count) # Exponential backoff
                time_since_last_attempt = current_time - last_attempt_ts
                if time_since_last_attempt < retry_delay:
                    logger.debug(f"[Offline Sync] Skipping item '{title}' (ID: {item_key}) - Retry delay active ({time_since_last_attempt:.0f}s / {retry_delay:.0f}s).")
                    continue # Skip this item for now, wait for delay

            # --- If checks pass, attempt processing ---
            items_attempted_this_cycle += 1
            logger.info(f"[Offline Sync] Attempting item '{title}' (ID: {item_key}, Attempt: {attempt_count + 1})")

            media_type = item_data.get("type") # 'movie', 'show', 'anime', 'episode' (from guessit)
            season = item_data.get("season")
            episode = item_data.get("episode")
            original_filepath = item_data.get("original_filepath") # For guessit items

            simkl_id_to_use = original_id
            resolved_title = title # Use backlog title unless resolved differently
            api_error = None # Store potential API error message

            # --- Handle Different Backlog Item Types ---
            is_temp_id = isinstance(original_id, str) and (original_id.startswith("temp_") or original_id.startswith("guessit_"))
            is_identification_task = media_type == "identification_pending"

            simkl_id_to_use = original_id
            resolved_title = title
            api_error = None # Store potential API error message

            # --- A. Identification Task ---
            if is_identification_task:
                logger.info(f"[Offline Sync] Attempting identification for '{title}' (Original ID: {item_key})")
                identification_info = None
                identification_error = None
                original_title_for_search = item_data.get("original_title", title) # Use original title if available
                media_type_guess = item_data.get("media_type_guess", "movie") # Get the guess
                # Retrieve the original filepath for file-based search
                original_filepath_for_search = item_data.get("original_filepath")

                try:
                    # Use search_file if filepath exists and guess suggests episode/show/anime
                    if original_filepath_for_search and media_type_guess in ["episode", "show", "anime"]:
                         logger.debug(f"Using search_file for identification based on filepath: {original_filepath_for_search}")
                         identification_info = search_file(original_filepath_for_search, self.client_id)
                    # Otherwise, use search_movie (for movies or shows without filepath)
                    elif media_type_guess == "movie" or (media_type_guess in ["show", "anime"] and not original_filepath_for_search):
                         logger.debug(f"Using search_movie for identification based on title: {original_title_for_search}")
                         identification_info = search_movie(original_title_for_search, self.client_id, self.access_token)
                    else:
                         identification_error = f"Unsupported media_type_guess for identification: {media_type_guess}"

                except Exception as e:
                     identification_error = f"Identification search failed: {e}"
                     logger.warning(f"[Offline Sync] {identification_error}")

                # Process identification result
                if identification_info:
                    new_simkl_id = None
                    new_media_type = None
                    new_title = None
                    new_season = None
                    new_episode = None

                    # Extract details based on expected structure (movie or show/episode)
                    if 'movie' in identification_info and identification_info['movie'].get('ids', {}).get('simkl'):
                        new_simkl_id = identification_info['movie']['ids']['simkl']
                        new_media_type = 'movie'
                        new_title = identification_info['movie'].get('title', original_title_for_search)
                    elif 'show' in identification_info and identification_info['show'].get('ids', {}).get('simkl'):
                        new_simkl_id = identification_info['show']['ids']['simkl']
                        new_media_type = identification_info['show'].get('type', 'show') # Could be 'anime'
                        new_title = identification_info['show'].get('title', original_title_for_search)
                        if 'episode' in identification_info: # If search_file was used
                            new_season = identification_info['episode'].get('season')
                            new_episode = identification_info['episode'].get('number')
                    # Handle direct list result from search_movie (less common now but possible)
                    elif isinstance(identification_info, list) and identification_info:
                         first_result = identification_info[0]
                         if first_result.get('type') == 'movie' and first_result.get('ids', {}).get('simkl'):
                              new_simkl_id = first_result['ids']['simkl']
                              new_media_type = 'movie'
                              new_title = first_result.get('title', original_title_for_search)
                         # Add similar check for shows if search_movie could return shows in list

                    if new_simkl_id:
                        logger.info(f"[Offline Sync] Identified '{original_title_for_search}' as '{new_title}' (ID: {new_simkl_id}, Type: {new_media_type})")
                        # Update the backlog item with resolved info and mark as ready for sync
                        update_payload = {
                            'simkl_id': new_simkl_id, # Store the actual ID
                            'title': new_title,
                            'type': new_media_type,
                            'season': new_season, # Will be None if not applicable
                            'episode': new_episode, # Will be None if not applicable
                            'attempt_count': 0, # Reset attempts for sync phase
                            'last_attempt_timestamp': current_time, # Mark identification attempt time
                            'last_error': None # Clear previous error
                        }
                        self.backlog_cleaner.update_item(item_key, update_payload)
                        # Item is now updated, will be processed for sync in the *next* cycle
                        continue # Move to the next backlog item
                    else:
                        api_error = "Identification succeeded but no Simkl ID found."
                        logger.warning(f"[Offline Sync] {api_error} for '{original_title_for_search}'")
                        failure_occurred_this_cycle = True
                else:
                    api_error = identification_error or "Identification failed (no results)."
                    logger.warning(f"[Offline Sync] {api_error} for '{original_title_for_search}'")
                    failure_occurred_this_cycle = True

                # If identification failed, update backlog item's attempt count/error
                if api_error:
                    self.backlog_cleaner.update_item(item_key, {
                        'attempt_count': attempt_count + 1,
                        'last_attempt_timestamp': current_time,
                        'last_error': api_error
                    })
                continue # Skip sync attempt for this item this cycle

            # --- B. Resolve Temporary/Guessit/Filepath IDs (for items already marked for sync) ---
            # Check if the item_key itself is a filepath (used for guessit items) OR if it's a temp ID
            elif os.path.exists(item_key) or is_temp_id: # Check if key is a valid path OR a temp ID
                logger.info(f"[Offline Sync] Attempting to resolve ID for '{title}' (Original Key/ID: {item_key})")
                resolved_info = None
                resolution_error = None
                try:
                    # Prioritize file search if the key is a path or if original_filepath exists
                    filepath_to_search = item_key if os.path.exists(item_key) else original_filepath
                    if filepath_to_search:
                        logger.debug(f"Attempting resolution via search_file: {filepath_to_search}")
                        resolved_info = search_file(filepath_to_search, self.client_id)
                    
                    # Fallback to title search if file search failed or wasn't applicable
                    if not resolved_info and not os.path.exists(item_key): # Only fallback if key wasn't a path
                        logger.debug(f"Attempting resolution via search_movie: {title}")
                        # Determine media type for search_movie if possible
                        search_type = 'movie' # Default assumption for temp IDs
                        if media_type in ['show', 'anime']:
                             search_type = media_type # Use known type if available
                        # Note: search_movie currently only supports 'movie', but adapting for future
                        if search_type == 'movie':
                             resolved_info = search_movie(title, self.client_id, self.access_token)
                        else:
                             logger.warning(f"Title search for type '{search_type}' not implemented yet.")

                except Exception as e:
                     resolution_error = f"Resolution search failed: {e}"
                     logger.warning(f"[Offline Sync] {resolution_error}")

                # Extract resolved ID and update details
                if resolved_info:
                    new_simkl_id = None
                    # Check 1: Nested under 'movie' key
                    if 'movie' in resolved_info and isinstance(resolved_info.get('movie'), dict) and resolved_info['movie'].get('ids', {}).get('simkl'):
                        new_simkl_id = resolved_info['movie']['ids']['simkl']
                        media_type = 'movie'
                        resolved_title = resolved_info['movie'].get('title', title)
                    # Check 2: Directly in the result (if type is movie)
                    elif resolved_info.get('type') == 'movie' and resolved_info.get('ids', {}).get('simkl'):
                        new_simkl_id = resolved_info['ids']['simkl']
                        media_type = 'movie'
                        resolved_title = resolved_info.get('title', title)
                    # Check 3: Nested under 'show' key
                    elif 'show' in resolved_info and isinstance(resolved_info.get('show'), dict) and resolved_info['show'].get('ids', {}).get('simkl'):
                        new_simkl_id = resolved_info['show']['ids']['simkl']
                        media_type = resolved_info['show'].get('type', 'show') # Could be 'anime'
                        resolved_title = resolved_info['show'].get('title', title)
                        if 'episode' in resolved_info: # If search_file was used
                            season = resolved_info['episode'].get('season', season)
                            episode = resolved_info['episode'].get('number', episode)
                    # Check 4: Directly in the result (if type is show/anime) - Less likely from search_movie but good practice
                    elif resolved_info.get('type') in ['show', 'anime'] and resolved_info.get('ids', {}).get('simkl'):
                         new_simkl_id = resolved_info['ids']['simkl']
                         media_type = resolved_info.get('type', 'show')
                         resolved_title = resolved_info.get('title', title)
                         # Note: Episode info might not be present here if resolved via search_movie

                    if new_simkl_id:
                        simkl_id_to_use = new_simkl_id
                        logger.info(f"[Offline Sync] Resolved '{title}' to Simkl ID {simkl_id_to_use} (Type: {media_type})")
                        # Update item data IN MEMORY for payload construction below
                        item_data['simkl_id'] = simkl_id_to_use # Use resolved ID for payload
                        item_data['title'] = resolved_title
                        item_data['type'] = media_type
                        item_data['season'] = season
                        item_data['episode'] = episode
                        # Persist the resolved ID back to the backlog file?
                        # This prevents re-resolution but means the key changes.
                        # For now, let's NOT change the key, just use the resolved ID for sync.
                        # If sync fails, it will retry resolution next time.
                    else:
                        api_error = "Resolution succeeded but no Simkl ID found."
                        logger.warning(f"[Offline Sync] {api_error} for '{title}'")
                        failure_occurred_this_cycle = True
                else:
                    api_error = resolution_error or "Resolution failed (no results)."
                    logger.warning(f"[Offline Sync] {api_error} for '{title}'")
                    failure_occurred_this_cycle = True

                # If resolution failed, update backlog and skip sync attempt
                if api_error:
                    self.backlog_cleaner.update_item(item_key, {
                        'attempt_count': attempt_count + 1,
                        'last_attempt_timestamp': current_time,
                        'last_error': api_error
                    })
                    continue # Skip sync attempt

            # --- C. Construct Payload for add_to_history (for items ready to sync) ---
            # Ensure we have a valid numeric Simkl ID at this point
            if not simkl_id_to_use or not isinstance(simkl_id_to_use, (int, str)) or isinstance(simkl_id_to_use, str) and simkl_id_to_use.startswith(('temp_', 'guessit_', 'identify_')):
                 logger.warning(f"[Offline Sync] Invalid or unresolved Simkl ID '{simkl_id_to_use}' for item '{resolved_title}'. Skipping sync.")
                 failure_occurred_this_cycle = True
                 # Update attempt count even if ID is bad, to prevent infinite loops if resolution always fails
                 self.backlog_cleaner.update_item(item_key, {
                     'attempt_count': attempt_count + 1,
                     'last_attempt_timestamp': current_time,
                     'last_error': f"Invalid/Unresolved Simkl ID: {simkl_id_to_use}"
                 })
                 continue

            payload = {}
            log_item_desc = f"'{resolved_title}' (ID: {simkl_id_to_use})"
            try:
                item_ids = {"simkl": int(simkl_id_to_use)} # Ensure ID is integer for payload

                if media_type == 'movie':
                    payload = {"movies": [{"ids": item_ids}]}
                    log_item_desc = f"movie {log_item_desc}"
                elif media_type == 'show': # TV Show
                    if season is not None and episode is not None:
                        payload = {
                            "shows": [{
                                "ids": item_ids,
                                "seasons": [{"number": int(season), "episodes": [{"number": int(episode)}]}]
                            }]
                        }
                        log_item_desc = f"show {log_item_desc} S{season}E{episode}"
                    else:
                        api_error = "Missing season/episode for show"
                elif media_type == 'anime':
                    if episode is not None:
                        payload = {
                            "shows": [{ # Still uses 'shows' key for anime
                                "ids": item_ids,
                                "episodes": [{"number": int(episode)}]
                            }]
                        }
                        log_item_desc = f"anime {log_item_desc} E{episode}"
                    else:
                        api_error = "Missing episode for anime"
                else:
                    api_error = f"Unknown media type: {media_type}"

            except (ValueError, TypeError) as e:
                 api_error = f"Data type error for payload: {e}"

            # If payload construction failed, update backlog and skip
            if api_error:
                logger.warning(f"[Offline Sync] Payload error for {log_item_desc}: {api_error}. Skipping.")
                failure_occurred_this_cycle = True
                self.backlog_cleaner.update_item(item_key, {
                    'attempt_count': attempt_count + 1,
                    'last_attempt_timestamp': current_time,
                    'last_error': api_error
                })
                continue

            # --- Attempt API Call ---
            logger.info(f"[Offline Sync] Syncing {log_item_desc} to Simkl history...")
            sync_result = None
            try:
                # Directly use the imported add_to_history
                sync_result = add_to_history(payload, self.client_id, self.access_token)

                if sync_result:
                    logger.info(f"[Offline Sync] Successfully added {log_item_desc} to Simkl history.")
                    # Store in local history AFTER successful Simkl sync
                    self._store_in_watch_history(simkl_id_to_use, item_data.get("original_title", title), resolved_title) # Use resolved info
                    self.backlog_cleaner.remove(item_key) # Use item_key (original ID string) for removal
                    success_count += 1
                    self._send_notification(
                        "Synced from Backlog",
                        f"'{resolved_title}' successfully synced to Simkl.",
                        online_only=True
                    )
                else:
                    # API call failed (but was attempted online) - could be 4xx, 5xx, or other issue
                    api_error = "API call failed (returned None/False)"
                    logger.warning(f"[Offline Sync] {api_error} for {log_item_desc}. Will retry later.")
                    failure_occurred_this_cycle = True

            except requests.exceptions.RequestException as e:
                # Handle specific request exceptions (like connection errors, timeouts)
                api_error = f"Network error: {e}"
                logger.warning(f"[Offline Sync] {api_error} syncing {log_item_desc}. Will retry later.")
                failure_occurred_this_cycle = True
            except Exception as e:
                # Handle other unexpected errors during the API call
                api_error = f"Unexpected error: {e}"
                logger.error(f"[Offline Sync] {api_error} syncing {log_item_desc}.", exc_info=True)
                failure_occurred_this_cycle = True

            # --- Update Backlog Item on Failure ---
            if api_error:
                self.backlog_cleaner.update_item(item_key, {
                    'attempt_count': attempt_count + 1,
                    'last_attempt_timestamp': current_time,
                    'last_error': api_error
                })

        # --- Final Logging ---
        if items_attempted_this_cycle > 0:
             logger.info(f"[Offline Sync] Cycle complete. Attempted: {items_attempted_this_cycle}, Synced: {success_count}.")
        elif len(pending_items) > 0:
             logger.info("[Offline Sync] Cycle complete. No items ready for retry based on delay.")
        # No need to log if pending_items was empty initially

        return {'processed': success_count, 'attempted': items_attempted_this_cycle, 'failed': failure_occurred_this_cycle}

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

    def cache_media_info(self, title, simkl_id, display_name, media_type='movie', season=None, episode=None, year=None, runtime=None):
        """
        Cache media info to avoid repeated searches. Works for all media types.

        Args:
            title: Original title from window or filename
            simkl_id: Simkl ID of the media
            display_name: Official name from Simkl (show name or movie title)
            media_type: Type of media ('movie', 'show', or 'anime')
            season: Season number for TV shows (optional)
            episode: Episode number for TV shows or anime (optional)
            year: Release year (optional)
            runtime: Media runtime in minutes (optional)
        """
        if title and simkl_id:
            cached_data = {
                "simkl_id": simkl_id,
                "movie_name": display_name,  # Keep "movie_name" key for compatibility
                "type": media_type
            }
            
            # Add TV/anime specific data if provided
            if season is not None:
                cached_data["season"] = season
            if episode is not None:
                cached_data["episode"] = episode
            if year is not None:
                cached_data["year"] = year

            # Handle duration
            api_duration_seconds = None
            if runtime:
                api_duration_seconds = runtime * 60

            # Check for existing duration in cache before overwriting
            current_cached_info = self.media_cache.get(title)
            existing_cached_duration = current_cached_info.get("duration_seconds") if current_cached_info else None

            # Prioritize durations: current player duration > API duration > existing cache
            duration_to_cache = self.total_duration_seconds
            if duration_to_cache is None:
                duration_to_cache = api_duration_seconds
            if duration_to_cache is None:
                duration_to_cache = existing_cached_duration

            if duration_to_cache:
                cached_data["duration_seconds"] = duration_to_cache
                logger.info(f"Caching duration information: {duration_to_cache} seconds for '{display_name}'")
            else:
                logger.info(f"No duration information available to cache for '{display_name}'")

            self.media_cache.set(title, cached_data)
            
            # If we're currently tracking this title, update instance variables
            if self.currently_tracking == title:
                is_new_identification = self.simkl_id != simkl_id or self.movie_name != display_name
                
                # Update instance variables with the new info
                self.simkl_id = simkl_id
                self.movie_name = display_name
                self.media_type = media_type
                
                # Update episode/season info if provided
                if season is not None:
                    self.season = season
                if episode is not None:
                    self.episode = episode

                # Notify only if it's a new identification or update
                if is_new_identification:
                    type_display = media_type.capitalize()
                    details_text = f"Playing: '{display_name}'"
                    
                    if media_type in ['show', 'anime'] and season is not None and episode is not None:
                        details_text += f" S{season}E{episode}"
                    elif media_type == 'anime' and episode is not None:
                        details_text += f" E{episode}"
                    elif year is not None:
                        details_text += f" ({year})"
                        
                    self._send_notification(
                        f"{type_display} Identified",
                        details_text,
                        online_only=True
                    )

                # Update total duration if we got a new value
                if duration_to_cache is not None and self.total_duration_seconds != duration_to_cache:
                     if self.total_duration_seconds is None:
                          logger.info(f"Updating known duration from None to {duration_to_cache}s based on cache/API info")
                          self.total_duration_seconds = duration_to_cache
                          self.estimated_duration = duration_to_cache

    def is_complete(self, threshold=None):
        """
        Check if the media is considered watched (based on instance threshold)
        Works for all media types (movie, show, anime)
        
        Args:
            threshold: Optional override for completion threshold percentage
            
        Returns:
            bool: True if media has met completion threshold
        """
        # Not tracking anything currently
        if not self.currently_tracking:
            return False

        # Already marked as completed
        if self.completed:
            return True

        # Use instance threshold if not specified
        if threshold is None:
            threshold = self.completion_threshold

        # Try to get percentage from position first, fall back to accumulated watch time
        percentage = self._calculate_percentage(use_position=True)
        if percentage is None:
            percentage = self._calculate_percentage(use_accumulated=True)

        # No valid percentage could be calculated
        if percentage is None:
            return False

        # Compare percentage against threshold
        is_complete = percentage >= threshold
        
        # If this is the first time we're detecting completion, log based on media type
        if is_complete and not self.completed:
            media_description = f"{self.media_type or 'media'}"
            if self.media_type in ['show', 'anime'] and self.season is not None and self.episode is not None:
                media_description = f"{self.media_type} S{self.season}E{self.episode}"
            elif self.media_type == 'anime' and self.episode is not None:
                media_description = f"anime E{self.episode}"
                
            logger.info(f"Completion threshold ({threshold}%) met for {media_description}: '{self.movie_name or self.currently_tracking}'")

        return is_complete

    def _store_guessit_fallback_data(self, filepath, guessit_info):
        """
        Stores fallback data from guessit when Simkl API identification fails
        
        Args:
            filepath: Full path to the media file
            guessit_info: Dictionary with guessit parse results
        """
        if not guessit_info:
            logger.debug("No guessit data to store as fallback.")
            return
            
        try:
            media_type = guessit_info.get('type', 'episode')
            title = guessit_info.get('title')
            season = guessit_info.get('season')
            episode = guessit_info.get('episode')
            
            if not title:
                logger.warning(f"Cannot store guessit fallback data: Missing title in {guessit_info}")
                return
                
            # Use filename as cache key
            cache_key = os.path.basename(filepath).lower() if filepath else title.lower()
            
            # Build fallback cache data
            fallback_data = {
                "type": media_type,
                "movie_name": title, # Use "movie_name" key for compatibility
                "source": "guessit_fallback",
                "original_filepath": filepath # Store original path for future identification
            }
            
            # Add TV/anime specific data if available
            if season is not None:
                fallback_data["season"] = season
            if episode is not None:
                fallback_data["episode"] = episode
                
            # Add year if available
            if 'year' in guessit_info:
                fallback_data["year"] = guessit_info['year']
                
            logger.info(f"Storing guessit fallback data for '{title}': {media_type}" +
                        (f", S{season}" if season is not None else "") +
                        (f", E{episode}" if episode is not None else ""))
            
            self.media_cache.set(cache_key, fallback_data)
            
            # Update current tracking state
            if self.currently_tracking and not self.simkl_id:
                self.movie_name = title
                self.media_type = media_type
                self.season = season
                self.episode = episode
                
        except Exception as e:
            logger.error(f"Error storing guessit fallback data: {e}", exc_info=True)
