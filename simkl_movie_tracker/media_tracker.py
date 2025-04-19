# media_tracker.py

import pygetwindow as gw
import win32gui
import win32process
import psutil
from guessit import guessit
import re
import logging
import time
import os
import json
import threading
import logging.handlers
import requests # For player web interfaces
import re # For parsing MPC variables.html
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


# Setup Playback Logger
playback_log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'playback_log.jsonl')
playback_logger = logging.getLogger('PlaybackLogger')
playback_logger.setLevel(logging.INFO)
# Use a rotating file handler (5MB per file, keep 3 backups)
formatter = logging.Formatter('{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}') # Raw JSON message
handler = logging.handlers.RotatingFileHandler(playback_log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
handler.setFormatter(formatter)
playback_logger.addHandler(handler)
playback_logger.propagate = False # Prevent double logging to root logger

# List of supported video player executable names
VIDEO_PLAYER_EXECUTABLES = [
    'vlc.exe',
    'mpc-hc.exe',
    'mpc-hc64.exe',
    'mpc-be.exe',
    'mpc-be64.exe', # Added 64bit mpc-be
    'wmplayer.exe',
    'mpv.exe',
    'PotPlayerMini.exe',
    'PotPlayerMini64.exe',
    'smplayer.exe',
    'kmplayer.exe',
    'GOM.exe',
    'MediaPlayerClassic.exe',
]

# List of supported video player window title keywords (as fallback)
VIDEO_PLAYER_KEYWORDS = [
    'VLC',
    'MPC-HC',
    'MPC-BE',
    'Windows Media Player',
    'mpv',
    'PotPlayer',
    'SMPlayer',
    'KMPlayer',
    'GOM Player',
    'Media Player Classic'
]

# Average duration dictionary removed as we now rely on player/API data

# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 10

# Playback states
PLAYING = "playing"
PAUSED = "paused"
STOPPED = "stopped"

# Polling and monitoring constants (These might be less relevant now without the specific monitor classes)
# MONITOR_POLL_INTERVAL = 10
# MONITOR_RECONNECT_INTERVAL = 30
# MONITOR_TIMEOUT = 5
# PLAYER_ACTIVITY_THRESHOLD = 300

class MediaCache:
    """Cache for storing identified media to avoid repeated searches"""

    def __init__(self, cache_file="media_cache.json"):
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), cache_file)
        self.cache = self._load_cache()

    def _load_cache(self):
        """Load the cache from file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
        return {}

    def _save_cache(self):
        """Save the cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def get(self, title):
        """Get movie info from cache"""
        return self.cache.get(title.lower())

    def set(self, title, movie_info):
        """Store movie info in cache"""
        self.cache[title.lower()] = movie_info
        self._save_cache()

    def get_all(self):
        """Get all cached movie info"""
        return self.cache

