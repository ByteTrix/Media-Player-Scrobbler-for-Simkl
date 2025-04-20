"""
Platform-specific window detection for SIMKL Scrobbler.
Provides utility functions for detecting windows and media players across platforms.
"""

import os
import platform
import logging
import re
from datetime import datetime

# Platform-specific imports
PLATFORM = platform.system().lower()

if PLATFORM == 'windows':
    import pygetwindow as gw
    import win32gui
    import win32process
    import psutil
    from guessit import guessit
elif PLATFORM == 'darwin':  # macOS
    import subprocess
    import psutil
    from guessit import guessit
    # Optional: import pygetwindow if available for macOS
    try:
        import pygetwindow as gw
    except ImportError:
        gw = None
elif PLATFORM == 'linux':
    import subprocess
    import psutil
    from guessit import guessit
    # For Linux, we'll use different approaches depending on desktop environment
    try:
        # Check if we're in X11 environment
        x11_available = os.environ.get('DISPLAY') is not None
    except:
        x11_available = False
    
    if x11_available:
        try:
            # Try importing xlib/xprop related tools if available
            import Xlib.display
        except ImportError:
            pass
else:
    # Import what's available for other platforms
    try:
        import psutil
        from guessit import guessit
    except ImportError:
        pass

# Configure module logging
logger = logging.getLogger(__name__)

# List of supported video player executables by platform
VIDEO_PLAYER_EXECUTABLES = {
    'windows': [
        'vlc.exe',
        'mpc-hc.exe',
        'mpc-hc64.exe',
        'mpc-be.exe',
        'mpc-be64.exe',
        'wmplayer.exe',
        'mpv.exe',
        'PotPlayerMini.exe',
        'PotPlayerMini64.exe',
        'smplayer.exe',
        'kmplayer.exe',
        'GOM.exe',
        'MediaPlayerClassic.exe',
    ],
    'darwin': [  # macOS
        'VLC',
        'mpv',
        'IINA',
        'QuickTime Player',
        'Elmedia Player',
        'Movist',
        'Movist Pro',
        'MPEG Streamclip',
    ],
    'linux': [
        'vlc',
        'mpv',
        'smplayer',
        'totem',
        'xplayer',
        'dragon',
        'parole',
        'kaffeine',
        'celluloid',
    ]
}

# Default to the current platform's player list
CURRENT_PLATFORM_PLAYERS = VIDEO_PLAYER_EXECUTABLES.get(PLATFORM, [])

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
    'Media Player Classic',
    'IINA',
    'QuickTime Player',
    'Elmedia Player',
    'Movist',
    'Totem',
    'Celluloid',
]

def get_process_name_from_hwnd(hwnd):
    """Get the process name from a window handle - Windows-specific function."""
    if PLATFORM != 'windows':
        logger.error("get_process_name_from_hwnd is only supported on Windows")
        return None
    
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

# Platform-specific window detection implementations
def get_active_window_info():
    """Get information about the currently active window in a platform-compatible way."""
    if PLATFORM == 'windows':
        return _get_active_window_info_windows()
    elif PLATFORM == 'darwin':  # macOS
        return _get_active_window_info_macos()
    elif PLATFORM == 'linux':
        return _get_active_window_info_linux()
    else:
        logger.warning(f"Unsupported platform: {PLATFORM}")
        return None

def _get_active_window_info_windows():
    """Windows-specific implementation to get active window info."""
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
        logger.error(f"Error getting Windows active window info: {e}")
    return None

def _get_active_window_info_macos():
    """macOS-specific implementation to get active window info."""
    try:
        # AppleScript to get the active window information
        script = '''
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
            set frontAppPath to path of first application process whose frontmost is true
            
            set windowTitle to ""
            try
                tell process frontApp
                    if exists (1st window whose value of attribute "AXMain" is true) then
                        set windowTitle to name of 1st window whose value of attribute "AXMain" is true
                    end if
                end tell
            end try
            
            return {frontApp, windowTitle, frontAppPath}
        end tell
        '''
        
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # Parse the result - format will be something like: "VLC, My Movie.mp4, /Applications/VLC.app"
            parts = result.stdout.strip().split(', ', 2)
            if len(parts) >= 2:
                app_name = parts[0].strip()
                window_title = parts[1].strip()
                
                # Get just the executable name from the app name
                process_name = app_name
                
                return {
                    'title': window_title,
                    'process_name': process_name,
                    'app_name': app_name  # Store full app name for macOS
                }
    except Exception as e:
        logger.error(f"Error getting macOS active window info: {e}")
    return None

