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
            elapsed = current_time - self.last_update_time
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
        
        if not self.client_id or not self.access_token:
            logger.error("Cannot mark movie as finished: missing API credentials")
            self.backlog.add(simkl_id, title)
            return False
            
        try:
            result = mark_as_watched(simkl_id, self.client_id, self.access_token)
            if result:
                logger.info(f"Successfully marked '{title}' as watched on Simkl")
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
        
    def cache_movie_info(self, title, simkl_id, movie_name):
        """Cache movie info to avoid repeated searches"""
        if title and simkl_id:
            self.media_cache.set(title, {
                "simkl_id": simkl_id,
                "movie_name": movie_name
            })
            
            # If this is the movie we're currently tracking, update our local copy
            if self.currently_tracking == title:
                self.simkl_id = simkl_id
                self.movie_name = movie_name
                
    def is_complete(self, threshold=80):
        """Check if the movie is considered watched (default: 80% threshold)"""
        if not self.currently_tracking:
            return False
            
        watched_minutes = self.watch_time / 60
        percentage = min(100, (watched_minutes / self.estimated_duration) * 100)
        
        return percentage >= threshold
        
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