class BacklogCleaner:
    """Manages a backlog of watched movies to sync when connection is restored"""

    def __init__(self, backlog_file="backlog.json"):
        self.backlog_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), backlog_file)
        self.backlog = self._load_backlog()

    def _load_backlog(self):
        """Load the backlog from file"""
        if os.path.exists(self.backlog_file):
            try:
                with open(self.backlog_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading backlog: {e}")
        return []

    def _save_backlog(self):
        """Save the backlog to file"""
        try:
            with open(self.backlog_file, 'w') as f:
                json.dump(self.backlog, f)
        except Exception as e:
            logger.error(f"Error saving backlog: {e}")

    def add(self, simkl_id, title):
        """Add a movie to the backlog"""
        entry = {
            "simkl_id": simkl_id,
            "title": title,
            "timestamp": datetime.now().isoformat()
        }

        # Don't add duplicates
        for item in self.backlog:
            if item.get("simkl_id") == simkl_id:
                return

        self.backlog.append(entry)
        self._save_backlog()
        logger.info(f"Added '{title}' to backlog for future syncing")

    def get_pending(self):
        """Get all pending backlog entries"""
        return self.backlog

    def remove(self, simkl_id):
        """Remove an entry from the backlog"""
        self.backlog = [item for item in self.backlog if item.get("simkl_id") != simkl_id]
        self._save_backlog()

    def clear(self):
        """Clear the entire backlog"""
        self.backlog = []
        self._save_backlog()

class MovieScrobbler:
    """Tracks movie viewing and scrobbles to Simkl"""

    def __init__(self, client_id=None, access_token=None, testing_mode=False):
        self.client_id = client_id
        self.access_token = access_token
        self.testing_mode = testing_mode # Add testing mode flag
        self.currently_tracking = None
        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.state = STOPPED
        self.previous_state = STOPPED
        self.estimated_duration = None # Kept for logging comparison, but not used for completion logic
        self.simkl_id = None
        self.movie_name = None
        self.last_scrobble_time = 0
        self.media_cache = MediaCache()
        self.backlog = BacklogCleaner()
        self.last_progress_check = 0  # Time of last progress threshold check
        self.completion_threshold = 80  # Default completion threshold (percent)
        self.completed = False  # Flag to track if movie has been marked as complete
        self.current_position_seconds = 0 # Current playback position in seconds
        self.total_duration_seconds = None # Total duration in seconds (if known)
        self._last_connection_error_log = {} # Track player connection errors

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
            "estimated_duration_seconds": self.estimated_duration, # Logged for comparison
            "completion_percent_accumulated": self._calculate_percentage(use_accumulated=True),
            "completion_percent_position": self._calculate_percentage(use_position=True),
            "is_complete_flag": self.completed,
        }
        if extra_data:
            log_entry.update(extra_data)

        # Use json.dumps to ensure proper JSON formatting within the log message
        try:
            playback_logger.info(json.dumps(log_entry))
        except Exception as e:
            logger.error(f"Failed to log playback event: {e} - Data: {log_entry}")


    def _get_player_position_duration(self, process_name):
        """
        Get current position and total duration from supported media players via web interfaces.
        Requires the web interface to be enabled in the player settings.
        Args:
            process_name (str): The executable name of the player process.
        Returns:
            tuple: (current_position_seconds, total_duration_seconds) or (None, None) if unavailable/unsupported.
        """
        position = None
        duration = None
        player_interface_url = None
        process_name_lower = process_name.lower() if process_name else ''

        try:
            # --- VLC Integration ---
            if process_name_lower == 'vlc.exe':
                player_interface_url = 'http://localhost:8080/requests/status.json'
                # TODO: Add configuration for VLC password if needed
                # auth = ('', vlc_password) if vlc_password else None
                response = requests.get(player_interface_url, timeout=0.5) # Short timeout
                response.raise_for_status()
                data = response.json()
                position = data.get('time')
                duration = data.get('length')

            # --- MPC-HC / MPC-BE Integration ---
            elif process_name_lower in ['mpc-hc.exe', 'mpc-hc64.exe', 'mpc-be.exe', 'mpc-be64.exe']:
                player_interface_url = 'http://localhost:13579/variables.html'
                response = requests.get(player_interface_url, timeout=0.5) # Short timeout
                response.raise_for_status()
                html_content = response.text
                # Extract variables using regex
                pos_match = re.search(r'<p id="position">(\d+)</p>', html_content)
                dur_match = re.search(r'<p id="duration">(\d+)</p>', html_content)
                # MPC reports position/duration in milliseconds
                if pos_match and dur_match:
                    position = int(pos_match.group(1)) / 1000.0
                    duration = int(dur_match.group(1)) / 1000.0

            # --- Add other player integrations here ---
            # Example: Add PotPlayer integration if it has a web API or similar

            if position is not None and duration is not None:
                # Basic validation
                if isinstance(position, (int, float)) and isinstance(duration, (int, float)) and duration >= 0 and position >= 0:
                     # Ensure position doesn't exceed duration slightly due to timing
                    position = min(position, duration)
                    return round(position, 2), round(duration, 2)
                else:
                    logger.debug(f"Invalid position/duration data received from {process_name}: pos={position}, dur={duration}")
                    return None, None

        except requests.exceptions.RequestException:
            # Log connection errors less frequently
            now = time.time()
            last_log_time = self._last_connection_error_log.get(process_name, 0)
            if now - last_log_time > 60: # Log max once per minute per player
                logger.warning(f"Could not connect to {process_name} web interface at {player_interface_url or 'default URL'}. Is it enabled/running?")
                self._last_connection_error_log[process_name] = now
        except Exception as e:
            logger.error(f"Error processing player ({process_name}) interface data: {e}")

        return None, None # Return None if unsupported, error occurred, or data invalid

    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token

    def process_window(self, window_info):
        """Process the current window and update scrobbling state"""
        if not is_video_player(window_info):
            if self.state != STOPPED:
                logger.info(f"Media player closed or changed, stopping tracking for: {self.currently_tracking}")
                self.stop_tracking()
            return None

        # Get the movie title
        movie_title = parse_movie_title(window_info)
        if not movie_title:
             if self.state != STOPPED:
                 logger.debug(f"Could not parse movie title from '{window_info.get('title', '')}', stopping tracking.")
                 self.stop_tracking()
             return None

        # Check if it's a new movie
        if self.currently_tracking != movie_title:
            if self.currently_tracking: # Stop previous before starting new
                 logger.info(f"New movie detected ('{movie_title}'), stopping tracking for '{self.currently_tracking}'")
                 self.stop_tracking()
            self._start_new_movie(movie_title)

        # It's the same movie (or just started), update tracking
        return self._update_tracking(window_info)

    def _start_new_movie(self, movie_title):
        """Start tracking a new movie"""
        logger.info(f"Starting to track: {movie_title}")

        # Check if we've seen this movie before in our cache
        cached_info = self.media_cache.get(movie_title)

        if cached_info:
            self.simkl_id = cached_info.get("simkl_id")
            self.movie_name = cached_info.get("movie_name", movie_title)
            self.total_duration_seconds = cached_info.get("duration_seconds") # Get duration from cache if available
            self.estimated_duration = self.total_duration_seconds # Align estimated with known, if available
            logger.info(f"Using cached info for '{movie_title}' (Simkl ID: {self.simkl_id}, Duration: {self.total_duration_seconds}s)")
        else:
            # Will be populated later by the main app after search or player query
            self.simkl_id = None
            self.movie_name = None
            self.estimated_duration = None # Duration is unknown initially
            self.total_duration_seconds = None

        self.currently_tracking = movie_title
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.watch_time = 0
        self.current_position_seconds = 0 # Reset position
        # total_duration_seconds is set above based on cache or None
        self.state = PLAYING # Assume playing initially
        self.previous_state = STOPPED
        self.completed = False  # Reset completed flag for new movie
        self.last_progress_check = time.time()

        # Log start event
        self._log_playback_event("start_tracking")

    def _update_tracking(self, window_info=None):
        """Update tracking for the current movie, including position and duration if possible."""
        if not self.currently_tracking or not self.last_update_time:
            return None

        current_time = time.time()

        # --- Get Position/Duration (From Player Integration) ---
        process_name = window_info.get('process_name') if window_info else None
        pos, dur = None, None
        if process_name:
            pos, dur = self._get_player_position_duration(process_name)

        position_updated = False
        if pos is not None and dur is not None and dur > 0: # Ensure duration is positive
             # Update total duration if player provides it and it wasn't known or differs
             if self.total_duration_seconds is None or abs(self.total_duration_seconds - dur) > 1: # Allow 1s difference
                 logger.info(f"Updating total duration from {self.total_duration_seconds}s to {dur}s based on player info.")
                 self.total_duration_seconds = dur
                 self.estimated_duration = dur # Keep estimate aligned

             # Detect seeking
             time_diff = current_time - self.last_update_time
             # Only detect seek if time has passed and we were playing
             if time_diff > 0.1 and self.state == PLAYING:
                 pos_diff = pos - self.current_position_seconds
                 # Allow for small discrepancies (e.g., 2 seconds) + normal playback time
                 if abs(pos_diff - time_diff) > 2.0:
                      logger.info(f"Seek detected: Position changed by {pos_diff:.1f}s in {time_diff:.1f}s (Expected ~{time_diff:.1f}s).")
                      self._log_playback_event("seek", {"previous_position_seconds": round(self.current_position_seconds, 2), "new_position_seconds": pos})
                      # Optional: Adjust accumulated watch time based on seek? (More complex)

             self.current_position_seconds = pos
             position_updated = True
        # --- End Position/Duration ---

        # Determine playback state (TODO: Enhance with player state if available)
        if self._detect_pause(window_info):
            new_state = PAUSED
        else:
            new_state = PLAYING

        # Calculate elapsed time for accumulated watch time
        elapsed = current_time - self.last_update_time
        if elapsed < 0: elapsed = 0 # Prevent negative time if clock changes
        # Sanity check for large gaps (e.g., sleep)
        if elapsed > 60:
            logger.warning(f"Large time gap detected ({elapsed:.1f}s), capping at 10 seconds for accumulated time.")
            elapsed = 10

        # Only increment accumulated watch time if we were playing
        if self.state == PLAYING:
            self.watch_time += elapsed

        # Handle state changes
        state_changed = (new_state != self.state)
        if state_changed:
            logger.info(f"Playback state changed: {self.state} -> {new_state}")
            self.previous_state = self.state
            self.state = new_state
            # Log state change
            self._log_playback_event("state_change", {"previous_state": self.previous_state})

        self.last_update_time = current_time

        # --- Calculate Percentage ---
        percentage = self._calculate_percentage(use_position=position_updated)
        # --- End Calculate Percentage ---

        # Log progress update periodically or on state change/seek
        log_progress = state_changed or position_updated or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        if log_progress:
             self._log_playback_event("progress_update")

        # Check completion threshold
        # Use self.is_complete() which handles the logic including the flag
        if not self.completed and (current_time - self.last_progress_check > 30):
            if self.is_complete(): # Check if threshold is met based on current state
                 logger.info(f"Completion threshold ({self.completion_threshold}%) met for '{self.movie_name or self.currently_tracking}'")
                 self._log_playback_event("completion_threshold_reached")
                 if self.simkl_id:
                     self.mark_as_finished(self.simkl_id, self.movie_name or self.currently_tracking)
                 else:
                     logger.warning("Cannot mark as finished: Simkl ID unknown.")
                     # Consider adding to backlog even without ID? Maybe not useful.
            self.last_progress_check = time.time() # Reset check timer regardless

        # Scrobble update (consider adjusting frequency/logic based on Simkl needs)
        should_scrobble = state_changed or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        if should_scrobble and self.simkl_id:
            self.last_scrobble_time = current_time
            self._log_playback_event("scrobble_update") # Log before returning data
            return {
                "title": self.currently_tracking,
                "movie_name": self.movie_name,
                "simkl_id": self.simkl_id,
                "state": self.state,
                "progress": percentage,
                "watched_seconds": round(self.watch_time, 2),
                "current_position_seconds": self.current_position_seconds,
                "total_duration_seconds": self.total_duration_seconds,
                "estimated_duration_seconds": self.estimated_duration # Keep for reference
            }

        return None

    def _calculate_percentage(self, use_position=False, use_accumulated=False):
        """Calculates completion percentage. Prefers position/duration if use_position is True and data is valid."""
        percentage = None
        # Try position first if requested and valid
        if use_position and self.current_position_seconds is not None and self.total_duration_seconds is not None and self.total_duration_seconds > 0:
            percentage = min(100, (self.current_position_seconds / self.total_duration_seconds) * 100)
        # Fallback to accumulated time vs known duration (player/API/cache)
        elif (use_accumulated or not use_position) and self.total_duration_seconds is not None and self.total_duration_seconds > 0:
             percentage = min(100, (self.watch_time / self.total_duration_seconds) * 100)
        # If duration is completely unknown, cannot calculate percentage

        return percentage


    def _detect_pause(self, window_info):
        """Detect if playback is paused based on window title."""
        # TODO: Enhance with player-specific state checks if possible via web interface/API
        # Some players indicate pause in the window title
        if window_info and window_info.get('title'):
            title_lower = window_info['title'].lower()
            if "paused" in title_lower: # More general check
                return True

        # For now, we assume it's playing if the player is open and title doesn't indicate pause
        return False

    def stop_tracking(self):
        """Stop tracking the current movie"""
        if not self.currently_tracking:
            return

        # --- Get final state before logging stop ---
        # Use the last known state for the stop log
        final_state = self.state
        final_pos = self.current_position_seconds
        final_watch_time = self.watch_time
        final_scrobble_info = { # Construct based on last known state
                "title": self.currently_tracking,
                "movie_name": self.movie_name,
                "simkl_id": self.simkl_id,
                "state": STOPPED, # Explicitly stopped
                "progress": self._calculate_percentage(use_position=True) or self._calculate_percentage(use_accumulated=True),
                "watched_seconds": round(final_watch_time, 2),
                "current_position_seconds": final_pos,
                "total_duration_seconds": self.total_duration_seconds,
                "estimated_duration_seconds": self.estimated_duration
            }
        # --- End final state capture ---

        # Log stop event *before* resetting state
        self._log_playback_event("stop_tracking", extra_data={"final_state": final_state, "final_position": final_pos, "final_watch_time": final_watch_time})


        # Reset tracking state
        logger.debug(f"Resetting tracking state for {self.currently_tracking}")
        self.currently_tracking = None
        self.state = STOPPED
        self.previous_state = self.state # Update previous state as well
        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.current_position_seconds = 0
        self.total_duration_seconds = None
        self.estimated_duration = None
        self.simkl_id = None
        self.movie_name = None
        self.completed = False # Ensure completed is reset

        # Return the constructed final scrobble info
        return final_scrobble_info

    def mark_as_finished(self, simkl_id, title):
        """Mark a movie as finished, either via API or backlog. Sets self.completed on success."""
        # Check testing_mode first
        if self.testing_mode:
            logger.info(f"TEST MODE: Simulating marking '{title}' (ID: {simkl_id}) as watched")
            self.completed = True # Set completed flag in test mode
            self._log_playback_event("marked_as_finished_test_mode")
            return True

        if not self.client_id or not self.access_token:
            logger.error("Cannot mark movie as finished: missing API credentials")
            self._log_playback_event("marked_as_finished_fail_credentials")
            self.backlog.add(simkl_id, title) # Backlog add logs itself
            return False

        try:
            # Import inside method to avoid circular imports
            from simkl_movie_tracker.simkl_api import mark_as_watched
            
            result = mark_as_watched(simkl_id, self.client_id, self.access_token)
            if result:
                logger.info(f"Successfully marked '{title}' as watched on Simkl")
                self.completed = True  # Update completed flag ONLY on success
                # Log successful marking
                self._log_playback_event("marked_as_finished_api_success")
                return True
            else:
                logger.warning(f"Failed to mark '{title}' as watched, adding to backlog")
                # Log API failure and backlog add
                self._log_playback_event("marked_as_finished_api_fail")
                self.backlog.add(simkl_id, title) # Backlog add logs itself
                return False
        except Exception as e:
            logger.error(f"Error marking movie as watched: {e}")
            # Log exception and backlog add
            self._log_playback_event("marked_as_finished_api_error", {"error": str(e)})
            self.backlog.add(simkl_id, title) # Backlog add logs itself
            return False

    def process_backlog(self):
        """Process pending backlog items"""
        if not self.client_id or not self.access_token:
            return 0

        from simkl_movie_tracker.simkl_api import mark_as_watched # Keep import local

        success_count = 0
        pending = self.backlog.get_pending()

        if not pending:
            return 0

        logger.info(f"Processing backlog: {len(pending)} items")

        # Process in reverse order? Or keep order? Keep order for now.
        items_to_process = list(pending) # Create copy to iterate over while modifying original

        for item in items_to_process:
            simkl_id = item.get("simkl_id")
            title = item.get("title", "Unknown")
            timestamp = item.get("timestamp")

            if simkl_id:
                logger.info(f"Backlog: Attempting to mark '{title}' (ID: {simkl_id}, Added: {timestamp}) as watched")
                try:
                    result = mark_as_watched(simkl_id, self.client_id, self.access_token)
                    if result:
                        logger.info(f"Backlog: Successfully marked '{title}' as watched")
                        self.backlog.remove(simkl_id) # Remove from original list
                        success_count += 1
                        self._log_playback_event("backlog_sync_success", {"backlog_simkl_id": simkl_id, "backlog_title": title})
                    else:
                        logger.warning(f"Backlog: Failed to mark '{title}' as watched via API")
                        self._log_playback_event("backlog_sync_fail", {"backlog_simkl_id": simkl_id, "backlog_title": title})
                        # Keep item in backlog for next try
                except Exception as e:
                    logger.error(f"Backlog: Error processing '{title}': {e}")
                    self._log_playback_event("backlog_sync_error", {"backlog_simkl_id": simkl_id, "backlog_title": title, "error": str(e)})
                    # Keep item in backlog for next try
            else:
                 logger.warning(f"Backlog: Skipping item with missing Simkl ID: {item}")
                 # Optionally remove invalid items? For now, keep them.
                 # self.backlog.remove(simkl_id) # Requires careful handling if ID is None

        if success_count > 0:
             logger.info(f"Backlog processing finished: {success_count} items synced.")
        elif items_to_process:
             logger.info("Backlog processing finished: No items synced successfully.")


        return success_count

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
            if runtime: # Runtime from Simkl API is usually in minutes
                api_duration_seconds = runtime * 60

            # Determine the best duration to cache: Player > API > Existing Cache > None
            current_cached_info = self.media_cache.get(title)
            existing_cached_duration = current_cached_info.get("duration_seconds") if current_cached_info else None

            # Use current total_duration_seconds if known (likely from player), else API, else existing cache
            duration_to_cache = self.total_duration_seconds if self.total_duration_seconds is not None else api_duration_seconds
            if duration_to_cache is None:
                duration_to_cache = existing_cached_duration

            if duration_to_cache:
                cached_data["duration_seconds"] = duration_to_cache
                logger.info(f"Caching duration information: {duration_to_cache} seconds for '{movie_name}'")
            else:
                 logger.info(f"No duration information available to cache for '{movie_name}'")

            self.media_cache.set(title, cached_data)

            # If this is the movie we're currently tracking, update its duration if needed
            if self.currently_tracking == title:
                self.simkl_id = simkl_id
                self.movie_name = movie_name

                # Update duration if cache provides a value and we don't have one,
                # or if the cached value is different (though player value should take precedence)
                if duration_to_cache is not None and self.total_duration_seconds != duration_to_cache:
                     if self.total_duration_seconds is None: # Only update if we didn't already get it from player
                          logger.info(f"Updating known duration from None to {duration_to_cache}s based on cache/API info")
                          self.total_duration_seconds = duration_to_cache
                          self.estimated_duration = duration_to_cache # Align estimate


    def is_complete(self, threshold=None):
        """Check if the movie is considered watched (default: based on instance threshold), prioritizing position."""
        if not self.currently_tracking:
            return False

        # Return completion flag status immediately if already marked
        if self.completed:
            return True

        # Use provided threshold or instance default
        if threshold is None:
            threshold = self.completion_threshold

        # Calculate percentage. Requires known duration (player/API/cache).
        # Prioritize position-based calculation.
        percentage = self._calculate_percentage(use_position=True)
        if percentage is None: # Fallback to accumulated time if position failed but duration is known
             percentage = self._calculate_percentage(use_accumulated=True)

        # If percentage could not be calculated (duration unknown), it's not complete.
        if percentage is None:
            # logger.debug(f"Cannot determine completion for '{self.currently_tracking}', duration unknown.")
            return False

        # Check threshold.
        is_past_threshold = percentage >= threshold
        # No need for debug log here, completion_threshold_reached event covers it

        return is_past_threshold