def _get_active_window_info_linux():
    """Linux-specific implementation to get active window info."""
    try:
        # Try various approaches depending on which tools are available
        
        # First try using xdotool if available (works on X11)
        try:
            # Get window ID
            window_id = subprocess.check_output(['xdotool', 'getactivewindow'], text=True).strip()
            # Get window name/title
            window_name = subprocess.check_output(['xdotool', 'getwindowname', window_id], text=True).strip()
            # Get window PID
            window_pid = subprocess.check_output(['xdotool', 'getwindowpid', window_id], text=True).strip()
            
            # Get process name from PID
            process = psutil.Process(int(window_pid))
            process_name = process.name()
            
            return {
                'title': window_name,
                'process_name': process_name,
                'pid': window_pid
            }
        except (subprocess.SubprocessError, FileNotFoundError):
            # xdotool not available or failed
            pass
        
        # Try using wmctrl as alternative
        try:
            active_window = subprocess.check_output(['wmctrl', '-a', ':ACTIVE:'], text=True).strip()
            for line in active_window.split('\n'):
                if line.strip():
                    parts = line.split(None, 1)
                    if len(parts) > 1:
                        window_id = parts[0]
                        window_title = parts[1]
                        
                        # Try to get PID using xprop 
                        try:
                            xprop_output = subprocess.check_output(['xprop', '-id', window_id, '_NET_WM_PID'], text=True)
                            pid_match = re.search(r'_NET_WM_PID\(CARDINAL\) = (\d+)', xprop_output)
                            if pid_match:
                                pid = int(pid_match.group(1))
                                process = psutil.Process(pid)
                                process_name = process.name()
                                
                                return {
                                    'title': window_title,
                                    'process_name': process_name,
                                    'pid': pid
                                }
                        except:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            # wmctrl not available or failed
            pass
            
        # For Wayland
        if os.environ.get('WAYLAND_DISPLAY'):
            logger.debug("Wayland detected, window detection might be limited")
            
            # Try to at least get running processes that might be video players
            for proc in psutil.process_iter(['name']):
                try:
                    proc_name = proc.info['name']
                    if any(player.lower() in proc_name.lower() for player in VIDEO_PLAYER_EXECUTABLES['linux']):
                        # For Wayland, we might not get the window title reliably
                        # but at least we can detect if a known player is running
                        return {
                            'title': f"Unknown title - {proc_name}",
                            'process_name': proc_name,
                            'pid': proc.pid
                        }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    except Exception as e:
        logger.error(f"Error getting Linux active window info: {e}")
    
    return None

def get_all_windows_info():
    """Get information about all open windows in a platform-compatible way."""
    if PLATFORM == 'windows':
        return _get_all_windows_info_windows()
    elif PLATFORM == 'darwin':  # macOS
        return _get_all_windows_info_macos()
    elif PLATFORM == 'linux':
        return _get_all_windows_info_linux()
    else:
        logger.warning(f"Unsupported platform: {PLATFORM}")
        return []

def _get_all_windows_info_windows():
    """Windows-specific implementation to get all windows info."""
    windows_info = []
    try:
        all_windows = gw.getAllWindows()
        for window in all_windows:
            if window.visible and window.title:
                try:
                    hwnd = window._hWnd
                    process_name = get_process_name_from_hwnd(hwnd)
                    if process_name and window.title:
                        windows_info.append({
                            'hwnd': hwnd,
                            'title': window.title,
                            'process_name': process_name
                        })
                except Exception as e:
                    logger.debug(f"Error processing window: {e}")
    except Exception as e:
        logger.error(f"Error getting all Windows windows info: {e}")
    return windows_info

def _get_all_windows_info_macos():
    """macOS-specific implementation to get all windows info."""
    windows_info = []
    try:
        # AppleScript to get all windows from all applications
        script = '''
        set windowList to {}
        tell application "System Events"
            set allProcesses to application processes where background only is false
            repeat with oneProcess in allProcesses
                set appName to name of oneProcess
                tell process appName
                    set appWindows to windows
                    repeat with windowObj in appWindows
                        set windowTitle to ""
                        try
                            set windowTitle to name of windowObj
                        end try
                        if windowTitle is not "" then
                            set end of windowList to {appName, windowTitle}
                        end if
                    end repeat
                end tell
            end repeat
        end tell
        return windowList
        '''
        
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # Parse the result
            # Format will be a list of app/window pairs
            output = result.stdout.strip()
            # Simple parsing - this could be improved with proper parsing of AppleScript output
            pairs = re.findall(r'\{\"(.*?)\", \"(.*?)\"\}', output)
            
            for app_name, window_title in pairs:
                windows_info.append({
                    'title': window_title,
                    'process_name': app_name,
                    'app_name': app_name
                })
    except Exception as e:
        logger.error(f"Error getting all macOS windows info: {e}")
        
        # Fallback: check for running video player processes
        try:
            for player in VIDEO_PLAYER_EXECUTABLES['darwin']:
                player_lower = player.lower()
                for proc in psutil.process_iter(['name']):
                    try:
                        proc_name = proc.info['name'].lower()
                        if player_lower in proc_name:
                            windows_info.append({
                                'title': f"Unknown - {proc_name}",
                                'process_name': proc.info['name'],
                                'pid': proc.pid
                            })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        except Exception as e:
            logger.error(f"Error with macOS fallback window detection: {e}")
            
    return windows_info

