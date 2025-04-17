# media_tracker.py

import pygetwindow as gw
from guessit import guessit

# List of supported video player window title keywords
VIDEO_PLAYERS = [
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

def get_active_window_title():
    window = gw.getActiveWindow()
    if window:
        return window.title
    return None

def is_video_player(window_title):
    """Check if the window title belongs to a supported video player application."""
    if not window_title:
        return False
    
    # Exclude common non-media player applications
    non_players = ['Visual Studio Code', 'Chrome', 'Firefox', 'Edge', 'Explorer', 'Notepad']
    if any(app in window_title for app in non_players):
        return False
    
    # More specific checks for media players
    for player in VIDEO_PLAYERS:
        # Check for exact matches (e.g., "VLC media player")
        if player.lower() == window_title.lower():
            return True
        
        # Check for player name at the beginning of the title (most common pattern)
        if window_title.lower().startswith(player.lower()):
            return True
        
        # Check for player name with common separators
        for separator in [' - ', ': ', ' | ']:
            pattern = separator + player.lower()
            if pattern in window_title.lower():
                return True
            pattern = player.lower() + separator
            if pattern in window_title.lower():
                return True
    
    # More lenient fallback check
    return any(player.lower() in window_title.lower() for player in VIDEO_PLAYERS)

def is_movie(window_title):
    """Determine if the media is a movie and not anime, series or TV show using guessit's detection."""
    guess = guessit(window_title)
    
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
    
    # Check for anime indicators
    if 'anime' in window_title.lower():
        return False
    
    # If we've gotten here and there's a title, it's likely a movie
    if guess.get('title'):
        return True
    
    return False

def parse_movie_title(window_title):
    """Parse the movie title from the window title if it's from a video player and is a movie."""
    if not is_video_player(window_title):
        return None
    
    # Check if it's a movie and not anime/series/tv show
    if not is_movie(window_title):
        return None
    
    guess = guessit(window_title)
    return guess.get('title')