def get_process_name_from_hwnd(hwnd):
    """Get the process name from a window handle."""
    try:
        # Get the process ID from the window handle
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        # Get the process name from the process ID
        process = psutil.Process(pid)
        return process.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, win32process.error) as e:
        logger.debug(f"Error getting process name for HWND {hwnd}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting process name: {e}")
    return None

# Modified function to get all windows, not just the active one
def get_all_windows_info():
    """Get information about all open windows, not just the active one."""
    windows_info = []

    try:
        # Get all visible windows using pygetwindow
        all_windows = gw.getAllWindows()

        for window in all_windows:
            if window.visible and window.title:
                try:
                    # Get handle from window
                    hwnd = window._hWnd

                    # Get process name
                    process_name = get_process_name_from_hwnd(hwnd)

                    # Only include windows with valid process names and titles
                    if process_name and window.title:
                        windows_info.append({
                            'hwnd': hwnd,
                            'title': window.title,
                            'process_name': process_name
                        })
                except Exception as e:
                    # Log error getting info for a specific window but continue
                    logger.debug(f"Error processing window (HWND: {window._hWnd}, Title: {window.title}): {e}")

    except Exception as e:
        logger.error(f"Error getting all windows info: {e}")

    return windows_info


# --- Functions related to identifying active media ---