def _get_all_windows_info_linux():
    """Linux-specific implementation to get all windows info."""
    windows_info = []
    try:
        # Try using wmctrl to list all windows (X11)
        try:
            output = subprocess.check_output(['wmctrl', '-l', '-p'], text=True)
            for line in output.strip().split('\n'):
                if line.strip():
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        window_id = parts[0]
                        desktop = parts[1]
                        pid = parts[2]
                        host = parts[3]
                        window_title = parts[4]
                        
                        # Get process name from PID
                        try:
                            process = psutil.Process(int(pid))
                            process_name = process.name()
                            
                            windows_info.append({
                                'title': window_title,
                                'process_name': process_name,
                                'pid': pid
                            })
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Can't get process name, still add with unknown
                            windows_info.append({
                                'title': window_title,
                                'process_name': 'unknown',
                                'pid': pid
                            })
                            
        except (subprocess.SubprocessError, FileNotFoundError):
            # wmctrl not available or failed
            logger.debug("wmctrl not available for window listing")
        
        # If no windows found or wmctrl failed, fall back to checking running processes
        if not windows_info:
            logger.debug("Using fallback process-based window detection")
            
            # Check for video player processes
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    cmdline = proc.info.get('cmdline', [])
                    
                    # Check if this is likely a video player
                    if any(player.lower() in proc_name.lower() for player in VIDEO_PLAYER_EXECUTABLES['linux']):
                        # Try to extract a title from cmdline (often contains the file being played)
                        title = "Unknown"
                        if cmdline and len(cmdline) > 1:
                            # Last argument might be the file
                            possible_file = cmdline[-1]
                            if os.path.isfile(possible_file) and '.' in possible_file:
                                # Likely a media file
                                title = os.path.basename(possible_file)
                        
                        windows_info.append({
                            'title': title,
                            'process_name': proc_name,
                            'pid': proc.pid
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    except Exception as e:
        logger.error(f"Error getting all Linux windows info: {e}")
    
    return windows_info

# --- Functions related to identifying active media ---

def get_active_window_title():
    """Get the title of the currently active window."""
    info = get_active_window_info()
    return info['title'] if info else None

def is_video_player(window_info):
    """
    Check if the window information corresponds to a known video player.
    Works cross-platform by checking against the appropriate player list.

    Args:
        window_info (dict): Dictionary containing 'process_name' and 'title'.

    Returns:
        bool: True if it's a known video player, False otherwise.
    """
    if not window_info:
        return False

    process_name = window_info.get('process_name', '').lower()
    app_name = window_info.get('app_name', '').lower()  # For macOS
    title = window_info.get('title', '').lower()
    
    # Get the platform-specific player list
    platform_players = VIDEO_PLAYER_EXECUTABLES.get(PLATFORM, [])
    
    # First check process name against known executables for the current platform
    if any(player.lower() in process_name for player in platform_players):
        return True
    
    # On macOS, also check the app_name 
    if PLATFORM == 'darwin' and app_name:
        if any(player.lower() in app_name for player in platform_players):
            return True
            
    # Fallback based on title keywords removed as it was causing false positives
    # for keyword in VIDEO_PLAYER_KEYWORDS:
    #     if keyword.lower() in title:
    #         return True
            
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
        process_name = window_title_or_info.get('process_name', '').lower()
        # Quick reject based on process name
        if process_name and not any(player in process_name for player in CURRENT_PLATFORM_PLAYERS):
            return None
    elif isinstance(window_title_or_info, str):
        window_title = window_title_or_info
    else:
        return None

    if not window_title:
        return None

    # Check for common non-video files
    non_video_patterns = [
        r'\.txt\b',           # Text files
        r'\.doc\b',           # Word documents
        r'\.pdf\b',           # PDF files
        r'\.xls\b',           # Excel files
        r'Notepad',           # Notepad windows
        r'Document',          # Generic document windows
        r'Microsoft Word',    # Microsoft Word windows
        r'Microsoft Excel',   # Microsoft Excel windows
    ]
    
    for pattern in non_video_patterns:
        if re.search(pattern, window_title, re.IGNORECASE):
            return None
            
    # Reject player names with no file - these are usually just the player UI with no movie loaded
    player_only_patterns = [
        r'^VLC( media player)?$',
        r'^MPC-HC$',
        r'^MPC-BE$',
        r'^Windows Media Player$',
        r'^mpv$',
        r'^PotPlayer.*$',
        r'^SMPlayer.*$',
        r'^KMPlayer.*$',
        r'^GOM Player.*$',
        r'^Media Player Classic.*$',
    ]
    
    for pattern in player_only_patterns:
        if re.search(pattern, window_title, re.IGNORECASE):
            logger.debug(f"Ignoring player-only window title: '{window_title}'")
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

    # Ensure we're not left with just a tiny title after cleanup
    if len(cleaned_title) < 3:
        logger.debug(f"Title too short after cleanup: '{cleaned_title}' from '{window_title}'")
        return None

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