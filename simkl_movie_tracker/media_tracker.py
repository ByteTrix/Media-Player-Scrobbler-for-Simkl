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
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# List of supported video player executable names
VIDEO_PLAYER_EXECUTABLES = [
    'vlc.exe',
    'mpc-hc.exe', 
    'mpc-hc64.exe',
    'mpc-be.exe',
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

# Average movie durations in minutes for different movie types
# Used to estimate completion percentage when we can't get actual duration
AVERAGE_MOVIE_DURATION = {
    'default': 120,  # 2 hours
    'animated': 100,  # 1 hour 40 minutes
    'short': 90,      # 1 hour 30 minutes
    'documentary': 100, # 1 hour 40 minutes
}

# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 10

# Playback states
PLAYING = "playing"
PAUSED = "paused"
STOPPED = "stopped"

# Polling and monitoring constants
MONITOR_POLL_INTERVAL = 10  # How often to check for active players (seconds)
MONITOR_RECONNECT_INTERVAL = 30  # How often to try reconnecting to players (seconds)
MONITOR_TIMEOUT = 5  # Timeout for player connection attempts (seconds)
PLAYER_ACTIVITY_THRESHOLD = 300  # How long to consider a player "active" after last seen (seconds)

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
    
    def __init__(self, client_id=None, access_token=None):
        self.client_id = client_id
        self.access_token = access_token
        self.currently_tracking = None
        self.start_time = None
        self.last_update_time = None
        self.watch_time = 0
        self.state = STOPPED
        self.previous_state = STOPPED
        self.estimated_duration = None
        self.simkl_id = None
        self.movie_name = None
        self.last_scrobble_time = 0
        self.media_cache = MediaCache()
        self.backlog = BacklogCleaner()
        self.last_progress_check = 0  # Time of last progress threshold check
        self.completion_threshold = 80  # Default completion threshold (percent)
        self.completed = False  # Flag to track if movie has been marked as complete
        
    def set_credentials(self, client_id, access_token):
        """Set API credentials"""
        self.client_id = client_id
        self.access_token = access_token
        
    def process_window(self, window_info):
        """Process the current window and update scrobbling state"""
        if not is_video_player(window_info):
            if self.state != STOPPED:
                logger.info(f"Media player closed, stopping tracking for: {self.currently_tracking}")
                self.stop_tracking()
            return None
            
        # Get the movie title
        movie_title = parse_movie_title(window_info)
        if not movie_title:
            return None
            
        # Check if it's a new movie
        if self.currently_tracking != movie_title:
            self._start_new_movie(movie_title)
            
        # It's the same movie, update tracking
        return self._update_tracking(window_info)
        
    def _start_new_movie(self, movie_title):
        """Start tracking a new movie"""
        logger.info(f"Starting to track: {movie_title}")
        
        # Check if we've seen this movie before in our cache
        cached_info = self.media_cache.get(movie_title)
        
        if cached_info:
            self.simkl_id = cached_info.get("simkl_id")
            self.movie_name = cached_info.get("movie_name", movie_title)
            self.estimated_duration = cached_info.get("runtime", self._estimate_duration(movie_title))
            logger.info(f"Using cached info for '{movie_title}' (Simkl ID: {self.simkl_id}, Runtime: {self.estimated_duration} min)")
        else:
            # Will be populated later by the main app after search
            self.simkl_id = None
            self.movie_name = None
            self.estimated_duration = self._estimate_duration(movie_title)
        
        self.currently_tracking = movie_title
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.watch_time = 0
        self.state = PLAYING
        self.previous_state = STOPPED
        self.completed = False  # Reset completed flag for new movie
        self.last_progress_check = time.time()
        
    def _update_tracking(self, window_info=None):
        """Update tracking for the current movie"""
        if not self.currently_tracking or not self.last_update_time:
            return None
            
        current_time = time.time()
        
        # Determine playback state
        if self._detect_pause(window_info):
            new_state = PAUSED
        else:
            new_state = PLAYING
            # Only increment watch time if we're actually playing
            if self.state == PLAYING:
                elapsed = current_time - self.last_update_time
                # Sanity check: if elapsed time is too large, cap it 
                # (e.g. computer was sleeping)
                if elapsed > 60:  # More than a minute
                    logger.warning(f"Large time gap detected ({elapsed:.1f}s), capping at 10 seconds")
                    elapsed = 10
                self.watch_time += elapsed
            
        # Handle state changes
        state_changed = (new_state != self.state)
        if state_changed:
            logger.info(f"Playback state changed: {self.state} -> {new_state}")
            self.previous_state = self.state
            self.state = new_state
        
        self.last_update_time = current_time
        
        # Calculate percentage watched
        watched_minutes = self.watch_time / 60
        percentage = min(100, (watched_minutes / self.estimated_duration) * 100)
        
        # Check if we've reached the completion threshold (every 30 seconds)
        if (current_time - self.last_progress_check > 30 and 
            not self.completed and 
            self.simkl_id and 
            percentage >= self.completion_threshold):
            
            logger.info(f"Progress {percentage:.1f}% reached threshold ({self.completion_threshold}%) for '{self.movie_name or self.currently_tracking}'")
            self.mark_as_finished(self.simkl_id, self.movie_name or self.currently_tracking)
            self.completed = True
            self.last_progress_check = current_time
        
        # Scrobble if the state changed or it's been longer than poll interval
        should_scrobble = state_changed or (current_time - self.last_scrobble_time > DEFAULT_POLL_INTERVAL)
        
        if should_scrobble and self.simkl_id:
            self.last_scrobble_time = current_time
            return {
                "title": self.currently_tracking,
                "movie_name": self.movie_name,
                "simkl_id": self.simkl_id,
                "state": self.state,
                "progress": percentage,
                "watched_minutes": watched_minutes,
                "estimated_duration": self.estimated_duration
            }
        
        return None
        
    def _detect_pause(self, window_info):
        """Detect if playback is paused based on window title or other indicators"""
        # Some players indicate pause in the window title
        if window_info and window_info.get('title'):
            if " - Paused" in window_info['title'] or "[Paused]" in window_info['title']:
                return True
                
        # More sophisticated pause detection could be added here
        # For now, we assume it's playing if the player is open
        return False
        
    def stop_tracking(self):
        """Stop tracking the current movie"""
        if not self.currently_tracking:
            return
            
        # Update one last time to get final progress
        scrobble_info = self._update_tracking()
        
        # Reset tracking state
        self.currently_tracking = None
        self.state = STOPPED
        self.start_time = None
        self.last_update_time = None
        
        return scrobble_info
        
    def mark_as_finished(self, simkl_id, title):
        """Mark a movie as finished, either via API or backlog"""
        from simkl_movie_tracker.simkl_api import mark_as_watched
        
        # For test mode, bypass the API call
        if hasattr(self, 'testing_mode') and self.testing_mode:
            logger.info(f"TEST MODE: Simulating marking '{title}' as watched")
            self.completed = True
            return True
            
        if not self.client_id or not self.access_token:
            logger.error("Cannot mark movie as finished: missing API credentials")
            self.backlog.add(simkl_id, title)
            return False
            
        try:
            result = mark_as_watched(simkl_id, self.client_id, self.access_token)
            if result:
                logger.info(f"Successfully marked '{title}' as watched on Simkl")
                self.completed = True  # Update completed flag
                return True
            else:
                logger.warning(f"Failed to mark '{title}' as watched, adding to backlog")
                self.backlog.add(simkl_id, title)
                return False
        except Exception as e:
            logger.error(f"Error marking movie as watched: {e}")
            self.backlog.add(simkl_id, title)
            return False
            
    def process_backlog(self):
        """Process pending backlog items"""
        if not self.client_id or not self.access_token:
            return 0
            
        from simkl_movie_tracker.simkl_api import mark_as_watched
        
        success_count = 0
        pending = self.backlog.get_pending()
        
        if not pending:
            return 0
            
        logger.info(f"Processing backlog: {len(pending)} items")
        
        for item in pending:
            simkl_id = item.get("simkl_id")
            title = item.get("title", "Unknown")
            
            if simkl_id:
                try:
                    result = mark_as_watched(simkl_id, self.client_id, self.access_token)
                    if result:
                        logger.info(f"Backlog: Successfully marked '{title}' as watched")
                        self.backlog.remove(simkl_id)
                        success_count += 1
                    else:
                        logger.warning(f"Backlog: Failed to mark '{title}' as watched")
                except Exception as e:
                    logger.error(f"Backlog: Error processing '{title}': {e}")
            
        return success_count
        
    def cache_movie_info(self, title, simkl_id, movie_name, runtime=None):
        """
        Cache movie info to avoid repeated searches
        
        Args:
            title: Original movie title from window
            simkl_id: Simkl ID of the movie
            movie_name: Official movie name from Simkl
            runtime: Movie runtime in minutes from Simkl API
        """
        if title and simkl_id:
            cached_data = {
                "simkl_id": simkl_id,
                "movie_name": movie_name
            }
            
            # Add runtime if available
            if runtime:
                cached_data["runtime"] = runtime
                logger.info(f"Caching runtime information: {runtime} minutes for '{movie_name}'")
            
            self.media_cache.set(title, cached_data)
            
            # If this is the movie we're currently tracking, update our local copy
            if self.currently_tracking == title:
                self.simkl_id = simkl_id
                self.movie_name = movie_name
                
                # Update estimated duration if we have runtime from API
                if runtime:
                    logger.info(f"Updating estimated duration from {self.estimated_duration} to {runtime} minutes")
                    self.estimated_duration = runtime
                
    def is_complete(self, threshold=None):
        """Check if the movie is considered watched (default: based on instance threshold)"""
        if not self.currently_tracking:
            return False
            
        # Use provided threshold or instance default
        if threshold is None:
            threshold = self.completion_threshold
            
        watched_minutes = self.watch_time / 60
        percentage = min(100, (watched_minutes / self.estimated_duration) * 100)
        
        return percentage >= threshold or self.completed
        
    def _estimate_duration(self, movie_title):
        """Estimate movie duration based on title or guessit data"""
        # Try to get info from guessit
        guess = guessit(movie_title)
        
        duration = AVERAGE_MOVIE_DURATION['default']
        
        # Check if guessit found any helpful info
        if guess.get('type') == 'movie':
            # Check for hints in the title
            lower_title = movie_title.lower()
            
            if any(word in lower_title for word in ['animated', 'animation', 'cartoon', 'pixar', 'disney']):
                duration = AVERAGE_MOVIE_DURATION['animated']
            elif any(word in lower_title for word in ['documentary', 'biography', 'true story']):
                duration = AVERAGE_MOVIE_DURATION['documentary']
            elif any(word in lower_title for word in ['short']):
                duration = AVERAGE_MOVIE_DURATION['short']
        
        return duration

def get_process_name_from_hwnd(hwnd):
    """Get the process name from a window handle."""
    try:
        # Get the process ID from the window handle
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        
        # Get the process name from the process ID
        process = psutil.Process(pid)
        return process.name()
    except Exception as e:
        logger.debug(f"Error getting process name: {e}")
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
                    # Skip windows that cause errors
                    logger.debug(f"Error getting info for window '{window.title}': {e}")
                    continue
        
        return windows_info
    except Exception as e:
        logger.error(f"Error getting all windows info: {e}")
        return []

# Keep the original function for backward compatibility
def get_active_window_info():
    """Get detailed information about the active window, including process name and title."""
    try:
        # Get the handle of the active window
        hwnd = win32gui.GetForegroundWindow()
        
        # Get the title of the active window
        window_title = win32gui.GetWindowText(hwnd)
        
        # Get the process name of the active window
        process_name = get_process_name_from_hwnd(hwnd)
        
        return {
            'hwnd': hwnd,
            'title': window_title,
            'process_name': process_name
        }
    except Exception as e:
        logger.error(f"Error getting active window info: {e}")
        return {
            'hwnd': None,
            'title': None,
            'process_name': None
        }

def get_active_window_title():
    """Legacy method for backwards compatibility."""
    window_info = get_active_window_info()
    return window_info['title']

def is_video_player(window_info):
    """
    Determine if the active window is a video player based on process name and window title.
    
    Args:
        window_info: Dictionary containing window information (title, process_name)
        
    Returns:
        bool: True if the window is a video player, False otherwise
    """
    if isinstance(window_info, str):
        # Handle string input for backwards compatibility
        window_title = window_info
        window_info = {'title': window_title, 'process_name': None}
    
    if not window_info['title']:
        return False
        
    # Check process name (most reliable method)
    if window_info['process_name'] and window_info['process_name'].lower() in [exe.lower() for exe in VIDEO_PLAYER_EXECUTABLES]:
        logger.debug(f"Matched video player by process name: {window_info['process_name']}")
        return True
    
    window_title = window_info['title']
    
    # Exclude common non-media player applications
    non_players = ['Visual Studio Code', 'Chrome', 'Firefox', 'Edge', 'Explorer', 'Notepad']
    if any(app in window_title for app in non_players):
        return False
    
    # Check for media player keywords in window title
    for player in VIDEO_PLAYER_KEYWORDS:
        # Check for exact matches
        if player.lower() == window_title.lower():
            return True
        
        # Check for player name at the beginning of the title
        if window_title.lower().startswith(player.lower()):
            return True
        
        # Check for player name with common separators
        for separator in [' - ', ': ', ' | ']:
            if f"{separator}{player.lower()}" in window_title.lower() or f"{player.lower()}{separator}" in window_title.lower():
                return True
    
    # Fallback check
    return any(player.lower() in window_title.lower() for player in VIDEO_PLAYER_KEYWORDS)

def is_movie(window_title):
    """Determine if the media is a movie and not anime, series or TV show using guessit's detection."""
    # First try guessit detection
    guess = guessit(window_title)
    
    # Debug info
    logger.debug(f"Guessit result for '{window_title}': {guess}")
    
    # Use guessit's type detection - it can determine if content is movie or episode
    media_type = guess.get('type')
    
    # If guessit explicitly identified this as an episode, it's not a movie
    if media_type == 'episode':
        return False
    
    # If guessit explicitly identified this as a movie, check if it's anime
    if media_type == 'movie':
        # Exclude anime movies
        if guess.get('anime'):
            return False
        return True
    
    # If guessit couldn't determine the type, check additional indicators
    
    # Check for episode/season numbers which indicate TV shows
    if guess.get('episode') is not None or guess.get('season') is not None:
        return False
    
    # TV show indicators
    tv_indicators = [
        r'\bS\d+E\d+\b',              # S01E01 format
        r'\b\d+x\d+\b',                # 1x01 format
        r'season\s+\d+',               # "Season 1"
        r'episode\s+\d+',              # "Episode 1"
        r'\b(anime|series|tv show)\b', # Explicit indicators
    ]
    
    for pattern in tv_indicators:
        if re.search(pattern, window_title, re.IGNORECASE):
            return False
    
    # If we've gotten here and there's a title, it's likely a movie
    if guess.get('title'):
        return True
    
    return False

def parse_movie_title(window_title_or_info):
    """
    Parse the movie title from a video player window without cleaning.
    
    Args:
        window_title_or_info: Either a window title string or a window info dictionary
        
    Returns:
        str: The movie title, or None if not a movie or video player
    """
    # Handle different input types
    if isinstance(window_title_or_info, dict):
        window_info = window_title_or_info
        window_title = window_info['title']
    else:
        window_title = window_title_or_info
        window_info = {'title': window_title, 'process_name': None}
    
    # Log the input for debugging
    logger.debug(f"Parsing title from: {window_title}")
    
    # Check if it's a video player
    if not is_video_player(window_info):
        logger.debug(f"Not a video player: {window_title}")
        return None
    
    # Check if it's a movie and not anime/series/tv show
    if not is_movie(window_title):
        logger.debug(f"Not a movie: {window_title}")
        return None
    
    # Remove specific player indicators from title
    for player in VIDEO_PLAYER_KEYWORDS:
        if f" - {player}" in window_title:
            window_title = window_title.replace(f" - {player}", "")
    
    # Try guessit as a fallback if title seems invalid
    if not window_title or len(window_title) < 2:
        guess = guessit(window_title)
        guessed_title = guess.get('title')
        if guessed_title:
            logger.debug(f"Using guessit title instead: {guessed_title}")
            return guessed_title
    
    return window_title

class PlayerMonitor:
    """
    Monitors a specific media player and extracts currently playing media information.
    Works as a consistent connection to a single player instance.
    """
    
    def __init__(self, player_name, executable_names=None, window_title_keywords=None):
        self.player_name = player_name
        self.executable_names = executable_names or []
        self.window_title_keywords = window_title_keywords or []
        self.running = False
        self.connected = False
        self.last_activity = 0
        self.current_media = None
        self.current_state = STOPPED
        self.last_connection_attempt = 0
        self.window_info = None  # Store the current window info
        
    def check_if_running(self):
        """Check if this player is currently running by looking at all windows, not just active one"""
        all_windows = get_all_windows_info()
        
        for window_info in all_windows:
            # Check by process name (most reliable)
            if window_info['process_name'] and any(exe.lower() == window_info['process_name'].lower() for exe in self.executable_names):
                self.running = True
                self.last_activity = time.time()
                self.window_info = window_info
                return True
                
            # Check by window title keywords (fallback)
            if window_info['title'] and any(keyword.lower() in window_info['title'].lower() for keyword in self.window_title_keywords):
                self.running = True
                self.last_activity = time.time()
                self.window_info = window_info
                return True
        
        # Check if it's been inactive too long
        if time.time() - self.last_activity > PLAYER_ACTIVITY_THRESHOLD:
            if self.running:
                logger.info(f"Player {self.player_name} seems to be closed (no activity for {PLAYER_ACTIVITY_THRESHOLD} seconds)")
            self.running = False
            self.window_info = None
            
        return self.running
        
    def try_connect(self):
        """Try to establish a connection to the player for media monitoring"""
        if not self.running or not self.window_info:
            return False
            
        # Don't try connecting too frequently if previously failed
        if not self.connected and time.time() - self.last_connection_attempt < MONITOR_RECONNECT_INTERVAL:
            return False
            
        self.last_connection_attempt = time.time()
        
        try:
            # We're now using the stored window_info rather than the active window
            window_info = self.window_info
            
            # Simple connection check - can we read window title and is it a video player
            if is_video_player(window_info):
                movie_title = parse_movie_title(window_info)
                if movie_title:
                    if not self.connected:
                        logger.info(f"Connected to {self.player_name}")
                    self.connected = True
                    return True
                    
            if self.connected:
                logger.info(f"Lost connection to {self.player_name}")
                self.connected = False
                
            return False
        except Exception as e:
            logger.error(f"Error connecting to {self.player_name}: {e}")
            self.connected = False
            return False
            
    def get_playing_media(self):
        """Get information about currently playing media"""
        if not self.connected or not self.window_info:
            return None
            
        try:
            window_info = self.window_info
            
            if is_video_player(window_info):
                movie_title = parse_movie_title(window_info)
                if movie_title:
                    # Detect pause state
                    paused = self._detect_pause(window_info)
                    
                    media_info = {
                        'title': movie_title,
                        'state': PAUSED if paused else PLAYING,
                        'player': self.player_name,
                        'timestamp': time.time()
                    }
                    
                    self.current_media = movie_title
                    self.current_state = media_info['state']
                    return media_info
            
            # If we get here, no media is detected
            self.current_media = None
            self.current_state = STOPPED
            return None
            
        except Exception as e:
            logger.error(f"Error getting media info from {self.player_name}: {e}")
            return None
            
    def _detect_pause(self, window_info):
        """Detect if playback is paused based on window title or other indicators"""
        if window_info and window_info.get('title'):
            if " - Paused" in window_info['title'] or "[Paused]" in window_info['title']:
                return True
        return False

class PlayerMonitorManager:
    """
    Manages multiple player monitors and coordinates media information extraction.
    This is the main controller for tracking all media players.
    """
    
    def __init__(self):
        self.monitors = []
        self.active_monitor = None
        self.running = False
        self._setup_monitors()
        self.polling_thread = None
        self.last_report_time = 0  # Track when we last reported activity to prevent log spam
        
    def _setup_monitors(self):
        """Set up monitors for supported media players"""
        # VLC monitor
        vlc_monitor = PlayerMonitor(
            "VLC Media Player",
            executable_names=['vlc.exe'],
            window_title_keywords=['VLC']
        )
        self.monitors.append(vlc_monitor)
        
        # MPC-HC/BE monitor
        mpc_monitor = PlayerMonitor(
            "Media Player Classic",
            executable_names=['mpc-hc.exe', 'mpc-hc64.exe', 'mpc-be.exe', 'MediaPlayerClassic.exe'],
            window_title_keywords=['MPC-HC', 'MPC-BE', 'Media Player Classic']
        )
        self.monitors.append(mpc_monitor)
        
        # Windows Media Player monitor
        wmp_monitor = PlayerMonitor(
            "Windows Media Player",
            executable_names=['wmplayer.exe'],
            window_title_keywords=['Windows Media Player']
        )
        self.monitors.append(wmp_monitor)
        
        # MPV Player monitor
        mpv_monitor = PlayerMonitor(
            "MPV Player",
            executable_names=['mpv.exe'],
            window_title_keywords=['mpv']
        )
        self.monitors.append(mpv_monitor)
        
        # PotPlayer monitor
        potplayer_monitor = PlayerMonitor(
            "PotPlayer",
            executable_names=['PotPlayerMini.exe', 'PotPlayerMini64.exe'],
            window_title_keywords=['PotPlayer']
        )
        self.monitors.append(potplayer_monitor)
        
        # Additional players can be added similarly
        smplayer_monitor = PlayerMonitor(
            "SMPlayer",
            executable_names=['smplayer.exe'],
            window_title_keywords=['SMPlayer']
        )
        self.monitors.append(smplayer_monitor)
        
        kmplayer_monitor = PlayerMonitor(
            "KMPlayer",
            executable_names=['kmplayer.exe'],
            window_title_keywords=['KMPlayer']
        )
        self.monitors.append(kmplayer_monitor)
        
        gom_monitor = PlayerMonitor(
            "GOM Player",
            executable_names=['GOM.exe'],
            window_title_keywords=['GOM Player']
        )
        self.monitors.append(gom_monitor)
        
        logger.info(f"Set up {len(self.monitors)} player monitors")
        
    def start_monitoring(self):
        """Start monitoring all players"""
        if self.running:
            return
            
        self.running = True
        self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.polling_thread.start()
        logger.info("Started player monitoring")
        
    def stop_monitoring(self):
        """Stop monitoring all players"""
        if not self.running:
            return
            
        self.running = False
        if self.polling_thread:
            self.polling_thread.join(timeout=1)
        logger.info("Stopped player monitoring")
        
    def _polling_loop(self):
        """Main polling loop to check all players for activity"""
        while self.running:
            try:
                self._check_players()
                time.sleep(MONITOR_POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(MONITOR_POLL_INTERVAL)
                
    def _check_players(self):
        """Check all players for activity and update active player"""
        active_found = False
        
        for monitor in self.monitors:
            # Check if this player is running
            if monitor.check_if_running():
                # If running, try to connect and get media info
                if monitor.try_connect():
                    media_info = monitor.get_playing_media()
                    if media_info:
                        # This player is active and has media playing
                        prev_monitor = self.active_monitor
                        self.active_monitor = monitor
                        active_found = True
                        
                        # Only log when we switch players or every 5 minutes to avoid spam
                        if prev_monitor != monitor or time.time() - self.last_report_time > 300:
                            logger.info(f"Monitoring media: '{media_info['title']}' on {monitor.player_name}")
                            self.last_report_time = time.time()
                            
                        # Process the media info
                        self._handle_active_media(media_info)
                        break
        
        # No active player found
        if not active_found and self.active_monitor:
            if time.time() - self.last_report_time > 60:  # Only log once per minute
                logger.info(f"No active media detected in any player")
                self.last_report_time = time.time()
            self.active_monitor = None
            self._handle_no_active_media()
    
    def _handle_active_media(self, media_info):
        """Handle active media detection - to be connected to scrobbling system"""
        # Placeholder - this will be handled by the MonitorAwareScrobbler
        pass
        
    def _handle_no_active_media(self):
        """Handle the case when no media is active"""
        # Placeholder - this will be handled by the MonitorAwareScrobbler
        pass
    
    def get_current_media_info(self):
        """Get current media info from active player, if any"""
        if self.active_monitor:
            return self.active_monitor.get_playing_media()
        return None

class MonitorAwareScrobbler(MovieScrobbler):
    """
    Extended version of MovieScrobbler that works with the PlayerMonitorManager
    to track media player activity more accurately.
    """
    
    def __init__(self, client_id=None, access_token=None):
        super().__init__(client_id, access_token)
        self.monitor_manager = PlayerMonitorManager()
        self.current_player = None
        
        # Initialize time tracking attributes
        self.start_time = time.time()
        self.last_update_time = time.time() 
        self.last_progress_check = time.time()
        self.continuous_monitoring = True  # Flag to control continuous monitoring
        
    def start_monitoring(self):
        """Start monitoring players and scrobbling"""
        self.monitor_manager.start_monitoring()
        # Start a thread to check for media updates
        threading.Thread(target=self._media_update_loop, daemon=True).start()
        logger.info("Started media monitoring and scrobbling")
        
    def stop_monitoring(self):
        """Stop monitoring players"""
        self.continuous_monitoring = False
        self.monitor_manager.stop_monitoring()
        logger.info("Stopped media monitoring")
        
    def _media_update_loop(self):
        """Loop to process media updates from monitor manager"""
        while self.continuous_monitoring:
            try:
                # Get current media info from monitor manager
                media_info = self.monitor_manager.get_current_media_info()
                
                if media_info:
                    # Process the media info using our existing scrobbler
                    self._process_monitor_media(media_info)
                elif self.currently_tracking:
                    # No media playing, but we were tracking something
                    # Only stop tracking if it's been a while since we saw activity
                    if time.time() - self.last_update_time > 60:  # 1 minute timeout
                        logger.info(f"No media detected for over a minute, stopping tracking for: {self.currently_tracking}")
                        self.stop_tracking()
                
                time.sleep(MONITOR_POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in media update loop: {e}")
                time.sleep(MONITOR_POLL_INTERVAL)
    
    def _process_monitor_media(self, media_info):
        """Process media info from monitor"""
        title = media_info['title']
        state = media_info['state']
        player = media_info['player']
        
        # Update our current player info
        self.current_player = player
        
        # Check if this is a new movie
        if self.currently_tracking != title:
            self._start_new_movie(title)
        
        # Create a window info object to pass to process_window
        window_info = {
            'title': title,
            'process_name': None,  # We don't need this for processing
            'state': state
        }
        
        # Update tracking and get scrobble info
        scrobble_info = self._update_tracking(window_info)
        
        # Check if we need to mark as watched (80% threshold)
        # This handles the case when simulation doesn't have time to check completion status
        if not self.completed and self.is_complete(threshold=80) and self.simkl_id:
            logger.info(f"Monitor detected 80% completion for '{self.movie_name or title}'")
            result = self.mark_as_finished(self.simkl_id, self.movie_name or title)
            if result:
                logger.info(f"✓ Successfully marked '{self.movie_name or title}' as watched on Simkl")
                self.completed = True
        
        return scrobble_info