def get_active_window_info():
    """Get information about the currently active window."""
    try:
        active_window = gw.getActiveWindow()
        if active_window:
            hwnd = active_window._hWnd
            process_name = get_process_name_from_hwnd(hwnd)
            if process_name and active_window.title:
                 return {
                     'hwnd': hwnd,
                     'title': active_window.title,
                     'process_name': process_name
                 }
    except Exception as e:
        logger.error(f"Error getting active window info: {e}")
    return None

def get_active_window_title():
    """Get the title of the currently active window."""
    info = get_active_window_info()
    return info['title'] if info else None

def is_video_player(window_info):
    """
    Check if the window information corresponds to a known video player.

    Args:
        window_info (dict): Dictionary containing 'process_name' and 'title'.

    Returns:
        bool: True if it's a known video player, False otherwise.
    """
    if not window_info:
        return False

    process_name = window_info.get('process_name', '').lower()
    # title = window_info.get('title', '') # Title check removed for now

    # Check against known executable names first
    if process_name in [p.lower() for p in VIDEO_PLAYER_EXECUTABLES]:
        return True

    return False

def is_movie(window_title):
    """Determine if the media is likely a movie using guessit."""
    if not window_title:
        return False

    try:
        guess = guessit(window_title)
        media_type = guess.get('type')

        # Primarily rely on guessit's type detection
        if media_type == 'movie':
            # Optional: Add checks to exclude things guessit might misclassify
            # e.g., if 'episode' or 'season' is also present, maybe ignore?
            if 'episode' not in guess and 'season' not in guess:
                 return True
            else:
                 logger.debug(f"Guessit identified as movie but found episode/season: {guess}")
                 return False # Likely a TV show episode named like a movie

    except Exception as e:
        logger.error(f"Error using guessit on title '{window_title}': {e}")

    return False


