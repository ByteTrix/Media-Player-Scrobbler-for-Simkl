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
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import threading
from collections import deque
from requests.exceptions import RequestException

# Import necessary functions and libraries
from simkl_mps.simkl_api import (
    is_internet_connected,
    get_movie_details,
    get_show_details,
    search_file,
    add_to_history,
    search_movie
)
from simkl_mps.backlog_cleaner import BacklogCleaner
from simkl_mps.window_detection import parse_movie_title, parse_filename_from_path, is_video_player
from simkl_mps.media_cache import MediaCache

logger = logging.getLogger(__name__)
try:
    import guessit
except ImportError:
    logger.error("The 'guessit' library is required for episode detection. Please install it: pip install guessit")
    guessit = None

from simkl_mps.utils.constants import PLAYING, PAUSED, STOPPED, DEFAULT_POLL_INTERVAL
from simkl_mps.config_manager import get_setting, DEFAULT_THRESHOLD
from simkl_mps.watch_history_manager import WatchHistoryManager

class MediaScrobbler:
    """Handles the scrobbling of media (movies, episodes) to SIMKL"""

    def __init__(self, app_data_dir, client_id=None, access_token=None, testing_mode=False):
        self.app_data_dir = pathlib.Path(app_data_dir) # Ensure it's a Path object
        self.client_id = client_id
        self.access_token = access_token
        self.testing_mode = testing_mode
        self.currently_tracking = None
        self.track_start_time = None
        self.notification_callback = None
        self._processing_backlog_items = set() # Tracks items currently being processed by process_backlog
        self._processing_lock = threading.Lock() # Lock for accessing _processing_backlog_items

        self.playback_log_path = self.app_data_dir / "playback_log.jsonl"

        self.backlog_cleaner = BacklogCleaner(
            app_data_dir=self.app_data_dir,
            backlog_file="backlog.json"
        )

        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.state = STOPPED
        self.previous_state = STOPPED
        self.estimated_duration = None
        self.simkl_id = None
        self.movie_name = None # Official title from Simkl (movie title or show title)
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
        self._last_connection_error_log = {} # Tracks last log time for player connection errors

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
                logger.error(f"Failed to create RotatingFileHandler for PlaybackLogger at {self.playback_log_file}: {e}", exc_info=True)

        self._last_window_info = None # Store last window info for player integrations
        self._vlc_integration = None
        self._mpc_integration = None
        self._mpcqt_integration = None
        self._mpv_integration = None
        self._mpv_wrapper_integration = None
        self.watch_history = WatchHistoryManager(self.app_data_dir) # Initialize watch history manager

    def set_notification_callback(self, callback):
        """Set a callback function for notifications"""
        self.notification_callback = callback

    def _send_notification(self, title, message, online_only=False, offline_only=False):
        """
        Safely sends a notification if the callback is set, respecting online/offline constraints.
        """
        if self.notification_callback:
            connected = is_internet_connected()
            if (online_only and not connected) or \
               (offline_only and connected):
                logger.debug(f"Notification '{title}' suppressed (Online: {connected}, Constraint: online_only={online_only}, offline_only={offline_only}).")
                return

            try:
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
            "media_type": self.media_type,
            "season": self.season,
            "episode": self.episode,
            "state": self.state,
            "watch_time_accumulated_seconds": round(self.watch_time, 2),
            "current_position_seconds": self.current_position_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "estimated_duration_seconds": self.estimated_duration,
            "completion_percent_accumulated": self._calculate_percentage(use_accumulated=True),
            "completion_percent_position": self._calculate_percentage(use_position=True),
            "is_complete_flag": self.completed,
            "filepath": self.current_filepath,
        }
        if extra_data:
            log_entry.update(extra_data)

        try:
            self.playback_logger.info(json.dumps(log_entry))
        except Exception as e:
            logger.error(f"Failed to log playback event: {e} - Data: {log_entry}", exc_info=True)


    def _get_player_integration(self, process_name_lower):
        """Lazy-loads and returns the appropriate player integration module."""
        if 'vlc' in process_name_lower:
            if not self._vlc_integration:
                from simkl_mps.players import VLCIntegration
                self._vlc_integration = VLCIntegration()
            return self._vlc_integration
        if any(p in process_name_lower for p in ['mpc-hc.exe', 'mpc-hc64.exe', 'mpc-be.exe', 'mpc-be64.exe']):
            if not self._mpc_integration:
                from simkl_mps.players.mpc import MPCIntegration
                self._mpc_integration = MPCIntegration()
            return self._mpc_integration
        if 'mpc-qt' in process_name_lower:
            if not self._mpcqt_integration:
                from simkl_mps.players.mpcqt import MPCQTIntegration
                self._mpcqt_integration = MPCQTIntegration()
            return self._mpcqt_integration
        if 'mpv' in process_name_lower: # Covers standalone mpv
            if not self._mpv_integration:
                from simkl_mps.players.mpv import MPVIntegration
                self._mpv_integration = MPVIntegration()
            return self._mpv_integration
        
        # Fallback for MPV wrappers (must be checked after standalone mpv)
        if not self._mpv_wrapper_integration:
            from simkl_mps.players.mpv_wrappers import MPVWrapperIntegration
            self._mpv_wrapper_integration = MPVWrapperIntegration()
        if self._mpv_wrapper_integration.is_mpv_wrapper(process_name_lower):
            return self._mpv_wrapper_integration
            
        return None

    def get_player_position_duration(self, process_name):
        """
        Get current position and total duration from supported media players.
        """
        position, duration = None, None
        if not process_name:
            return None, None
            
        process_name_lower = process_name.lower()
        integration = self._get_player_integration(process_name_lower)

        if integration:
            try:
                player_name = integration.__class__.__name__.replace("Integration", "")
                logger.debug(f"{player_name} detected: {process_name}")
                position, duration = integration.get_position_duration(process_name)
                if position is not None and duration is not None:
                    if isinstance(position, (int, float)) and isinstance(duration, (int, float)) and duration > 0 and position >= 0:
                        position = min(position, duration) # Cap position at duration
                        logger.debug(f"Retrieved from {player_name}: pos={position:.2f}s, dur={duration:.2f}s")
                        return round(position, 2), round(duration, 2)
                    else:
                        logger.debug(f"Invalid pos/dur from {player_name}: pos={position}, dur={duration}")
                else:
                    logger.debug(f"{player_name} integration couldn't get position/duration.")
            except RequestException as e:
                now = time.time()
                last_log_time = self._last_connection_error_log.get(process_name, 0)
                if now - last_log_time > 60: # Log connection errors at most once per minute per player
                    logger.warning(f"Could not connect to {process_name} web interface. Error: {e}")
                    self._last_connection_error_log[process_name] = now
            except Exception as e:
                logger.error(f"Error getting pos/dur from {process_name} ({getattr(integration, '__class__', type(integration)).__name__}): {e}", exc_info=True)
        
        return None, None


    def get_current_filepath(self, process_name):
        """
        Get the current filepath of the media being played from player integrations.
        """
        if not process_name:
            return None
        
        process_name_lower = process_name.lower()
        integration = self._get_player_integration(process_name_lower)
        
        if integration and hasattr(integration, 'get_current_filepath'):
            try:
                filepath = integration.get_current_filepath(process_name)
                if filepath:
                    player_name = integration.__class__.__name__.replace("Integration", "")
                    logger.debug(f"Retrieved filepath from {player_name}: {filepath}")
                    return filepath
            except Exception as e:
                logger.error(f"Error getting filepath from {process_name} ({integration.__class__.__name__}): {e}", exc_info=True)
        return None

    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token

    def process_window(self, window_info):
        """Process the current window and update scrobbling state"""
        self._last_window_info = window_info

        if not is_video_player(window_info):
            if self.currently_tracking:
                logger.info("Media playback ended: Player closed or changed focus.")
                self.stop_tracking()
            return None

        process_name = window_info.get('process_name')
        filepath = None
        detected_title = None # This will be the raw title from filename or window
        detection_source = "unknown"
        detection_details = None

        if process_name:
            filepath = self.get_current_filepath(process_name)
            if filepath:
                detected_title = parse_filename_from_path(filepath)
                if detected_title:
                    detection_source = "filename"
                    detection_details = os.path.basename(filepath)

        if not detected_title:
            raw_window_title = window_info.get('title', '')
            detected_title = parse_movie_title(raw_window_title)
            if detected_title:
                detection_source = "window_title"
                detection_details = raw_window_title

        if not detected_title:
            if self.currently_tracking:
                logger.debug(f"Unable to identify media in '{window_info.get('title', '')}' or from filepath.")
                self.stop_tracking()
            return None

        identified_type_guessit = 'movie' # Default assumption
        guessit_info = None
        if filepath and guessit:
            try:
                filename_for_guessit = os.path.basename(filepath)
                guessit_info = guessit.guessit(filename_for_guessit)
                identified_type_guessit = guessit_info.get('type', 'movie') # 'movie' or 'episode'
                logger.debug(f"Guessit identified: '{identified_type_guessit}' from '{filename_for_guessit}'. Info: {guessit_info}")
            except Exception as e:
                logger.warning(f"Guessit failed to parse '{filepath}': {e}")

        if self.currently_tracking and self.currently_tracking != detected_title:
            logger.info(f"Media change detected: '{detected_title}' now playing (was '{self.currently_tracking}').")
            self.stop_tracking()

        if not self.currently_tracking:
            log_prefix = f"Detected {identified_type_guessit}"
            if detection_source == "filename":
                logger.info(f"{log_prefix} from filename: '{detected_title}' (from: {detection_details})")
            elif detection_source == "window_title":
                logger.info(f"{log_prefix} from window title: '{detected_title}'")
            else: # Should not happen if detected_title is set
                logger.info(f"Starting tracking for '{detected_title}' (type: {identified_type_guessit})")

            self._start_new_media_item(detected_title, filepath, identified_type_guessit, guessit_info)


        self._update_tracking(window_info) # Update tracking state, position, etc.

        return {
            "title": detected_title, # Raw detected title
            "simkl_id": self.simkl_id,
            "movie_name": self.movie_name, # Simkl official title
            "source": detection_source,
            "detection_details": detection_details
        }

    def _start_new_media_item(self, raw_title, filepath, initial_media_type_guess, guessit_info=None):
        """Starts tracking a new media item, sets initial state, and attempts identification."""
        if not raw_title or raw_title.lower() in ["audio", "video", "media", "no file"]:
            logger.info(f"Ignoring generic title for tracking: '{raw_title}'")
            return

        logger.info(f"Starting media tracking for raw title: '{raw_title}'")
        self.currently_tracking = raw_title # Store raw title
        self.current_filepath = filepath
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.watch_time = 0
        self.state = PLAYING
        self.previous_state = STOPPED
        self.completed = False
        self.current_position_seconds = 0
        self.total_duration_seconds = None # Will be updated by player or API
        self.estimated_duration = None

        # Reset Simkl-specific details for the new item
        self.simkl_id = None
        self.movie_name = None # Official Simkl title
        self.media_type = initial_media_type_guess # Initial guess, will be refined by Simkl
        self.season = None
        self.episode = None

        self._send_notification("Tracking Started", f"Tracking: '{raw_title}'", offline_only=True)

        # Attempt initial identification
        cache_key = os.path.basename(filepath).lower() if filepath else raw_title.lower()
        cached_info = self.media_cache.get(cache_key)

        if cached_info and cached_info.get('simkl_id') and not str(cached_info.get('simkl_id')).startswith("temp_"):
            logger.info(f"Found cached Simkl info for '{raw_title}': ID {cached_info['simkl_id']}")
            self._apply_cached_info_to_state(cached_info)
        elif is_internet_connected():
            if initial_media_type_guess == 'episode' and filepath:
                logger.info(f"Attempting Simkl file search for episode: '{raw_title}' from '{filepath}'")
                self._identify_media_from_filepath(filepath, guessit_info)
            elif initial_media_type_guess == 'movie':
                logger.info(f"Attempting Simkl movie title search for: '{raw_title}'")
                self._identify_movie(raw_title) # Pass raw_title for movie search
            # If neither, it will be attempted in _update_tracking if still unidentified
        else: # Offline
            logger.info(f"Offline: Media identification deferred for '{raw_title}'. Will use guessit/filename info if available.")
            if filepath: # Only cache if we have a filepath
                self._cache_initial_offline_info(raw_title, filepath, initial_media_type_guess, guessit_info)
            else:
                logger.info("Offline: Cannot cache basic info - filepath not available.")


    def _cache_initial_offline_info(self, raw_title, filepath, media_type_guess, guessit_info):
        """Caches basic info when detected offline before full Simkl ID."""
        offline_cache_key = os.path.basename(filepath).lower()
        
        year_for_cache = None
        if guessit_info and isinstance(guessit_info, dict) and 'year' in guessit_info:
            year_for_cache = guessit_info.get('year')
        elif raw_title:
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', raw_title)
            if year_match:
                try:
                    year_for_cache = int(year_match.group(1))
                except ValueError:
                    pass # Keep year_for_cache as None

        initial_offline_cache_data = {
            "title": raw_title,
            "year": year_for_cache,
            "filepath": filepath,
            "type": media_type_guess, # 'movie' or 'episode' from guessit
            "source": "offline_playback_detection",
        }
        if media_type_guess == 'episode' and guessit_info:
            initial_offline_cache_data["season"] = guessit_info.get('season')
            initial_offline_cache_data["episode"] = guessit_info.get('episode')


        existing_entry = self.media_cache.get(offline_cache_key)
        if existing_entry:
            if existing_entry.get('simkl_id') and not str(existing_entry.get('simkl_id')).startswith("temp_"):
                logger.info(f"Offline: '{raw_title}' (key: {offline_cache_key}) already has a Simkl ID. Skipping initial offline cache.")
                return
            if 'simkl_search' in str(existing_entry.get('source','')):
                logger.info(f"Offline: '{raw_title}' (key: {offline_cache_key}) has API-sourced cache. Skipping initial offline cache.")
                return
        
        self.media_cache.set(offline_cache_key, initial_offline_cache_data)
        logger.info(f"Offline: Cached basic info for '{raw_title}'. Key: {offline_cache_key}. Data: {initial_offline_cache_data}")
        self._send_notification(
            f"Offline {media_type_guess.capitalize()} Detected",
            f"Cached basic info for: '{raw_title}'",
            offline_only=True
        )

    def _apply_cached_info_to_state(self, cached_info):
        """Applies detailed info from cache to the current scrobbler state."""
        self.simkl_id = cached_info.get('simkl_id')
        self.movie_name = cached_info.get('movie_name', self.currently_tracking) # Official title
        self.media_type = cached_info.get('type') # Simkl type: 'movie', 'show', 'anime'
        self.season = cached_info.get('season')
        self.episode = cached_info.get('episode')
        
        if 'duration_seconds' in cached_info and self.total_duration_seconds is None:
            self.total_duration_seconds = cached_info['duration_seconds']
            self.estimated_duration = self.total_duration_seconds
            logger.info(f"Set duration from cache for '{self.movie_name}': {self.total_duration_seconds}s")
        
        # Send notification for cached identification if actively tracking this item
        if self.currently_tracking and self.movie_name and self.simkl_id:
            display_text = f"Playing: '{self.movie_name}'"
            if self.media_type in ['show', 'anime']:
                if self.season is not None and self.episode is not None:
                    display_text += f" S{self.season}E{self.episode}"
                elif self.media_type == 'anime' and self.episode is not None: # Anime might only have episode
                    display_text += f" E{self.episode}"
            elif self.media_type == 'movie' and cached_info.get('year'):
                display_text += f" ({cached_info.get('year')})"
            
            self._send_notification(
                f"{self.media_type.capitalize()} Identified (Cache)",
                display_text,
                online_only=True # Notifications for confirmed IDs are online-only
            )

    def _start_new_movie(self, movie_title):
        """Deprecated. Use _start_new_media_item instead."""
        # This method is essentially replaced by the richer _start_new_media_item.
        # Kept for a moment to ensure no direct calls were missed, but should be removed.
        logger.warning("_start_new_movie is deprecated. Called with: " + movie_title)
        # For safety, redirect to the new method with some defaults if called.
        self._start_new_media_item(movie_title, None, 'movie')


    def _update_tracking(self, window_info=None):
        """Update tracking for the current media, including position, duration, and state."""
        if not self.currently_tracking or not self.last_update_time:
            return None

        current_time = time.time()
        elapsed_since_last_update = current_time - self.last_update_time
        if elapsed_since_last_update < 0: elapsed_since_last_update = 0 # Clock drift?
        
        # Update filepath if it changed
        process_name = window_info.get('process_name') if window_info else None
        if process_name:
            try:
                current_player_filepath = self.get_current_filepath(process_name)
                if current_player_filepath and self.current_filepath != current_player_filepath:
                    logger.info(f"Filepath changed from '{self.current_filepath}' to '{current_player_filepath}'")
                    # This might indicate a new media item, but process_window handles new item detection.
                    # Here, we just update it if it's for the *same* tracked raw_title.
                    self.current_filepath = current_player_filepath
            except Exception as e:
                 logger.error(f"Error getting filepath during update: {e}", exc_info=False)

        # Get position and duration from player
        pos, dur = None, None
        if process_name:
            pos, dur = self.get_player_position_duration(process_name)

        position_updated_from_player = False
        if pos is not None and dur is not None and dur > 0:
            if self.total_duration_seconds is None or abs(self.total_duration_seconds - dur) > 2: # Allow small variance
                logger.info(f"Updating total duration for '{self.movie_name or self.currently_tracking}' from {self.total_duration_seconds}s to {dur}s via player.")
                self.total_duration_seconds = dur
                self.estimated_duration = dur # Player duration is a good estimate

            # Detect seeks
            if self.state == PLAYING and self.current_position_seconds is not None:
                # Compare current player position with expected position based on elapsed time
                expected_pos_increase = elapsed_since_last_update
                actual_pos_increase = pos - self.current_position_seconds
                # If the difference between actual and expected increase is significant, it's likely a seek
                # Threshold for seek detection (e.g., 2 seconds)
                seek_threshold = 2.0 
                if abs(actual_pos_increase - expected_pos_increase) > seek_threshold and elapsed_since_last_update > 0.1:
                    logger.info(f"Seek detected for '{self.movie_name or self.currently_tracking}': Position changed by {actual_pos_increase:.1f}s in {elapsed_since_last_update:.1f}s (Expected ~{expected_pos_increase:.1f}s).")
                    self._log_playback_event("seek", {"previous_position_seconds": round(self.current_position_seconds, 2), "new_position_seconds": pos})

            self.current_position_seconds = pos
            position_updated_from_player = True
        
        # Determine current playback state (PLAYING or PAUSED)
        new_state = PAUSED if self._detect_pause(window_info) else PLAYING

        # Accumulate watch time if playing
        if self.state == PLAYING:
            # Cap elapsed time to avoid huge jumps if app was suspended
            # Useful if position_updated_from_player is False, otherwise current_position_seconds is more reliable
            safe_elapsed = min(elapsed_since_last_update, 30.0) # Max 30s jump for accumulated time
            self.watch_time += safe_elapsed

        # Handle state changes
        state_changed = (new_state != self.state)
        if state_changed:
            logger.info(f"Playback state for '{self.movie_name or self.currently_tracking}' changed: {self.state} -> {new_state}")
            self.previous_state = self.state
            self.state = new_state
            self._log_playback_event("state_change", {"previous_state": self.previous_state})

        self.last_update_time = current_time

        # Attempt identification if Simkl ID is still missing
        if not self.simkl_id and self.currently_tracking:
            cache_key_for_lookup = os.path.basename(self.current_filepath).lower() if self.current_filepath else self.currently_tracking.lower()
            cached_info = self.media_cache.get(cache_key_for_lookup)
            if cached_info and cached_info.get('simkl_id') and not str(cached_info.get('simkl_id')).startswith("temp_"):
                logger.info(f"Found cached Simkl info for '{self.currently_tracking}' during update: ID {cached_info['simkl_id']}")
                self._apply_cached_info_to_state(cached_info) # This updates self.simkl_id, self.movie_name etc.
            elif is_internet_connected():
                if self.media_type == 'episode' and self.current_filepath: # media_type is initial guessit type
                    self._identify_media_from_filepath(self.current_filepath)
                elif self.media_type == 'movie': # media_type is initial guessit type
                    self._identify_movie(self.currently_tracking) # Use raw title for movie search
                # If guessit type was neither, or identification failed, it remains unknown for now.
            # If identification was successful, self.simkl_id etc. are now set.

        # Log progress periodically or on significant changes
        # Use self.last_scrobble_time to track when the last "scrobble_update" event was logged
        if state_changed or position_updated_from_player or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL):
            self._log_playback_event("progress_update") # Generic progress event
            # self.last_scrobble_time = current_time # Update this only when returning scrobble data below

        # Check completion threshold
        if not self.completed and (current_time - self.last_progress_check > 5): # Check every 5s
            completion_pct = self._calculate_percentage(use_position=position_updated_from_player)
            if completion_pct and completion_pct >= self.completion_threshold:
                display_title_for_log = self.movie_name or self.currently_tracking
                logger.info(f"Completion threshold ({self.completion_threshold}%) met for '{display_title_for_log}' at {completion_pct:.2f}%.")
                self._log_playback_event("completion_threshold_reached")
                self._attempt_add_to_history() # This handles setting self.completed
            self.last_progress_check = current_time

        # Determine if a scrobble update should be returned (e.g., for UI)
        # This is different from just logging progress_update.
        should_return_scrobble_data = state_changed or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        if should_return_scrobble_data:
            self.last_scrobble_time = current_time # Update time of last returned scrobble data
            # self._log_playback_event("scrobble_update_returned") # Optional: Differentiate logged progress from returned data
            return {
                "raw_title": self.currently_tracking,
                "movie_name": self.movie_name, # Official Simkl title
                "simkl_id": self.simkl_id,
                "media_type": self.media_type, # Simkl media type
                "season": self.season,
                "episode": self.episode,
                "state": self.state,
                "progress": self._calculate_percentage(use_position=position_updated_from_player),
                "watched_seconds": round(self.watch_time, 2),
                "current_position_seconds": self.current_position_seconds,
                "total_duration_seconds": self.total_duration_seconds,
                "estimated_duration_seconds": self.estimated_duration
            }
        return None


    def _calculate_percentage(self, use_position=False, use_accumulated=False):
        """Calculates completion percentage. Prefers position/duration if use_position is True and data is valid."""
        percentage = None
        # Prioritize position-based calculation if requested and valid data exists
        if use_position and self.current_position_seconds is not None and \
           self.total_duration_seconds is not None and self.total_duration_seconds > 0:
            percentage = min(100, (self.current_position_seconds / self.total_duration_seconds) * 100)
        # Fallback to accumulated watch time if position-based is not used or not possible,
        # or if use_accumulated is explicitly True (though use_position usually takes precedence)
        elif (use_accumulated or not use_position) and \
             self.total_duration_seconds is not None and self.total_duration_seconds > 0:
            percentage = min(100, (self.watch_time / self.total_duration_seconds) * 100)
        
        return round(percentage, 2) if percentage is not None else None


    def _detect_pause(self, window_info):
        """Detect if playback is paused based on window title keywords."""
        if window_info and window_info.get('title'):
            title_lower = window_info['title'].lower()
            # More robust pause detection might involve checking player status directly if available
            # For now, relying on title keywords
            pause_keywords = ["paused", "- pause", "[paused]"]
            if any(keyword in title_lower for keyword in pause_keywords):
                return True
        return False

    def stop_tracking(self):
        """Stop tracking the current media item and reset state."""
        if not self.currently_tracking:
            return None

        final_raw_title = self.currently_tracking
        final_movie_name = self.movie_name
        final_simkl_id = self.simkl_id
        final_media_type = self.media_type
        final_season = self.season
        final_episode = self.episode
        final_state_on_stop = self.state # State just before stopping
        final_pos = self.current_position_seconds
        final_watch_time = self.watch_time
        final_total_duration = self.total_duration_seconds
        final_estimated_duration = self.estimated_duration
        
        # Check completion one last time before stopping
        # Use a stricter check if it wasn't already marked complete by _update_tracking
        if not self.completed:
            final_completion_pct = self._calculate_percentage(use_position=True) # Prefer position at stop
            if final_completion_pct and final_completion_pct >= self.completion_threshold:
                logger.info(f"'{final_movie_name or final_raw_title}' met completion threshold upon stopping.")
                # Attempt to add to history if not already done
                self._attempt_add_to_history() # This might set self.completed

        log_message = f"Tracking stopped for '{final_movie_name or final_raw_title}'"
        if self.completed:
            log_message += " (marked as completed/synced)."
        logger.info(log_message)

        self._log_playback_event("stop_tracking", extra_data={
            "final_state_before_stop": final_state_on_stop,
            "final_position_seconds": final_pos,
            "final_watch_time_seconds": round(final_watch_time, 2)
        })

        # Reset all tracking variables
        self.currently_tracking = None
        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.state = STOPPED
        self.previous_state = STOPPED # Should reflect the new STOPPED state
        self.estimated_duration = None
        self.simkl_id = None
        self.movie_name = None
        self.completed = False # Reset completion for the next item
        self.current_position_seconds = 0
        self.total_duration_seconds = None
        self.current_filepath = None
        self.media_type = None
        self.season = None
        self.episode = None
        # self.last_backlog_attempt_time should persist for items, not cleared globally here.

        return {
            "raw_title": final_raw_title,
            "movie_name": final_movie_name,
            "simkl_id": final_simkl_id,
            "media_type": final_media_type,
            "season": final_season,
            "episode": final_episode,
            "state": STOPPED, # Final state is always STOPPED
            "progress": self._calculate_percentage(use_position=True) or self._calculate_percentage(use_accumulated=True), # Recalculate with final values
            "watched_seconds": round(final_watch_time, 2),
            "current_position_seconds": final_pos,
            "total_duration_seconds": final_total_duration,
            "estimated_duration_seconds": final_estimated_duration
        }

    def _identify_media_from_filepath(self, filepath, guessit_info=None):
        """
        Identifies media (movie or episode) using Simkl /search/file and updates state.
        Handles offline fallback using guessit.
        """
        if not self.client_id:
            logger.warning("Cannot identify media from filepath: Missing Client ID.")
            return

        cache_key = os.path.basename(filepath).lower()
        cached_info = self.media_cache.get(cache_key)

        if cached_info and cached_info.get('simkl_id') and not str(cached_info.get('simkl_id')).startswith("temp_"):
            logger.info(f"Using cached Simkl info for file '{cache_key}': ID {cached_info['simkl_id']}")
            self._apply_cached_info_to_state(cached_info)
            return

        if not is_internet_connected():
            logger.warning(f"Offline: Cannot identify '{filepath}' via Simkl API. Using guessit fallback if available.")
            self._handle_offline_identification_fallback(filepath, guessit_info, cache_key)
            return

        try:
            logger.info(f"Querying Simkl API with file: '{filepath}'")
            result = search_file(filepath, self.client_id)

            if result:
                self._process_simkl_search_result(result, filepath, cache_key, "simkl_search_file")
            else:
                logger.info(f"Simkl /search/file found no match for '{filepath}'. Storing guessit fallback if available.")
                self._store_guessit_fallback_data(filepath, guessit_info, cache_key)

        except RequestException as e:
            logger.warning(f"Network error during Simkl file identification for '{filepath}': {e}")
            if self.media_type == 'episode': # media_type here is the initial guessit type
                 self.backlog_cleaner.add(filepath, os.path.basename(filepath), additional_data={"type": "episode", "original_filepath": filepath, "source": "failed_file_search"})
            self._store_guessit_fallback_data(filepath, guessit_info, cache_key) # Fallback on network error
        except Exception as e:
            logger.error(f"Error during Simkl file identification for '{filepath}': {e}", exc_info=True)
            self._store_guessit_fallback_data(filepath, guessit_info, cache_key) # Fallback on other errors

    def _handle_offline_identification_fallback(self, filepath, guessit_info, cache_key):
        """Handles offline identification using guessit."""
        if not guessit:
            logger.warning("Guessit library not available for offline fallback.")
            return

        try:
            info_to_use = guessit_info
            if not info_to_use and filepath: # If no pre-parsed info, try to parse now
                info_to_use = guessit.guessit(os.path.basename(filepath))
            
            if isinstance(info_to_use, dict) and info_to_use.get('title'):
                self.media_type = info_to_use.get('type', 'episode') # Guessit 'episode' or 'movie'
                self.movie_name = info_to_use.get('title') # This becomes the stand-in for official title offline
                self.season = info_to_use.get('season')
                self.episode = info_to_use.get('episode')
                # Simkl ID remains None

                logger.info(f"Offline fallback (guessit): Title='{self.movie_name}', Type='{self.media_type}', "
                            f"S={self.season if self.season is not None else 'N/A'}, "
                            f"E={self.episode if self.episode is not None else 'N/A'}")
                
                self.media_cache.set(cache_key, {
                    "movie_name": self.movie_name, # Using movie_name for consistency
                    "type": self.media_type, # Store guessit type
                    "season": self.season,
                    "episode": self.episode,
                    "year": info_to_use.get('year'),
                    "source": "guessit_fallback_offline",
                    "original_filepath": filepath
                })
                
                display_text = f"Using Filename Data: '{self.movie_name}'"
                if self.media_type == 'episode' and self.season is not None and self.episode is not None:
                    display_text += f" S{self.season}E{self.episode}"
                self._send_notification("Offline Media Detection", display_text, offline_only=True)
            else:
                logger.warning(f"Guessit couldn't extract valid title from '{filepath}' for offline fallback.")
        except Exception as e:
            logger.error(f"Error using guessit for offline fallback: {e}", exc_info=True)

    def _process_simkl_search_result(self, result, original_input, cache_key, source_description):
        """Processes a search result from Simkl (either file or title search) and updates state."""
        media_item = None # This will hold the 'movie' or 'show' object
        simkl_type = None # This will be 'movie', 'show', or 'anime' from Simkl
        episode_details_from_api = {}

        if 'show' in result:
            media_item = result['show']
            simkl_type = media_item.get('type', 'show') # Could be 'anime'
            episode_details_from_api = result.get('episode', {})
        elif 'movie' in result:
            media_item = result['movie']
            simkl_type = 'movie'
        elif isinstance(result, list) and result: # Handle list results (e.g., from search_movie)
            # Assume the first result is the most relevant
            # Need to check if the first item itself contains 'movie' or is the movie object
            first_result = result[0]
            if 'movie' in first_result:
                media_item = first_result['movie']
                simkl_type = 'movie'
            elif first_result.get('type') == 'movie':
                media_item = first_result 
                simkl_type = 'movie'
            else:
                logger.warning(f"Unknown structure in first search result: {first_result}")
                return
        elif isinstance(result, dict) and result.get('type') == 'movie': # Direct movie object from search_movie
            media_item = result
            simkl_type = 'movie'
        else:
            logger.warning(f"Simkl search response missing expected 'movie' or 'show' fields: {result}")
            return

        if not (media_item and 'ids' in media_item and media_item['ids'].get('simkl')):
            logger.warning(f"Simkl search found a result but no valid Simkl ID was present. Media item: {media_item}")
            return

        self.simkl_id = media_item['ids']['simkl']
        self.movie_name = media_item.get('title', self.currently_tracking) # Official title
        self.media_type = simkl_type # Simkl's type ('movie', 'show', 'anime')

        # Episode/Season for shows/anime from /search/file result
        self.season = None
        self.episode = None
        if simkl_type in ['show', 'anime']:
            if 'season' in episode_details_from_api:
                self.season = episode_details_from_api['season']
            if 'episode' in episode_details_from_api:
                self.episode = episode_details_from_api['episode']
        
        year = media_item.get('year')
        runtime_minutes = media_item.get('runtime') or episode_details_from_api.get('runtime')
        
        log_parts = [
            f"Simkl identified '{original_input}' as: Type='{self.media_type}'",
            f"Title='{self.movie_name}'",
            f"ID={self.simkl_id}",
            f"Year={year}" if year else "",
        ]
        if self.media_type in ['show', 'anime']:
            if self.season is not None: log_parts.append(f"Season={self.season}")
            if self.episode is not None: log_parts.append(f"Episode={self.episode}")
        
        logger.info(", ".join(filter(None, log_parts)))

        # Prepare arguments for cache_media_info, potentially overriding with get_show_details
        # These are initialized with values from the search_file result (media_item, episode_details_from_api)
        # self.simkl_id, self.movie_name, self.media_type, self.season, self.episode, year, runtime_minutes are already set.
        
        final_simkl_id_for_cache = self.simkl_id
        final_display_name_for_cache = self.movie_name
        final_media_type_for_cache = self.media_type
        final_season_for_cache = self.season # Episode specific, from search_file
        final_episode_for_cache = self.episode # Episode specific, from search_file
        final_year_for_cache = year
        final_runtime_minutes_for_cache = runtime_minutes # Already considers episode runtime from search_file
        final_api_ids_for_cache = media_item.get('ids', {})
        final_overview_for_cache = media_item.get('overview') or episode_details_from_api.get('overview')
        final_poster_url_for_cache = media_item.get('poster') or episode_details_from_api.get('poster')
        # Default _api_full_details to the media_item from search_file result
        final_api_full_details_for_cache = media_item

        if final_media_type_for_cache in ['show', 'anime'] and final_simkl_id_for_cache and self.client_id and self.access_token:
            if is_internet_connected():
                logger.info(f"Fetching full show details for '{final_display_name_for_cache}' (ID: {final_simkl_id_for_cache}) to enhance cache.")
                detailed_show_info_api = get_show_details(final_simkl_id_for_cache, self.client_id, self.access_token)
                if detailed_show_info_api:
                    logger.info(f"Successfully fetched full details for show/anime ID {final_simkl_id_for_cache}.")
                    final_api_full_details_for_cache = detailed_show_info_api # Use this richer data for cache

                    # Update arguments for cache_media_info with richer data from get_show_details
                    final_display_name_for_cache = detailed_show_info_api.get('title', final_display_name_for_cache)
                    final_media_type_for_cache = detailed_show_info_api.get('type', final_media_type_for_cache) # API's type is canonical
                    final_year_for_cache = detailed_show_info_api.get('year', final_year_for_cache)
                    
                    # Overview: Prefer show's overview if episode overview from search_file was empty or not present
                    episode_overview_from_search = episode_details_from_api.get('overview')
                    if not (episode_overview_from_search and episode_overview_from_search.strip()):
                        final_overview_for_cache = detailed_show_info_api.get('overview', final_overview_for_cache)
                    # else, keep episode_overview_from_search if it was valid
                    
                    # Poster: Prefer poster_url from get_show_details if available
                    final_poster_url_for_cache = detailed_show_info_api.get('poster_url') or \
                                                 detailed_show_info_api.get('poster') or \
                                                 final_poster_url_for_cache
                    
                    # IDs: Merge, prioritizing get_show_details (which should include anilist_id if my prev changes worked)
                    final_api_ids_for_cache = {**final_api_ids_for_cache, **detailed_show_info_api.get('ids', {})}

                    # Runtime: get_show_details provides show's typical runtime.
                    # final_runtime_minutes_for_cache already has episode-specific runtime from search_file if available.
                    # Only update if search_file didn't provide episode runtime and get_show_details provides a show runtime.
                    if not episode_details_from_api.get('runtime') and detailed_show_info_api.get('runtime'):
                        try:
                            final_runtime_minutes_for_cache = int(detailed_show_info_api.get('runtime'))
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse runtime from get_show_details: {detailed_show_info_api.get('runtime')}")
                else:
                    logger.warning(f"Failed to fetch full show details for ID {final_simkl_id_for_cache}. Using data from search/file.")
            else:
                logger.info(f"Offline: Cannot fetch full show details for ID {final_simkl_id_for_cache}. Using data from search/file.")

        original_filepath_for_cache = None
        if isinstance(original_input, str) and (os.path.sep in original_input or (os.path.altsep and os.path.altsep in original_input)):
            original_filepath_for_cache = original_input

        self.cache_media_info(
            original_title_key=cache_key,
            simkl_id=final_simkl_id_for_cache,
            display_name=final_display_name_for_cache,
            media_type=final_media_type_for_cache,
            season=final_season_for_cache, # Season/Episode are from search_file (episode context)
            episode=final_episode_for_cache, # Season/Episode are from search_file (episode context)
            year=final_year_for_cache,
            runtime_minutes=final_runtime_minutes_for_cache,
            api_ids=final_api_ids_for_cache,
            overview=final_overview_for_cache,
            poster_url=final_poster_url_for_cache,
            source_description=source_description,
            original_filepath_if_any=original_filepath_for_cache,
            _api_full_details=final_api_full_details_for_cache # This now passes the richer details
        )
        
        # Notification logic: cache_media_info handles notifications if it updates the *currently tracked* item's state.
        # The existing notification below might be slightly delayed if cache_media_info updates self.movie_name etc.
        # For now, let's keep it to ensure a notification is sent.
        display_text = f"Playing: '{self.movie_name}'" # self.movie_name might have been updated by cache_media_info
        if self.media_type in ['show', 'anime']: # self.media_type might have been updated
            if self.season is not None and self.episode is not None: display_text += f" S{self.season}E{self.episode}"
            elif self.media_type == 'anime' and self.episode is not None: display_text += f" E{self.episode}"
        elif self.media_type == 'movie' and final_year_for_cache: display_text += f" ({final_year_for_cache})" # Use potentially updated year
        
        self._send_notification(f"{self.media_type.capitalize()} Identified", display_text, online_only=True)
        self._clear_backlog_entry_if_temp_identified()

    def _identify_movie(self, title_to_search):
        """
        Identifies a movie using Simkl /search/movie.
        `title_to_search` is the raw title detected from filename or window.
        """
        if not self.client_id or not self.access_token:
            logger.warning("Cannot identify movie by title: Missing Client ID or Access Token.")
            return

        # If we already have a Simkl ID for the currently tracking item, skip redundant API calls
        if self.simkl_id and self.movie_name and self.currently_tracking == title_to_search:
            logger.info(f"Skipping redundant title search for '{title_to_search}': Already identified as '{self.movie_name}' (ID: {self.simkl_id})")
            return

        cache_key = title_to_search.lower() # Use raw title for this initial cache lookup
        cached_info = self.media_cache.get(cache_key)
        if cached_info and cached_info.get('simkl_id') and not str(cached_info.get('simkl_id')).startswith("temp_"):
            logger.info(f"Using cached Simkl info for movie title '{title_to_search}': ID {cached_info['simkl_id']}")
            self._apply_cached_info_to_state(cached_info)
            return
        
        if not is_internet_connected():
            logger.warning(f"Offline: Cannot identify movie '{title_to_search}' via Simkl API.")
            # Add to backlog for later identification if not already handled by _cache_initial_offline_info
            # _cache_initial_offline_info handles simple offline caching.
            # This specific backlog add is for items that *need online identification*.
            backlog_id_key = f"identify_{cache_key}"
            if not self.backlog_cleaner.get_pending().get(backlog_id_key): # Avoid duplicate backlog entries
                backlog_added = self.backlog_cleaner.add(
                    backlog_id_key,
                    title_to_search, # Store the title that needs searching
                    additional_data={
                        "type": "identification_pending",
                        "original_title": title_to_search,
                        "media_type_guess": "movie", # Assume movie for title search
                        "original_filepath": self.current_filepath
                    }
                )
                if backlog_added:
                    self._send_notification(
                        "Offline: Movie Needs Identification",
                        f"'{title_to_search}' will be identified by Simkl when online.",
                        offline_only=True
                    )
            return

        logger.info(f"Attempting Simkl movie title search for: '{title_to_search}'")
        try:
            results = search_movie(title_to_search, self.client_id, self.access_token)
            if results:
                # search_movie can return a list or a single movie dict
                # _process_simkl_search_result handles both list (takes first) and dict
                self._process_simkl_search_result(results, title_to_search, cache_key, "simkl_search_movie")
            else:
                logger.warning(f"Simkl movie search for '{title_to_search}' returned no results.")
                # No specific fallback here for movies other than what might be in cache already
        except RequestException as e:
            logger.warning(f"Network error during Simkl movie title search for '{title_to_search}': {e}")
        except Exception as e:
            logger.error(f"Error during Simkl movie title search for '{title_to_search}': {e}", exc_info=True)

    def _clear_backlog_entry_if_temp_identified(self):
        """Removes a temporary 'identification_pending' backlog entry if the current item was resolved from it."""
        if not self.currently_tracking or not self.simkl_id: # Must have a current item and a resolved Simkl ID
            return

        # The key for 'identification_pending' items is f"identify_{original_title_lower}"
        original_title_lower = self.currently_tracking.lower() # currently_tracking holds the raw title
        backlog_item_key_to_check = f"identify_{original_title_lower}"

        pending_item_data = self.backlog_cleaner.get_pending().get(backlog_item_key_to_check)

        if pending_item_data and pending_item_data.get("type") == "identification_pending":
            # Ensure it's the correct item by original_title if available
            if pending_item_data.get("original_title", "").lower() == original_title_lower:
                if self.backlog_cleaner.remove(backlog_item_key_to_check):
                    logger.info(f"Removed temporary backlog entry '{backlog_item_key_to_check}' for identified movie '{self.movie_name or self.currently_tracking}'.")
                else:
                    logger.warning(f"Attempted to remove temp backlog entry '{backlog_item_key_to_check}', but it was already gone.")
            else:
                logger.debug(f"Temp backlog entry '{backlog_item_key_to_check}' original title mismatch. Not removing.")
        else:
            logger.debug(f"No 'identification_pending' backlog entry found for '{original_title_lower}'.")


    def _attempt_add_to_history(self):
        """
        Attempts to add the currently tracked media to Simkl history or backlog.
        Sets self.completed on success or when added to backlog.
        """
        display_title = self.movie_name or self.currently_tracking # Use official name if known
        # Cache key for cooldown tracking: prefer filepath, fallback to raw title
        cache_key_for_cooldown = os.path.basename(self.current_filepath).lower() if self.current_filepath else self.currently_tracking.lower()
        current_time = time.time()
        cooldown_period = 300 # 5 minutes

        if self.completed:
            logger.debug(f"'{display_title}' already marked as complete/backlogged. Skipping history add.")
            return False

        if self.last_backlog_attempt_time.get(cache_key_for_cooldown) and \
           (current_time - self.last_backlog_attempt_time[cache_key_for_cooldown] < cooldown_period):
            logger.info(f"Recently attempted to backlog '{display_title}'. Cooldown active. Marking complete and skipping.")
            self.completed = True # Ensure it's marked complete if in cooldown from backlog add
            return False

        if not self.client_id or not self.access_token:
            logger.error(f"Cannot add '{display_title}' to history: missing API credentials.")
            if self.simkl_id: # If we have an ID, we can backlog it
                self._add_to_backlog_due_to_issue(
                    self.simkl_id, display_title, "missing_credentials",
                    {"simkl_id": self.simkl_id, "type": self.media_type, "season": self.season, "episode": self.episode}
                )
                self._send_notification("Auth Error", f"'{display_title}' needs sync (missing creds). Added to backlog.")
            return False

        # --- Identification Check ---
        if not self.simkl_id:
            # Try to use guessit fallback info if no Simkl ID
            cached_fallback_info = self.media_cache.get(cache_key_for_cooldown)
            if cached_fallback_info and cached_fallback_info.get("source", "").startswith("guessit_fallback"):
                logger.info(f"'{display_title}' has no Simkl ID. Using guessit fallback for backlog.")
                # Use filepath as backlog key for guessit items, or a guessit-prefixed key
                backlog_key = self.current_filepath if self.current_filepath else f"guessit_{cache_key_for_cooldown}"
                guessit_title_for_backlog = cached_fallback_info.get("movie_name", display_title)
                backlog_data = {
                    "title": guessit_title_for_backlog,
                    "type": cached_fallback_info.get("type", "episode"), # guessit type
                    "season": cached_fallback_info.get("season"),
                    "episode": cached_fallback_info.get("episode"),
                    "year": cached_fallback_info.get("year"),
                    "original_filepath": self.current_filepath, # Critical for later re-identification
                    "source": "guessit_for_backlog"
                }
                self._add_to_backlog_due_to_issue(backlog_key, guessit_title_for_backlog, "guessit_fallback", backlog_data)
                self._send_notification("Offline: Added to Backlog (Filename Data)", f"'{guessit_title_for_backlog}' needs sync.", offline_only=True)
            elif not is_internet_connected():
                # Offline, no Simkl ID, no guessit fallback suitable for backlog
                import uuid
                temp_id = f"temp_{str(uuid.uuid4())[:8]}"
                logger.info(f"Offline and unidentified: Adding '{display_title}' to backlog with temp ID {temp_id}")
                backlog_data = {
                    "simkl_id": temp_id, # This is the item_key for the backlog
                    "title": display_title, # Raw title
                    "type": self.media_type or 'unknown', # Initial guessit type or unknown
                    "season": self.season, # From guessit if available
                    "episode": self.episode, # From guessit if available
                    "original_filepath": self.current_filepath,
                    "source": "temp_id_offline_unidentified"
                }
                self._add_to_backlog_due_to_issue(temp_id, display_title, "temp_id_offline", backlog_data)
                self._send_notification("Offline: Added to Backlog (Temp ID)", f"'{display_title}' needs sync.", offline_only=True)
            else: # Online, but no Simkl ID and no suitable fallback
                logger.info(f"Cannot add '{display_title}' to history yet: Simkl ID unknown and no suitable fallback. Will retry identification.")
            return False # Return false whether backlogged or just waiting for ID

        # --- Internet Connection Check (Now that we have a Simkl ID) ---
        if not is_internet_connected():
            logger.warning(f"Offline: Adding '{display_title}' (ID: {self.simkl_id}) to backlog.")
            self._add_to_backlog_due_to_issue(
                self.simkl_id, display_title, "offline_with_id",
                {"simkl_id": self.simkl_id, "type": self.media_type, "season": self.season, "episode": self.episode}
            )
            self._send_notification("Offline: Added to Backlog", f"'{display_title}' will sync when online.", offline_only=True)
            return False

        # --- Ensure Season/Episode for Shows/Anime (Simkl Type) ---
        if self.media_type in ['show', 'anime'] and (self.season is None or self.episode is None):
            logger.warning(f"Attempting to sync {self.media_type} '{display_title}' but missing season/episode. Trying to resolve.")
            self._resolve_missing_season_episode(cache_key_for_cooldown) # Tries to update self.season/episode
            if self.media_type == 'show' and (self.season is None or self.episode is None):
                logger.error(f"Failed to resolve S/E for show '{display_title}'. Cannot sync.")
                # Optionally backlog here if resolution consistently fails. For now, just fail the attempt.
                return False
            if self.media_type == 'anime' and self.episode is None:
                 logger.error(f"Failed to resolve episode for anime '{display_title}'. Cannot sync.")
                 return False

        # --- Construct Payload ---
        payload = self._build_add_to_history_payload()
        if not payload:
            logger.error(f"Could not construct valid payload for '{display_title}' (Type: {self.media_type}, S:{self.season}, E:{self.episode}).")
            return False

        # --- Attempt API Call ---
        log_item_desc = f"{self.media_type} '{display_title}' (ID: {self.simkl_id})"
        if self.media_type in ['show', 'anime']:
            log_item_desc += f" S{self.season}E{self.episode}" if self.media_type == 'show' and self.season else f" E{self.episode}"

        try:
            result = add_to_history(payload, self.client_id, self.access_token)
            if result:
                self.completed = True
                self._log_playback_event("added_to_history_success", {"simkl_id": self.simkl_id, "type": self.media_type})
                self._store_in_watch_history(
                    self.simkl_id, self.currently_tracking, self.movie_name, # Raw, Official
                    media_type=self.media_type, season=self.season, episode=self.episode,
                    original_filepath=self.current_filepath
                )
                self._send_notification(f"{self.media_type.capitalize()} Synced", f"'{display_title}' added to Simkl.", online_only=True)
                if cache_key_for_cooldown in self.last_backlog_attempt_time:
                    del self.last_backlog_attempt_time[cache_key_for_cooldown]
                return True
            else: # API call made, but returned failure (e.g., Simkl error)
                logger.warning(f"Failed to add {log_item_desc} to Simkl history (API indicated failure). Adding to backlog.")
                self._add_to_backlog_due_to_issue(
                    self.simkl_id, display_title, "api_sync_fail",
                    {"simkl_id": self.simkl_id, "type": self.media_type, "season": self.season, "episode": self.episode, "error": "API_FAIL"}
                )
                self._send_notification("Online Sync Failed", f"'{display_title}' couldn't sync. Added to backlog.")
                return False
        except RequestException as e: # Network errors
            logger.warning(f"Network error adding {log_item_desc} to history: {e}. Adding to backlog.")
            self._add_to_backlog_due_to_issue(
                self.simkl_id, display_title, "api_network_error",
                {"simkl_id": self.simkl_id, "type": self.media_type, "season": self.season, "episode": self.episode, "error": str(e)}
            )
            self._send_notification("Sync Network Error", f"'{display_title}' couldn't sync. Added to backlog.")
            return False
        except Exception as e: # Other unexpected errors
            logger.error(f"Unexpected error adding {log_item_desc} to history: {e}", exc_info=True)
            self._add_to_backlog_due_to_issue(
                self.simkl_id, display_title, "api_exception",
                {"simkl_id": self.simkl_id, "type": self.media_type, "season": self.season, "episode": self.episode, "error": str(e)}
            )
            self._send_notification("Sync Error", f"Error syncing '{display_title}'. Added to backlog.")
            return False

    def _add_to_backlog_due_to_issue(self, item_key_for_backlog, title_for_backlog, reason_code, backlog_data_payload):
        """Helper to add item to backlog, set completed flag, and log."""
        # item_key_for_backlog is the Simkl ID, or filepath, or temp_id
        # backlog_data_payload is the 'additional_data' for backlog_cleaner.add
        
        self.backlog_cleaner.add(item_key_for_backlog, title_for_backlog, additional_data=backlog_data_payload)
        
        # Use a consistent cache key for cooldown, based on current filepath or raw title
        cooldown_key = os.path.basename(self.current_filepath).lower() if self.current_filepath else self.currently_tracking.lower()
        self.last_backlog_attempt_time[cooldown_key] = time.time()
        
        self.completed = True # Mark as "handled" for this playback session
        self._log_playback_event(f"added_to_backlog_{reason_code}", backlog_data_payload)


    def _resolve_missing_season_episode(self, cache_key):
        """Tries to find missing S/E from cache or filename for currently tracked item."""
        # Check cache first
        cached_info = self.media_cache.get(cache_key)
        if cached_info:
            if self.season is None and 'season' in cached_info: self.season = cached_info['season']
            if self.episode is None and 'episode' in cached_info: self.episode = cached_info['episode']
            if self.media_type == 'show' and self.season is not None and self.episode is not None: return
            if self.media_type == 'anime' and self.episode is not None: return

        # Try regex on filename if still missing
        source_for_regex = None
        if self.current_filepath:
            source_for_regex = os.path.basename(self.current_filepath)
        elif self.currently_tracking: # Fallback to raw title
            source_for_regex = self.currently_tracking

        if source_for_regex:
            patterns = [
                r'[sS](\d{1,3})[eE](\d{1,4})', r'(\d{1,3})x(\d{1,4})',
                r'[sS](\d{1,3}).?[eE]?(\d{1,4})', # S01.E01, S01E01, S01.01
                r'episode.*?(\d{1,4})', # "episode 01", "Episode.1" (captures episode only)
                r' (\d{1,4}) ', # Space-padded number, might be an episode for anime
            ]
            for pattern in patterns:
                match = re.search(pattern, source_for_regex, re.IGNORECASE)
                if match:
                    try:
                        if len(match.groups()) == 2: # Season and Episode
                            if self.season is None: self.season = int(match.group(1))
                            if self.episode is None: self.episode = int(match.group(2))
                        elif len(match.groups()) == 1: # Episode only
                            if self.episode is None: self.episode = int(match.group(1))
                        
                        logger.info(f"Resolved S/E from regex on '{source_for_regex}': S{self.season}, E{self.episode}")
                        # Update cache if resolved
                        if cached_info:
                            if self.season is not None: cached_info['season'] = self.season
                            if self.episode is not None: cached_info['episode'] = self.episode
                            self.media_cache.set(cache_key, cached_info)
                        break # Found a match
                    except ValueError:
                        logger.warning(f"Regex matched non-integer S/E in '{source_for_regex}' with pattern '{pattern}'")
                        # Reset to ensure partial matches don't cause issues
                        if len(match.groups()) == 2 and self.season is not None and not isinstance(self.season, int): self.season = None
                        if self.episode is not None and not isinstance(self.episode, int): self.episode = None


    def _build_add_to_history_payload(self):
        """Constructs the payload for Simkl's add_to_history endpoint."""
        if not self.simkl_id: return None
        
        try:
            # Ensure Simkl ID is an integer for the payload
            simkl_id_int = int(self.simkl_id)
            item_ids = {"simkl": simkl_id_int}
        except ValueError:
            logger.error(f"Invalid Simkl ID format for payload: {self.simkl_id}. Must be integer.")
            return None

        payload = {}
        if self.media_type == 'movie':
            payload = {"movies": [{"ids": item_ids}]}
        elif self.media_type == 'show':
            if self.season is not None and self.episode is not None:
                try:
                    payload = {
                        "shows": [{
                            "ids": item_ids,
                            "seasons": [{"number": int(self.season), "episodes": [{"number": int(self.episode)}]}]
                        }]
                    }
                except ValueError:
                    logger.error(f"Invalid S/E format for show payload: S{self.season}E{self.episode}")
                    return None
            else: return None # Missing S/E for show
        elif self.media_type == 'anime':
            # Anime payload might vary; Simkl API docs say episodes can be directly under show or under season.
            # Assuming direct episodes for simplicity if season is not robustly identified.
            # If Simkl API for anime consistently uses seasons, this might need adjustment or reliance on S/E resolution.
            if self.episode is not None:
                try:
                    anime_episode_payload = [{"number": int(self.episode)}]
                    show_item = {"ids": item_ids}
                    if self.season is not None: # If season is known, nest episode under it
                         show_item["seasons"] = [{"number": int(self.season), "episodes": anime_episode_payload}]
                    else: # Otherwise, episodes directly under show (common for OVAs or movies treated as anime episodes)
                         show_item["episodes"] = anime_episode_payload
                    payload = {"shows": [show_item]}
                except ValueError:
                    logger.error(f"Invalid E (or S) format for anime payload: S{self.season}E{self.episode}")
                    return None
            else: return None # Missing E for anime
        else:
            logger.error(f"Unknown media type for payload: {self.media_type}")
            return None
        return payload


    def _store_in_watch_history(self, simkl_id, original_title, resolved_title=None,
                                media_type=None, season=None, episode=None,
                                original_filepath=None, api_details_to_use=None):
        """Stores watched media in local history, enriching with API details if needed."""
        if not hasattr(self, 'watch_history'): # Should be initialized in __init__
            self.watch_history = WatchHistoryManager(self.app_data_dir)

        media_file_path_for_history = original_filepath or self.current_filepath
        
        # Cache key for fetching existing full details: prefer filepath, then resolved title, then original
        cache_key_for_details = None
        if media_file_path_for_history:
            cache_key_for_details = os.path.basename(media_file_path_for_history).lower()
        elif resolved_title:
            cache_key_for_details = resolved_title.lower()
        elif original_title:
            cache_key_for_details = original_title.lower()

        # Base info for history entry
        history_entry = {
            'simkl_id': simkl_id,
            'title': resolved_title or original_title, # Official Simkl title
            'original_title': original_title,       # Raw detected title
            'type': media_type or 'movie',          # Simkl type ('movie', 'show', 'anime')
            'season': season,
            'episode': episode,
            'watched_at': datetime.utcnow().isoformat() + "Z",
            'ids': {'simkl': simkl_id} # Ensure base 'ids' with simkl_id
        }
        if media_file_path_for_history:
            history_entry['filepath_at_watch'] = media_file_path_for_history

        current_details = None
        details_source = "unknown"

        # 1. Try to get from media_cache first (should be freshest after backlog processing updates it)
        if cache_key_for_details:
            cached_full_info = self.media_cache.get(cache_key_for_details)
            if cached_full_info:
                if '_api_full_details' in cached_full_info and cached_full_info['_api_full_details']:
                    details_source = "media_cache_api_full_details"
                    current_details = cached_full_info['_api_full_details']
                    logger.info(f"Watch History: Using full API details from cache for '{history_entry['title']}' (ID: {simkl_id}).")
                elif cached_full_info.get('source', ''): # Check if it has any source, indicating it's populated
                    # Check if the source indicates it's from a Simkl API call (more reliable)
                    # or if it's a more complete entry (e.g., has overview or poster_url)
                    is_simkl_sourced = "simkl_" in cached_full_info.get('source', '')
                    has_rich_details = cached_full_info.get('overview') or cached_full_info.get('poster_url')
                    if is_simkl_sourced or has_rich_details:
                        details_source = "media_cache_populated"
                        current_details = cached_full_info # Use the cache entry
                        logger.info(f"Watch History: Using populated details from cache for '{history_entry['title']}' (ID: {simkl_id}, Source: {cached_full_info.get('source')}).")
                    else:
                        logger.info(f"Watch History: Cache entry for '{history_entry['title']}' (ID: {simkl_id}) found but deemed not rich enough (Source: {cached_full_info.get('source')}). Will try other sources.")


        # 2. If not in cache (or cache was insufficient), use provided api_details_to_use (from backlog resolution step)
        if not current_details and api_details_to_use:
            details_source = "provided_api_details_from_backlog_resolve"
            current_details = api_details_to_use
            logger.info(f"Watch History: Using provided API details from backlog resolution for '{history_entry['title']}' (ID: {simkl_id}).")
        
        # 3. If still no details, and online, fetch fresh from API
        if not current_details and is_internet_connected() and self.client_id and self.access_token:
            logger.info(f"Fetching details for watch history: '{history_entry['title']}' (ID: {simkl_id})")
            details_source = "live_api_fetch"
            try:
                if history_entry['type'] == 'movie':
                    current_details = get_movie_details(simkl_id, self.client_id, self.access_token)
                elif history_entry['type'] in ['show', 'anime']:
                    current_details = get_show_details(simkl_id, self.client_id, self.access_token)
                
                # If fetched, update cache using the centralized cache_media_info method
                if current_details and cache_key_for_details:
                    logger.info(f"Watch History: Fetched details for ID {simkl_id}. Updating cache via cache_media_info.")
                    
                    # Poster ID processing
                    raw_poster_url_hist = current_details.get('poster')

                    self.cache_media_info(
                        original_title_key=cache_key_for_details,
                        simkl_id=simkl_id,
                        display_name=current_details.get('title', history_entry['title']),
                        media_type=current_details.get('type', history_entry['type']),
                        season=season, # Use season from parameters, API details might not have episode context
                        episode=episode, # Use episode from parameters
                        year=current_details.get('year'),
                        runtime_minutes=current_details.get('runtime'),
                        api_ids=current_details.get('ids'),
                        overview=current_details.get('overview'),
                        poster_url=raw_poster_url_hist,
                        source_description="simkl_api_watch_history_enrich",
                        original_filepath_if_any=media_file_path_for_history, # original_filepath passed to _store_in_watch_history
                        _api_full_details=current_details
                    )
            except Exception as e:
                logger.warning(f"Error fetching API details for watch history (ID: {simkl_id}): {e}")
                current_details = None # Ensure it's None on error

        # Populate history_entry with details if found/fetched
        if current_details:
            logger.debug(f"Using details from '{details_source}' for watch history ID {simkl_id}")
            history_entry['title'] = current_details.get('title', history_entry['title'])
            history_entry['year'] = current_details.get('year')
            history_entry['overview'] = current_details.get('overview')
            history_entry['type'] = current_details.get('type', history_entry['type']) # API type is canonical
            history_entry['poster_url'] = current_details.get('poster_url') or current_details.get('poster') # Prioritize poster_url
            
            # Runtime: from 'runtime' (minutes) in API details or 'duration_seconds' in cache
            runtime_minutes = None
            if 'runtime' in current_details:
                try: runtime_minutes = int(current_details['runtime'])
                except: pass
            elif 'duration_seconds' in current_details: # From cache
                try: runtime_minutes = int(current_details['duration_seconds'] / 60)
                except: pass
            history_entry['runtime'] = runtime_minutes

            # IDs: merge, prioritizing API details
            api_ids = current_details.get('ids', {})
            essential_ids = {k: v for k, v in api_ids.items() if k in ['simkl', 'imdb', 'tmdb', 'tvdb', 'mal', 'anilist'] and v}
            history_entry['ids'] = {**history_entry['ids'], **essential_ids} # Merge, API values overwrite
            if 'imdb' in history_entry['ids']: history_entry['imdb_id'] = history_entry['ids']['imdb'] # Convenience

        # Final type correction if S/E implies show/anime
        if (history_entry.get('season') is not None or history_entry.get('episode') is not None) and \
           history_entry.get('type') not in ['show', 'anime']:
            logger.info(f"Correcting history type to 'show' for '{history_entry['title']}' due to S/E presence.")
            history_entry['type'] = 'show' # Default to 'show' if S/E exists and type isn't already show/anime

        try:
            logger.debug(f"Adding to local watch history: ID {simkl_id}, Title: '{history_entry['title']}', Type: {history_entry['type']}")
            self.watch_history.add_entry(history_entry, media_file_path=media_file_path_for_history)
        except Exception as e:
            logger.error(f"Error storing in local watch history (ID: {simkl_id}): {e}", exc_info=True)


    def process_backlog(self):
        """Processes pending backlog items: identifies, resolves, and syncs to Simkl."""
        MAX_ATTEMPTS = 5
        BASE_RETRY_DELAY_SECONDS = 60 # 1 minute

        if not self.client_id or not self.access_token:
            logger.warning("[Backlog] Missing credentials. Cannot process.")
            return {'processed': 0, 'attempted': 0, 'failed': True, 'reason': 'Missing credentials'}

        if not is_internet_connected():
            logger.info("[Backlog] No internet. Sync deferred.")
            return {'processed': 0, 'attempted': 0, 'failed': False, 'reason': 'Offline'}

        pending_items_dict = self.backlog_cleaner.get_pending()
        if not pending_items_dict:
            return {'processed': 0, 'attempted': 0, 'failed': False, 'reason': 'No items'}

        logger.info(f"[Backlog] Processing {len(pending_items_dict)} items...")
        success_count = 0
        attempted_this_cycle = 0
        failure_this_cycle = False
        current_time = time.time()

        items_to_process_keys = list(pending_items_dict.keys()) # Iterate over a copy

        for item_key in items_to_process_keys:
            item_data = pending_items_dict.get(item_key) # Get current data for this key

            if not isinstance(item_data, dict):
                logger.warning(f"[Backlog] Invalid item data for key '{item_key}'. Skipping.")
                failure_this_cycle = True
                continue

            display_title = item_data.get("title", item_key) # For logging

            # Concurrency check: ensure only one thread processes an item
            with self._processing_lock:
                if item_key in self._processing_backlog_items:
                    logger.info(f"[Backlog] Item '{display_title}' (Key: {item_key}) already being processed. Skipping.")
                    continue
                self._processing_backlog_items.add(item_key)
            
            try:
                attempt_count = item_data.get("attempt_count", 0)
                last_attempt_ts = item_data.get("last_attempt_timestamp")

                if attempt_count >= MAX_ATTEMPTS:
                    logger.warning(f"[Backlog] Item '{display_title}' (Key: {item_key}) max attempts reached. Skipping.")
                    # Consider permanent failure logic here if needed (e.g., move to a "failed" log)
                    continue

                if last_attempt_ts:
                    retry_delay = BASE_RETRY_DELAY_SECONDS * (2 ** min(attempt_count, 6)) # Cap exponential backoff
                    if current_time - last_attempt_ts < retry_delay:
                        logger.debug(f"[Backlog] Item '{display_title}' (Key: {item_key}) in retry cooldown. Skipping.")
                        continue
                
                attempted_this_cycle += 1
                logger.info(f"[Backlog] Attempting item '{display_title}' (Key: {item_key}, Attempt: {attempt_count + 1})")

                # --- Step 1: Resolve Item ID if Necessary ---
                # This updates item_data with resolved simkl_id, type, title, S/E
                resolution_success, item_data, api_error_msg = self._resolve_backlog_item_identity(item_key, item_data)
                
                if not resolution_success:
                    logger.warning(f"[Backlog] Failed to resolve identity for '{display_title}' (Key: {item_key}): {api_error_msg}")
                    self.backlog_cleaner.update_item(item_key, {
                        'attempt_count': attempt_count + 1,
                        'last_attempt_timestamp': current_time,
                        'last_error': api_error_msg or "Identity resolution failed"
                    })
                    failure_this_cycle = True
                    continue # To next item

                # --- Step 2: Prepare for Simkl Sync (item_data is now resolved) ---
                simkl_id_to_sync = item_data.get('simkl_id')
                media_type_to_sync = item_data.get('type')
                title_to_sync = item_data.get('title', display_title)
                season_to_sync = item_data.get('season')
                episode_to_sync = item_data.get('episode')
                original_filepath_from_backlog = item_data.get('original_filepath') or \
                                                 (item_key if os.path.exists(str(item_key)) else None)


                if not simkl_id_to_sync or not media_type_to_sync:
                    logger.error(f"[Backlog] Resolved item '{title_to_sync}' missing Simkl ID or Type. Cannot sync.")
                    self.backlog_cleaner.update_item(item_key, {
                        'attempt_count': attempt_count + 1, 'last_attempt_timestamp': current_time,
                        'last_error': "Resolved item missing ID/Type"
                    })
                    failure_this_cycle = True
                    continue

                # --- Step 3: Construct Payload and Sync ---
                # Use a temporary scrobbler state for payload building
                # This is a bit of a hack but reuses the payload logic.
                # A more direct payload builder for backlog items might be cleaner.
                temp_state_simkl_id = self.simkl_id
                temp_state_media_type = self.media_type
                temp_state_season = self.season
                temp_state_episode = self.episode
                
                self.simkl_id = simkl_id_to_sync
                self.media_type = media_type_to_sync
                self.season = season_to_sync
                self.episode = episode_to_sync
                
                payload = self._build_add_to_history_payload()

                # Restore original scrobbler state
                self.simkl_id = temp_state_simkl_id
                self.media_type = temp_state_media_type
                self.season = temp_state_season
                self.episode = temp_state_episode

                if not payload:
                    logger.error(f"[Backlog] Failed to build payload for '{title_to_sync}' (ID: {simkl_id_to_sync}). Error in item data.")
                    self.backlog_cleaner.update_item(item_key, {
                        'attempt_count': attempt_count + 1, 'last_attempt_timestamp': current_time,
                        'last_error': "Payload build failed"
                    })
                    failure_this_cycle = True
                    continue

                sync_api_error = None
                try:
                    logger.info(f"[Backlog] Syncing '{title_to_sync}' (ID: {simkl_id_to_sync}, Type: {media_type_to_sync}) to Simkl.")
                    sync_result = add_to_history(payload, self.client_id, self.access_token)
                    if sync_result:
                        success_count += 1
                        logger.info(f"[Backlog] Successfully synced '{title_to_sync}'. Removing from backlog.")
                        self.backlog_cleaner.remove(item_key)

                        # After successful sync, fetch and cache additional details
                        cache_key_for_update = (os.path.basename(original_filepath_from_backlog).lower()
                                                if original_filepath_from_backlog
                                                else title_to_sync.lower())
                        self._fetch_and_update_cache_with_full_details(
                            simkl_id_to_sync,
                            media_type_to_sync,
                            cache_key_for_update,
                            title_to_sync
                        )
                        
                        # Store in local watch history with potentially enriched details
                        # item_data should have the resolved title, type, S/E from _resolve_backlog_item_identity
                        # and cache should now be updated with full details
                        self._store_in_watch_history(
                            simkl_id_to_sync,
                            item_data.get('original_title', title_to_sync), # original detected title
                            title_to_sync, # resolved title
                            media_type=media_type_to_sync,
                            season=season_to_sync,
                            episode=episode_to_sync,
                            original_filepath=original_filepath_from_backlog,
                            api_details_to_use=item_data.get('_api_details_for_history') # Pass if _resolve fetched them
                        )
                    else:
                        sync_api_error = "Simkl API add_to_history call failed (returned False/None)."
                except RequestException as e:
                    sync_api_error = f"Network error during Simkl sync: {e}"
                except Exception as e:
                    sync_api_error = f"Unexpected error during Simkl sync: {e}"
                    logger.error(f"[Backlog] {sync_api_error} for '{title_to_sync}'", exc_info=True)

                if sync_api_error:
                    logger.warning(f"[Backlog] Sync failed for '{title_to_sync}': {sync_api_error}")
                    self.backlog_cleaner.update_item(item_key, {
                        'attempt_count': attempt_count + 1,
                        'last_attempt_timestamp': current_time,
                        'last_error': sync_api_error
                    })
                    failure_this_cycle = True

            finally:
                with self._processing_lock:
                    if item_key in self._processing_backlog_items:
                        self._processing_backlog_items.remove(item_key)
        
        if attempted_this_cycle > 0:
            logger.info(f"[Backlog] Cycle complete. Attempted: {attempted_this_cycle}, Synced: {success_count}.")
        elif len(pending_items_dict) > 0: # Items exist but none were attempted (e.g., all in cooldown)
            logger.info("[Backlog] Cycle complete. No items ready for retry due to cooldowns.")

        return {'processed': success_count, 'attempted': attempted_this_cycle, 'failed': failure_this_cycle}

    def _resolve_backlog_item_identity(self, item_key, item_data):
        """
        Attempts to resolve the Simkl ID and full details for a backlog item.
        Updates item_data in place if successful.
        Returns: (success_bool, updated_item_data, error_message_str_or_none)
        """
        original_id_in_backlog = item_data.get("simkl_id", item_key) # item_key might be filepath or temp_id
        title_from_backlog = item_data.get("title")
        media_type_from_backlog = item_data.get("type") # Original type from backlog
        original_filepath = item_data.get("original_filepath") or \
                            (item_key if os.path.exists(str(item_key)) else None) # If item_key is a path
        
        # If already a valid Simkl ID, just enrich details if needed
        if isinstance(original_id_in_backlog, int) or (isinstance(original_id_in_backlog, str) and original_id_in_backlog.isdigit()):
            resolved_simkl_id = int(original_id_in_backlog)
            # Fetch full details to confirm type and get official title, S/E
            logger.info(f"[Backlog Resolve] Item '{title_from_backlog}' (ID: {resolved_simkl_id}) has Simkl ID. Fetching details.")
            api_details = None
            try:
                if media_type_from_backlog == 'movie': # Use backlog type as hint
                    api_details = get_movie_details(resolved_simkl_id, self.client_id, self.access_token)
                elif media_type_from_backlog in ['show', 'anime', 'episode']: # 'episode' is guessit type
                    api_details = get_show_details(resolved_simkl_id, self.client_id, self.access_token)
                else: # Unknown type, try show details as a common case, or try to guess from title
                    logger.warning(f"[Backlog Resolve] Unknown type '{media_type_from_backlog}' for ID {resolved_simkl_id}. Trying show details.")
                    api_details = get_show_details(resolved_simkl_id, self.client_id, self.access_token)
                    if not api_details: # If show fails, try movie
                         api_details = get_movie_details(resolved_simkl_id, self.client_id, self.access_token)
                
                if api_details:
                    item_data['simkl_id'] = resolved_simkl_id
                    item_data['title'] = api_details.get('title', title_from_backlog)
                    item_data['type'] = api_details.get('type', media_type_from_backlog) # API type is canonical
                    if item_data['type'] in ['show', 'anime']:
                        # If backlog item had S/E (e.g. from guessit), use it unless API provides better
                        # This part is tricky; Simkl's get_show_details doesn't return specific episode info
                        # We rely on the S/E stored in the backlog item if it was from /search/file or guessit
                        # If item_data['season'] or ['episode'] is None, it remains so.
                        pass 
                    item_data['_api_details_for_history'] = api_details # Store for watch history
                    return True, item_data, None
                else:
                    return False, item_data, f"Failed to fetch details for Simkl ID {resolved_simkl_id}"
            except Exception as e:
                return False, item_data, f"API error fetching details for Simkl ID {resolved_simkl_id}: {e}"

        # --- Handle identification_pending, temp_id, guessit_ (filepath key), or filepath key directly ---
        search_term_title = item_data.get("original_title", title_from_backlog) # For title-based search
        media_type_guess = item_data.get("media_type_guess", media_type_from_backlog) # Hint for search
        
        logger.info(f"[Backlog Resolve] Attempting to identify item: Key='{item_key}', Title='{search_term_title}', File='{original_filepath}', TypeHint='{media_type_guess}'")
        
        api_search_result = None
        try:
            if original_filepath and media_type_guess in ['episode', 'show', 'anime']:
                api_search_result = search_file(original_filepath, self.client_id)
            elif media_type_guess == 'movie' or not original_filepath : # Movie search or title search if no file
                api_search_result = search_movie(search_term_title, self.client_id, self.access_token)
            else: # Should not happen if logic is sound
                 return False, item_data, "Could not determine search method for backlog item."
        except Exception as e:
            return False, item_data, f"API search failed: {e}"

        if not api_search_result:
            return False, item_data, "Simkl API search yielded no results."

        # Process search result (similar to _process_simkl_search_result but for backlog context)
        # This should populate item_data with 'simkl_id', 'title', 'type', 'season', 'episode'
        # And potentially '_api_details_for_history' if the search result is detailed enough
        # For simplicity, assume search_file/search_movie returns structure handled by _process_simkl_search_result logic
        # We need to adapt it to update item_data instead of self state.

        # Simplified extraction for backlog resolution:
        found_media_item = None
        found_simkl_type = None
        found_episode_details = {}

        if 'show' in api_search_result:
            found_media_item = api_search_result['show']
            found_simkl_type = found_media_item.get('type', 'show')
            found_episode_details = api_search_result.get('episode', {})
        elif 'movie' in api_search_result:
            found_media_item = api_search_result['movie']
            found_simkl_type = 'movie'
        elif isinstance(api_search_result, list) and api_search_result:
            first_res = api_search_result[0]
            if 'movie' in first_res: found_media_item = first_res['movie']; found_simkl_type = 'movie'
            elif first_res.get('type') == 'movie': found_media_item = first_res; found_simkl_type = 'movie'
        elif isinstance(api_search_result, dict) and api_search_result.get('type') == 'movie':
            found_media_item = api_search_result; found_simkl_type = 'movie'

        if not (found_media_item and found_media_item.get('ids', {}).get('simkl')):
            return False, item_data, "Search result parsing failed or no Simkl ID found."

        item_data['simkl_id'] = int(found_media_item['ids']['simkl'])
        item_data['title'] = found_media_item.get('title', search_term_title)
        item_data['type'] = found_simkl_type
        item_data['_api_details_for_history'] = found_media_item # Store for history if needed

        if found_simkl_type in ['show', 'anime']:
            item_data['season'] = found_episode_details.get('season') # May be None
            item_data['episode'] = found_episode_details.get('episode') # May be None
            # Convert to int if not None
            if item_data['season'] is not None:
                try:
                    item_data['season'] = int(item_data['season'])
                except (ValueError, TypeError):
                    item_data['season'] = None
            if item_data['episode'] is not None:
                try:
                    item_data['episode'] = int(item_data['episode'])
                except (ValueError, TypeError):
                    item_data['episode'] = None
        else: # Movie
            item_data['season'] = None
            item_data['episode'] = None
        
        logger.info(f"[Backlog Resolve] Successfully resolved '{search_term_title}' to ID {item_data['simkl_id']}, Title '{item_data['title']}', Type '{item_data['type']}'")
        return True, item_data, None


    def start_offline_sync_thread(self, interval_seconds=120):
        """Start a background thread to periodically sync backlog when online."""
        if hasattr(self, '_offline_sync_thread') and self._offline_sync_thread.is_alive():
            logger.debug("Offline sync thread already running.")
            return
            
        def sync_loop():
            logger.info("Offline sync thread started.")
            while True:
                try:
                    # Check internet connection before attempting to get pending items
                    if is_internet_connected():
                        if self.backlog_cleaner.has_pending_items(): # Efficient check
                            logger.info("[Offline Sync Thread] Internet detected. Checking backlog...")
                            result = self.process_backlog() # process_backlog itself checks connection again
                            
                            if isinstance(result, dict):
                                processed = result.get('processed', 0)
                                attempted = result.get('attempted', 0)
                                if processed > 0:
                                    logger.info(f"[Offline Sync Thread] Synced {processed} of {attempted} items from backlog.")
                                elif attempted > 0 : # Attempted but none succeeded
                                    logger.info(f"[Offline Sync Thread] Attempted {attempted} backlog items, none synced this cycle.")
                                # If attempted is 0, it means process_backlog found no items ready (e.g. all in cooldown)
                            # else: result might be legacy, handle if necessary or phase out.
                        else:
                            logger.debug("[Offline Sync Thread] Internet detected, but no backlog items to process.")
                    else:
                        logger.debug("[Offline Sync Thread] Still offline. Will retry later.")
                except Exception as e:
                    logger.error(f"[Offline Sync Thread] Error during backlog sync loop: {e}", exc_info=True)
                
                # Wait for the_interval_seconds regardless of outcome
                time.sleep(interval_seconds)
                
        self._offline_sync_thread = threading.Thread(target=sync_loop, daemon=True, name="OfflineSyncThread")
        self._offline_sync_thread.start()

    def cache_media_info(self, original_title_key, simkl_id, display_name, media_type='movie',
                         season=None, episode=None, year=None, runtime_minutes=None,
                         api_ids=None, overview=None, poster_url=None, # Changed from poster_url
                         source_description=None, original_filepath_if_any=None,
                         _api_full_details=None):
        """
        Caches detailed media info, consolidating by Simkl ID and merging data.
        `original_title_key` is the key for this specific caching attempt (e.g., filename or raw title).
        """
        if not original_title_key or not simkl_id:
            logger.warning("Cannot cache media info: Missing original_title_key or Simkl ID.")
            return

        try:
            simkl_id = int(simkl_id) # Ensure simkl_id is an integer
        except (ValueError, TypeError):
            logger.warning(f"Cannot cache media info: Invalid Simkl ID format '{simkl_id}'. Must be integer-convertible.")
            return

        cache_key_to_use = original_title_key.lower()

        # Initialize local variables for fields that might be overridden by episode-specific data
        overview_for_cache = overview
        runtime_minutes_for_cache = runtime_minutes
        poster_url_for_cache = poster_url

        # Episode-specific override logic
        if media_type in ['show', 'anime'] and season is not None and episode is not None and \
           _api_full_details and isinstance(_api_full_details, dict):
            api_episodes_list = _api_full_details.get('episodes')
            if isinstance(api_episodes_list, list):
                for ep_api_data in api_episodes_list:
                    if isinstance(ep_api_data, dict) and \
                       ep_api_data.get('season') == season and \
                       ep_api_data.get('episode') == episode:
                        
                        logger.info(f"Found matching S{season}E{episode} in embedded API details for '{display_name}'.")
                        
                        ep_specific_runtime_min = ep_api_data.get('runtime')
                        if ep_specific_runtime_min is not None:
                            try:
                                runtime_minutes_for_cache = int(ep_specific_runtime_min)
                                logger.info(f"Using episode-specific runtime: {runtime_minutes_for_cache} mins.")
                            except (ValueError, TypeError):
                                logger.warning(f"Invalid episode-specific runtime format: {ep_specific_runtime_min}")
                                
                        ep_specific_overview = ep_api_data.get('overview')
                        if ep_specific_overview and ep_specific_overview.strip(): # Prioritize non-empty episode overview
                            overview_for_cache = ep_specific_overview
                            logger.info("Using episode-specific overview.")
                        
                        # Poster is typically show-level, poster_url_for_cache (derived from poster_url param) is not changed here.
                        break # Found the matching episode
        
        # Prepare the new data, adding fields only if they have a meaningful value
        new_data_to_cache = {"simkl_id": simkl_id}
        if display_name: new_data_to_cache["movie_name"] = display_name
        if media_type: new_data_to_cache["type"] = media_type
        if year is not None: new_data_to_cache["year"] = year
        if overview_for_cache is not None: new_data_to_cache["overview"] = overview_for_cache
        if poster_url_for_cache is not None: new_data_to_cache["poster_url"] = poster_url_for_cache
        if source_description: new_data_to_cache["source"] = source_description
        else: new_data_to_cache["source"] = "updated_via_cache_media_info" # Default source if not specified

        if original_filepath_if_any: new_data_to_cache["original_filepath"] = original_filepath_if_any
        if _api_full_details: new_data_to_cache["_api_full_details"] = _api_full_details

        # Clean and add IDs
        current_api_ids = {"simkl": simkl_id} # Always ensure simkl id is in the 'ids' dict
        if api_ids and isinstance(api_ids, dict):
            current_api_ids.update({k: v for k, v in api_ids.items() if v})
        new_data_to_cache["ids"] = current_api_ids

        if media_type in ['show', 'anime']:
            if season is not None: new_data_to_cache["season"] = season
            if episode is not None: new_data_to_cache["episode"] = episode
        
        duration_seconds_to_cache = None
        if runtime_minutes_for_cache: # Use the potentially episode-specific runtime
            try: duration_seconds_to_cache = int(runtime_minutes_for_cache) * 60
            except (ValueError, TypeError): pass
        
        # If self.total_duration_seconds is known from player for the current item, it's often more accurate
        # This check should happen AFTER episode-specific runtime is considered.
        # If player duration is available and this cache entry is for the currently playing item, prefer player duration.
        if self.total_duration_seconds is not None and self.currently_tracking and \
           (original_title_key.lower() == self.currently_tracking.lower() or \
            (original_filepath_if_any and self.current_filepath and \
             os.path.basename(original_filepath_if_any).lower() == os.path.basename(self.current_filepath).lower())):
            
            # If episode-specific runtime was found, player duration might still be more accurate for *that specific file*.
            # If no episode-specific runtime, player duration is definitely better than show average.
            if duration_seconds_to_cache is None or abs(duration_seconds_to_cache - self.total_duration_seconds) > 120: # If player duration is significantly different (e.g. > 2 mins)
                logger.info(f"Using player-provided duration ({self.total_duration_seconds}s) for caching '{display_name}' (overriding API/episode runtime: {duration_seconds_to_cache}s).")
                duration_seconds_to_cache = self.total_duration_seconds
            else:
                 logger.info(f"Player-provided duration ({self.total_duration_seconds}s) is close to API/episode runtime ({duration_seconds_to_cache}s). Using API/episode for cache consistency.")
        
        if duration_seconds_to_cache is not None:
            new_data_to_cache["duration_seconds"] = duration_seconds_to_cache

        # --- Simkl ID based consolidation and merging ---
        existing_key_for_id, existing_info = self.media_cache.get_by_simkl_id(simkl_id)

        if existing_info: # An entry with this simkl_id already exists
            logger.info(f"Simkl ID {simkl_id} ('{display_name or existing_info.get('movie_name')}') already cached under key '{existing_key_for_id}'. Merging new data.")
            
            merged_data = {**existing_info} # Start with existing data

            # Smart merge: new data takes precedence if not None, or if existing is None/empty
            for key, new_value in new_data_to_cache.items():
                if new_value is not None: # Only consider new values that are not None
                    if key not in merged_data or merged_data[key] is None or str(merged_data[key]).strip() == "":
                        merged_data[key] = new_value
                    elif isinstance(new_value, dict) and isinstance(merged_data.get(key), dict):
                        # For dicts (like 'ids' or '_api_full_details'), merge them deeply if appropriate
                        if key == 'ids': # Simple overwrite for 'ids' is fine, new_data_to_cache['ids'] is already complete
                             merged_data[key] = new_value
                        elif key == '_api_full_details': # Prefer newer full details
                             merged_data[key] = new_value
                        else: # Generic dict merge (could be refined)
                             merged_data[key] = {**merged_data.get(key, {}), **new_value}
                    elif key == 'source': # Always update source to reflect the latest update
                        merged_data[key] = new_value
                    elif key == 'overview' and not merged_data.get('overview') and new_value: # Fill overview if missing
                        merged_data[key] = new_value
                    elif key == 'poster_url' and not merged_data.get('poster_url') and new_value: # Fill poster if missing
                        merged_data[key] = new_value
                    else: # General overwrite for other fields if new_value is present
                        merged_data[key] = new_value
            
            # Ensure essential fields are correctly set from the latest information
            if display_name: merged_data["movie_name"] = display_name
            if media_type: merged_data["type"] = media_type # API type is canonical
            merged_data["simkl_id"] = simkl_id # Ensure it's the correct int type

            self.media_cache.update(existing_key_for_id, merged_data)
            logger.info(f"Updated entry for Simkl ID {simkl_id} at key '{existing_key_for_id}'.")
            
            # If the current call was with a different key (cache_key_to_use)
            # and that key points to a now-redundant entry (that isn't the one we just updated), remove it.
            if cache_key_to_use != existing_key_for_id:
                other_entry_at_cache_key = self.media_cache.get(cache_key_to_use)
                if other_entry_at_cache_key:
                    # If the other entry has the same simkl_id, or no simkl_id (temp entry), it's redundant
                    if other_entry_at_cache_key.get("simkl_id") == simkl_id or not other_entry_at_cache_key.get("simkl_id"):
                        logger.info(f"Removing redundant cache entry at '{cache_key_to_use}' after merging into '{existing_key_for_id}'.")
                        self.media_cache.remove(cache_key_to_use)
        else: # No existing entry for this simkl_id, create a new one
            # Ensure all essential fields are present before setting
            if "movie_name" not in new_data_to_cache and display_name: new_data_to_cache["movie_name"] = display_name
            if "type" not in new_data_to_cache and media_type: new_data_to_cache["type"] = media_type
            if "simkl_id" not in new_data_to_cache: new_data_to_cache["simkl_id"] = simkl_id
            if "source" not in new_data_to_cache: new_data_to_cache["source"] = source_description or "initial_cache_media_info"

            self.media_cache.set(cache_key_to_use, new_data_to_cache)
            logger.info(f"Cached new info for '{new_data_to_cache.get('movie_name', 'N/A')}' (ID: {simkl_id}) under key '{cache_key_to_use}'.")

        # If currently tracking this item, update instance state
        if self.currently_tracking and \
           (cache_key_to_use == self.currently_tracking.lower() or \
            (original_filepath_if_any and self.current_filepath and os.path.basename(original_filepath_if_any).lower() == os.path.basename(self.current_filepath).lower())):
            
            is_new_id_for_instance = (self.simkl_id != simkl_id)
            
            self.simkl_id = simkl_id
            if display_name: self.movie_name = display_name
            if media_type: self.media_type = media_type
            if season is not None: self.season = season
            if episode is not None: self.episode = episode
            
            current_total_duration = new_data_to_cache.get("duration_seconds")
            if current_total_duration is not None and \
               (self.total_duration_seconds is None or abs(self.total_duration_seconds - current_total_duration) > 2): # Allow small variance
                self.total_duration_seconds = current_total_duration
                self.estimated_duration = current_total_duration # Update estimate
                logger.info(f"Instance duration updated to {current_total_duration}s for '{self.movie_name}'.")

            if is_new_id_for_instance or (display_name and self.movie_name != display_name): # Notify if ID or official title changes
                notify_text = f"Playing: '{self.movie_name}'"
                if self.media_type in ['show', 'anime']:
                    if self.season is not None and self.episode is not None: notify_text += f" S{self.season}E{self.episode}"
                    elif self.episode is not None : notify_text += f" E{self.episode}" # Anime
                elif year is not None: notify_text += f" ({year})" # Use year from params if available
                elif new_data_to_cache.get('year') is not None: notify_text += f" ({new_data_to_cache.get('year')})"

                self._send_notification(f"{self.media_type.capitalize()} Identified", notify_text, online_only=True)


    def is_complete(self, threshold_override=None):
        """Checks if the currently tracked media has met the completion threshold."""
        if not self.currently_tracking: return False
        if self.completed: return True # Already marked

        threshold_to_use = threshold_override if threshold_override is not None else self.completion_threshold

        # Prefer position-based percentage if available and reliable
        percentage = self._calculate_percentage(use_position=True)
        if percentage is None: # Fallback to accumulated watch time
            percentage = self._calculate_percentage(use_accumulated=True)

        if percentage is None: return False # Cannot determine completion

        is_now_complete = percentage >= threshold_to_use
        
        # Log first time completion detection for this item
        if is_now_complete and not hasattr(self, '_logged_completion_for_this_item'):
            media_desc = f"{self.media_type or 'media'}"
            if self.media_type in ['show', 'anime']:
                if self.season is not None and self.episode is not None: media_desc += f" S{self.season}E{self.episode}"
                elif self.episode is not None: media_desc += f" E{self.episode}" # Anime case
            logger.info(f"Completion threshold ({threshold_to_use}%) met for {media_desc}: '{self.movie_name or self.currently_tracking}' at {percentage:.2f}%.")
            self._logged_completion_for_this_item = True # Prevent re-logging for this item
        
        return is_now_complete

    def _store_guessit_fallback_data(self, filepath, guessit_info, cache_key_override=None):
        """Stores fallback data from guessit when Simkl API identification fails or is unavailable."""
        if not guessit:
            logger.debug("Guessit not available, cannot store fallback data.")
            return
        if not guessit_info or not isinstance(guessit_info, dict):
            logger.debug("No valid guessit data to store as fallback.")
            return

        try:
            raw_title_from_guessit = guessit_info.get('title')
            if not raw_title_from_guessit:
                logger.warning(f"Cannot store guessit fallback: Missing title in {guessit_info}")
                return

            media_type_from_guessit = guessit_info.get('type', 'episode') # 'episode' or 'movie'
            season_from_guessit = guessit_info.get('season')
            episode_from_guessit = guessit_info.get('episode')
            year_from_guessit = guessit_info.get('year')

            # Use provided cache_key or derive from filepath/title
            cache_key_to_use = cache_key_override
            if not cache_key_to_use:
                 cache_key_to_use = os.path.basename(filepath).lower() if filepath else raw_title_from_guessit.lower()
            
            fallback_data = {
                "movie_name": raw_title_from_guessit, # Store as movie_name for consistency
                "type": media_type_from_guessit, # This is guessit's type
                "season": season_from_guessit,
                "episode": episode_from_guessit,
                "year": year_from_guessit,
                "source": "guessit_fallback_stored",
                "original_filepath": filepath # Crucial for later re-identification attempts
            }
            
            logger.info(f"Storing guessit fallback for '{raw_title_from_guessit}' (Key: {cache_key_to_use}): "
                        f"Type='{media_type_from_guessit}', S={season_from_guessit}, E={episode_from_guessit}")
            self.media_cache.set(cache_key_to_use, fallback_data)

            # If currently tracking this item and it's still unidentified by Simkl, apply guessit info to state
            if self.currently_tracking and not self.simkl_id and \
               ( (filepath and os.path.basename(filepath).lower() == self.currently_tracking.lower()) or \
                 raw_title_from_guessit.lower() == self.currently_tracking.lower() ):
                
                self.movie_name = raw_title_from_guessit # Use guessit title as current official title
                self.media_type = media_type_from_guessit # Use guessit type as current type
                self.season = season_from_guessit
                self.episode = episode_from_guessit
                # Simkl ID remains None
                logger.info("Applied guessit fallback data to current tracking state.")
        except Exception as e:
            logger.error(f"Error storing guessit fallback data: {e}", exc_info=True)

    def _fetch_and_update_cache_with_full_details(self, simkl_id, media_type, original_input_key, resolved_title_hint):
        """Fetches full details for a media item and updates the cache via cache_media_info."""
        if not self.client_id or not self.access_token:
            logger.info(f"[CacheEnhance] Skipping detail fetch for {simkl_id}: no Simkl credentials.")
            return
        if not is_internet_connected():
            logger.info(f"[CacheEnhance] Skipping detail fetch for {simkl_id}: no internet connection.")
            return

        logger.info(f"[CacheEnhance] Attempting to fetch full details for {media_type} ID {simkl_id} ('{resolved_title_hint}') to enhance cache.")
        
        details = None
        try:
            if media_type == 'movie':
                details = get_movie_details(simkl_id, self.client_id, self.access_token)
            elif media_type in ['show', 'anime']:
                details = get_show_details(simkl_id, self.client_id, self.access_token)
            else:
                logger.warning(f"[CacheEnhance] Unknown media type '{media_type}' for Simkl ID {simkl_id}. Cannot fetch details.")
                return
        except Exception as e:
            logger.error(f"[CacheEnhance] Error fetching details for {media_type} ID {simkl_id}: {e}", exc_info=True)
            return

        if details:
            overview = details.get('overview')
            # imdb_id is part of 'ids', which cache_media_info handles.
            
            poster_url_from_api = details.get('poster') # This is usually like "ab/cdfg..." or a full path for some endpoints

            logger.info(f"[CacheEnhance] Fetched for ID {simkl_id}: overview ({'yes' if overview else 'no'}), "
                        f"imdb_id (in ids: {'yes' if details.get('ids', {}).get('imdb') else 'no'}), "
                        f"poster_url ({poster_url_from_api or 'no'})")

            # Use existing cache_media_info to update the cache.
            # This method handles finding/updating existing entries by simkl_id or original_input_key.
            # Use existing cache_media_info to update the cache.
            self.cache_media_info(
                original_title_key=original_input_key,
                simkl_id=simkl_id,
                display_name=details.get('title', resolved_title_hint),
                media_type=details.get('type', media_type), # Use API's type if available
                # season and episode are not typically part of get_movie_details/get_show_details for a general item,
                # but if this method were to be used for specific episodes, they'd need to be passed.
                # For now, assume this fetches general movie/show details.
                season=details.get('season'), # If API provides it (unlikely for base show/movie details)
                episode=details.get('episode'), # If API provides it
                year=details.get('year'),
                runtime_minutes=details.get('runtime'),
                api_ids=details.get('ids'),
                overview=overview,
                poster_url=poster_url_from_api,
                source_description="simkl_api_cache_enhance", # Specific source
                original_filepath_if_any=original_input_key if os.path.sep in original_input_key or (os.path.altsep and os.path.altsep in original_input_key) else None, # Pass if original_input_key is a path
                _api_full_details=details
            )
        else:
            logger.warning(f"[CacheEnhance] Failed to fetch full details for {media_type} ID {simkl_id} (details object was None).")