def parse_movie_title(window_title_or_info):
    """
    Extract a clean movie title from the window title or info dictionary.
    Tries to remove player-specific clutter and episode info.

    Args:
        window_title_or_info (str or dict): The window title string or info dict.

    Returns:
        str: A cleaned movie title, or None if parsing fails or it's not likely a movie.
    """
    if isinstance(window_title_or_info, dict):
        window_title = window_title_or_info.get('title', '')
    elif isinstance(window_title_or_info, str):
        window_title = window_title_or_info
    else:
        return None

    if not window_title:
        return None

    # --- Initial check if it's likely a movie ---
    # This check is important to avoid trying to parse titles from non-movie windows
    if not is_movie(window_title):
         # logger.debug(f"Title '{window_title}' doesn't seem to be a movie based on guessit.")
         return None
    # --- End initial check ---


    # --- Clean the title ---
    cleaned_title = window_title

    # Remove common player indicators first
    player_patterns = [
        r'\s*-\s*VLC media player$',
        r'\s*-\s*MPC-HC.*$',
        r'\s*-\s*MPC-BE.*$',
        r'\s*-\s*Windows Media Player$',
        r'\s*-\s*mpv$',
        r'\s+\[.*PotPlayer.*\]$', # PotPlayer often adds [Playing] etc.
        r'\s*-\s*SMPlayer.*$',
        r'\s*-\s*KMPlayer.*$',
        r'\s*-\s*GOM Player.*$',
        r'\s*-\s*Media Player Classic.*$',
        r'\s*\[Paused\]$', # General pause indicator
        r'\s*-\s*Paused$',
    ]
    for pattern in player_patterns:
        cleaned_title = re.sub(pattern, '', cleaned_title, flags=re.IGNORECASE).strip()


    # Use guessit to get the core title if possible
    try:
        guess = guessit(cleaned_title)
        # Prefer guessit's title if found and seems reasonable
        if 'title' in guess:
             # Basic sanity check: avoid excessively short titles from guessit
             if len(guess['title']) > 2:
                  # If guessit also found a year, include it
                  if 'year' in guess:
                       # Ensure year is plausible
                       if isinstance(guess['year'], int) and 1880 < guess['year'] < datetime.now().year + 2:
                            return f"{guess['title']} ({guess['year']})"
                       else:
                            return guess['title'] # Return title without implausible year
                  else:
                       return guess['title']
             else:
                  logger.debug(f"Guessit title '{guess['title']}' too short, using cleaned title.")
        # Fallback to the regex-cleaned title if guessit didn't provide a good one
        return cleaned_title.strip()

    except Exception as e:
         logger.error(f"Error using guessit for title parsing '{cleaned_title}': {e}")
         # Fallback to the regex-cleaned title on error
         return cleaned_title.strip()


class MonitorAwareScrobbler(MovieScrobbler):
    """
    Enhanced version of MovieScrobbler that handles its own monitoring of windows.
    This class adds window monitoring functionality on top of the basic scrobbling.
    """

    def __init__(self, client_id=None, access_token=None, testing_mode=False):
        super().__init__(client_id, access_token, testing_mode)
        self.monitor_thread = None
        self.poll_interval = 10  # Default polling interval in seconds
        self.monitoring = False
        self.last_window_info = None
        self.check_all_windows = True  # Whether to check all windows or just active window

    def set_poll_interval(self, seconds):
        """Set the polling interval for window checks"""
        if seconds > 0:
            self.poll_interval = seconds
            logger.info(f"Set polling interval to {seconds} seconds")

    def start_monitoring(self):
        """Start the window monitoring thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("Monitor thread already running")
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Started window monitoring thread")

    def stop_monitoring(self):
        """Stop the window monitoring thread"""
        self.monitoring = False
        if self.monitor_thread:
            if self.monitor_thread.is_alive():
                logger.info("Stopping monitor thread...")
                # Join with timeout to avoid blocking
                self.monitor_thread.join(timeout=1.0)
            self.monitor_thread = None
        logger.info("Window monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop that checks for video player windows"""
        logger.info("Monitor loop started")
        
        while self.monitoring:
            try:
                # Process active window first (most likely scenario)
                active_window_info = get_active_window_info()
                if active_window_info and is_video_player(active_window_info):
                    scrobble_data = self.process_window(active_window_info)
                    self.last_window_info = active_window_info
                    
                    # Check if we need to update movie info (for movies not in cache)
                    if scrobble_data:
                        # This would be handled by the main app's _handle_scrobble_update
                        # but we log it here in case someone uses this class directly
                        logger.debug(f"Scrobble update: {scrobble_data.get('title')} - {scrobble_data.get('progress'):.1f}%")
                
                # Optionally check all windows (more resource intensive)
                elif self.check_all_windows:
                    # Get all visible windows and look for video players
                    all_windows = get_all_windows_info()
                    video_players = [w for w in all_windows if is_video_player(w)]
                    
                    if video_players:
                        # Take the first video player window for now
                        # Could be enhanced to track multiple players or prioritize
                        window_info = video_players[0]
                        scrobble_data = self.process_window(window_info)
                        self.last_window_info = window_info
                        
                        if scrobble_data:
                            logger.debug(f"Scrobble update (non-active window): {scrobble_data.get('title')} - {scrobble_data.get('progress'):.1f}%")
                    
                    # If no players found but we were tracking something, process null to stop
                    elif self.currently_tracking:
                        self.process_window(None)
                
                # No video player found, stop tracking if needed
                elif self.currently_tracking and not is_video_player(self.last_window_info if self.last_window_info else {}):
                    self.process_window(None)
                    self.last_window_info = None
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            
            # Sleep to avoid high CPU usage
            time.sleep(self.poll_interval)
            
        logger.info("Monitor loop terminated")

    def set_check_all_windows(self, check_all):
        """Set whether to check all windows or just active window"""
        self.check_all_windows = bool(check_all)
        logger.info(f"Set check_all_windows to {self.check_all_windows}")

# --- End of File ---