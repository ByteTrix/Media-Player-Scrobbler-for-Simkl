"""
Platform-specific window detection for Media Player Scrobbler for SIMKL.
Provides utility functions for detecting windows and media players across platforms.
"""

import os
import platform
import logging
import re
from datetime import datetime

PLATFORM = platform.system().lower()

# Platform-specific imports
if PLATFORM == 'windows':
    import pygetwindow as gw
    try:
        import win32gui
        import win32process
        import psutil
        from guessit import guessit
    except ImportError as e:
        logging.warning(f"Windows-specific module import error: {e}")
elif PLATFORM == 'darwin':  # macOS
    import subprocess
    import psutil
    from guessit import guessit
    try:
        import pygetwindow as gw
    except ImportError:
        gw = None
elif PLATFORM == 'linux':
    import subprocess
    import psutil
    from guessit import guessit
    try:
        x11_available = os.environ.get('DISPLAY') is not None
    except:
        x11_available = False
    
    if x11_available:
        try:
            import Xlib.display # type: ignore
        except ImportError:
            pass
else:
    try:
        import psutil
        from guessit import guessit
    except ImportError:
        pass

logger = logging.getLogger(__name__)

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
        'mpvnet.exe',  
        'mpc-qt.exe', 
        'syncplay.exe',  
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
        # MPV Wrapper Players for macOS
        'io.iina.IINA',  # IINA - alternative process name
        'smplayer',  # SMPlayer
        'syncplay',  # Syncplay
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
        # MPV Wrapper Players for Linux
        'haruna',  # Haruna Player
        'mpc-qt',  # Media Player Classic Qute Theater
        'mpv.net',  # MPV.net
        'syncplay',  # Syncplay
    ]
}

CURRENT_PLATFORM_PLAYERS = VIDEO_PLAYER_EXECUTABLES.get(PLATFORM, [])

# Removed unused VIDEO_PLAYER_KEYWORDS list.
# Player detection relies on VIDEO_PLAYER_EXECUTABLES.

def get_process_name_from_hwnd(hwnd):
    """Get the process name from a window handle - Windows-specific function."""
    if PLATFORM != 'windows':
        logger.error("get_process_name_from_hwnd is only supported on Windows")
        return None
    
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return process.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, win32process.error) as e:
        logger.debug(f"Error getting process name for HWND {hwnd}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting process name: {e}")
    return None

def get_active_window_info():
    """Get information about the currently active window in a platform-compatible way."""
    if PLATFORM == 'windows':
        return _get_active_window_info_windows()
    elif PLATFORM == 'darwin':
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
            parts = result.stdout.strip().split(', ', 2)
            if len(parts) >= 2:
                app_name = parts[0].strip()
                window_title = parts[1].strip()
                process_name = app_name
                
                return {
                    'title': window_title,
                    'process_name': process_name,
                    'app_name': app_name
                }
    except Exception as e:
        logger.error(f"Error getting macOS active window info: {e}")
    return None

def _get_active_window_info_linux():
    """Linux-specific implementation to get active window info."""
    try:
        # Method 1: Using xdotool (most reliable)
        try:
            window_id = subprocess.check_output(['xdotool', 'getactivewindow'], text=True, stderr=subprocess.PIPE).strip()
            window_name = subprocess.check_output(['xdotool', 'getwindowname', window_id], text=True, stderr=subprocess.PIPE).strip()
            window_pid = subprocess.check_output(['xdotool', 'getwindowpid', window_id], text=True, stderr=subprocess.PIPE).strip()
            
            process = psutil.Process(int(window_pid))
            process_name = process.name()
            
            return {
                'title': window_name,
                'process_name': process_name,
                'pid': window_pid
            }
        except (subprocess.SubprocessError, subprocess.CalledProcessError, FileNotFoundError) as e:
            error_output = str(e.stderr) if hasattr(e, 'stderr') and e.stderr else str(e)
            if "Cannot get client list properties" in error_output:
                logger.debug("xdotool cannot get client list - possibly running in WSL or without proper X server")
            else:
                logger.debug(f"xdotool method failed: {e}")
        
        # Method 2: Using wmctrl
        try:
            wmctrl_output = subprocess.check_output(['wmctrl', '-a', ':ACTIVE:', '-v'], text=True, stderr=subprocess.PIPE)
            for line in wmctrl_output.split('\n'):
                if "Using window" in line and "0x" in line:
                    window_id = line.split()[-1]
                    
                    # Get window title
                    output = subprocess.check_output(['wmctrl', '-l'], text=True)
                    for window_line in output.splitlines():
                        if window_id in window_line:
                            parts = window_line.split(None, 3)
                            if len(parts) >= 4:
                                window_title = parts[3]
                                
                                # Get window PID
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
        except (subprocess.SubprocessError, subprocess.CalledProcessError, FileNotFoundError) as e:
            error_output = str(e.stderr) if hasattr(e, 'stderr') and e.stderr else str(e)
            logger.debug(f"wmctrl method failed: {e}")
        
        # Method 3: If running under Wayland or WSL, try to detect using ps
        if os.environ.get('WAYLAND_DISPLAY') or 'WSL' in os.uname().release:
            logger.debug("Wayland or WSL detected, using process-based detection")
            
            # Find running media players
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    if any(player.lower() in proc_name.lower() for player in VIDEO_PLAYER_EXECUTABLES['linux']):
                        # Try to get the media file name from command line
                        cmdline = proc.info.get('cmdline', [])
                        title = f"Unknown - {proc_name}"
                        
                        # Check if any command line arg is a media file
                        for arg in reversed(cmdline):
                            if arg and os.path.isfile(arg) and '.' in arg:
                                title = os.path.basename(arg)
                                break
                        
                        return {
                            'title': title,
                            'process_name': proc_name,
                            'pid': proc.pid
                        }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    except Exception as e:
        logger.warning(f"Error getting Linux active window info: {e}")
    
    return None

def get_all_windows_info():
    """Get information about all open windows in a platform-compatible way."""
    if PLATFORM == 'windows':
        return _get_all_windows_info_windows()
    elif PLATFORM == 'darwin':
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
            output = result.stdout.strip()
            pairs = re.findall(r'\{\"(.*?)\", \"(.*?)\"\}', output)
            
            for app_name, window_title in pairs:
                windows_info.append({
                    'title': window_title,
                    'process_name': app_name,
                    'app_name': app_name
                })
    except Exception as e:
        logger.error(f"Error getting all macOS windows info: {e}")
        
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
    
    # Standard Linux detection using window management tools
    try:
        # First try using wmctrl which is more reliable
        try:
            output = subprocess.check_output(['wmctrl', '-l', '-p'], text=True, stderr=subprocess.PIPE)
            for line in output.strip().split('\n'):
                if line.strip():
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        window_id = parts[0]
                        desktop = parts[1]
                        pid = parts[2]
                        host = parts[3]
                        window_title = parts[4]
                        
                        try:
                            process = psutil.Process(int(pid))
                            process_name = process.name()
                            
                            # Skip generic titles from media players
                            if process_name in VIDEO_PLAYER_EXECUTABLES['linux'] and window_title.lower() in ["audio", "video", "media"]:
                                # Try to get the actual file being played from commandline
                                cmdline = process.cmdline()
                                if cmdline and len(cmdline) > 1:
                                    for arg in reversed(cmdline):
                                        if arg and os.path.isfile(arg) and '.' in arg:
                                            # Replace the generic title with the actual filename
                                            window_title = os.path.basename(arg)
                                            logger.debug(f"Replaced generic '{window_title}' with filename: {window_title}")
                                            break
                            
                            windows_info.append({
                                'title': window_title,
                                'process_name': process_name,
                                'pid': pid
                            })
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            windows_info.append({
                                'title': window_title,
                                'process_name': 'unknown',
                                'pid': pid
                            })
                            
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"wmctrl not available for window listing: {e}")
        
        # If wmctrl failed or didn't find any windows, try using process detection
        if not windows_info:
            logger.debug("Using process-based window detection (fallback)")
            
            # Detect all running media player processes
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    proc_name = proc.info['name']
                    cmdline = proc.info.get('cmdline', [])
                    
                    if any(player.lower() in proc_name.lower() for player in VIDEO_PLAYER_EXECUTABLES['linux']):
                        title = "Unknown"
                        if cmdline and len(cmdline) > 1:
                            # Look for media files in the command line arguments
                            for arg in reversed(cmdline):
                                if arg and os.path.isfile(arg) and '.' in arg:
                                    # Use the filename as the title
                                    title = os.path.basename(arg)
                                    logger.debug(f"Found movie filename in cmdline: {title}")
                                    break
                        
                        windows_info.append({
                            'title': title,
                            'process_name': proc_name,
                            'pid': proc.pid
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    except Exception as e:
        logger.warning(f"Error getting Linux windows info: {e}")
        logger.info("Falling back to media player process detection")
        
        # Last resort - just look for media player processes
        try:
            for player_name in VIDEO_PLAYER_EXECUTABLES['linux']:
                for proc in psutil.process_iter(['name', 'cmdline']):
                    try:
                        proc_name = proc.info['name']
                        if player_name.lower() in proc_name.lower():
                            # Try to get the actual media file from cmdline
                            title = f"Media Player: {proc_name}"
                            cmdline = proc.info.get('cmdline', [])
                            
                            if cmdline and len(cmdline) > 1:
                                for arg in reversed(cmdline):
                                    if arg and os.path.isfile(arg) and '.' in os.path.basename(arg):
                                        ext = os.path.splitext(arg)[1].lower()
                                        # Common video file extensions
                                        if ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg']:
                                            title = os.path.basename(arg)
                                            break
                            
                            windows_info.append({
                                'title': title,
                                'process_name': proc_name,
                                'pid': proc.pid
                            })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        except Exception as e:
            logger.error(f"Process-based fallback also failed: {e}")
    
    return windows_info

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
    
    platform_players = VIDEO_PLAYER_EXECUTABLES.get(PLATFORM, [])
    
    if any(player.lower() in process_name for player in platform_players):
        return True
    
    if PLATFORM == 'darwin' and app_name:
        if any(player.lower() in app_name for player in platform_players):
            return True
            
    return False

def get_media_type(window_title_or_path):
    """
    Determine the type of media (movie, episode, anime) using guessit.
    This is a replacement for is_movie() that handles all media types.

    Args:
        window_title_or_path (str): The window title or file path to analyze

    Returns:
        str: Media type ('movie', 'episode', or 'unknown')
    """
    if not window_title_or_path:
        return 'unknown'

    # Skip titles that are just "Audio" or similar generic names
    if window_title_or_path.lower() in ["audio", "video", "media", "no file"]:
        logger.debug(f"Ignoring generic media title: '{window_title_or_path}'")
        return 'unknown'

    try:
        guess = guessit(window_title_or_path)
        media_type = guess.get('type')

        if media_type == 'movie':
            logger.debug(f"Guessit identified '{window_title_or_path}' as movie")
            return 'movie'
        elif media_type == 'episode':
            # Check for anime-specific indicators
            if 'anime' in guess or (
                guess.get('episode_title') and 
                any(word in window_title_or_path.lower() for word in ['anime', 'sub', 'dub', 'jpn'])
            ):
                logger.debug(f"Guessit identified '{window_title_or_path}' as anime")
                return 'anime'
            else:
                logger.debug(f"Guessit identified '{window_title_or_path}' as TV episode")
                return 'episode'
        else:
            logger.debug(f"Guessit couldn't determine media type for '{window_title_or_path}'")
    except Exception as e:
        logger.error(f"Error using guessit on '{window_title_or_path}': {e}")

    return 'unknown'

def is_movie(window_title):
    """
    Legacy method that determines if the media is likely a movie using guessit.
    Now delegates to get_media_type for more accurate detection.
    """
    media_type = get_media_type(window_title)
    return media_type == 'movie'

def parse_media_title(window_title_or_info):
    """
    Extract a clean media title from the window title or info dictionary.
    Works for movies, TV shows and anime - replaces parse_movie_title.

    Args:
        window_title_or_info (str or dict): The window title string or info dict.

    Returns:
        dict: Dictionary with 'title', 'type', 'season', 'episode' and other metadata
              or None if parsing fails.
    """
    if isinstance(window_title_or_info, dict):
        window_title = window_title_or_info.get('title', '')
        process_name = window_title_or_info.get('process_name', '').lower()
        if process_name and not any(player in process_name for player in CURRENT_PLATFORM_PLAYERS):
            return None
    elif isinstance(window_title_or_info, str):
        window_title = window_title_or_info
    else:
        return None

    if not window_title:
        return None

    # Filter out non-media titles
    non_video_patterns = [
        r'\.txt\b',
        r'\.doc\b',
        r'\.pdf\b',
        r'\.xls\b',
        r'Notepad',
        r'Document',
        r'Microsoft Word',
        r'Microsoft Excel',
    ]
    
    for pattern in non_video_patterns:
        if re.search(pattern, window_title, re.IGNORECASE):
            return None
            
    # Filter out player-only titles without media info
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
        # MPV Wrapper player-only window titles
        r'^mpv\.net$',
        r'^Celluloid$',
        r'^IINA$',
        r'^Haruna$',
        r'^Syncplay.*$',
        r'^MPC-QT$',
    ]
    
    for pattern in player_only_patterns:
        if re.search(pattern, window_title, re.IGNORECASE):
            logger.debug(f"Ignoring player-only window title: '{window_title}'")
            return None

    # Clean up the title by removing player specific information
    cleaned_title = window_title

    player_patterns = [
        r'\s*-\s*VLC media player$',
        r'\s*-\s*MPC-HC.*$',
        r'\s*-\s*MPC-BE.*$',
        r'\s*-\s*Windows Media Player$',
        r'\s*-\s*mpv$',
        r'\s+\[.*PotPlayer.*\]$',
        r'\s*-\s*SMPlayer.*$',
        r'\s*-\s*KMPlayer.*$',
        r'\s*-\s*GOM Player.*$',
        r'\s*-\s*Media Player Classic.*$',
        # MPV Wrapper Players patterns
        r'\s*-\s*MPV\.net$',
        r'\s*-\s*Celluloid$',
        r'\s*-\s*IINA$',
        r'\s*-\s*Haruna$',
        r'\s*-\s*Syncplay.*$',
        r'\s*-\s*MPC-QT$',
        # Pause indicators
        r'\s*\[Paused\]$',
        r'\s*-\s*Paused$',
    ]
    for pattern in player_patterns:
        cleaned_title = re.sub(pattern, '', cleaned_title, flags=re.IGNORECASE).strip()

    # --- Pre-process title for separators and release info ---
    title_to_guess = cleaned_title
    separators = ['|', ' - ']
    release_info_pattern = re.compile(
        r'\b(psarips|rarbg|yts|yify|evo|mkvcage|\[.*?\]|\(.*?\)|(www\.)?\w+\.(com|org|net|info))\b',
        re.IGNORECASE
    )
    processed_split = False

    for sep in separators:
        if sep in cleaned_title:
            processed_split = True
            parts = [p.strip() for p in cleaned_title.split(sep) if p.strip()]
            
            # Filter out parts that look like release info
            potential_title_parts = []
            for part in parts:
                 if not release_info_pattern.search(part):
                      potential_title_parts.append(part)
                 else:
                      logger.debug(f"Part '{part}' identified as release info, filtering out.")
            
            # If exactly one part remains after filtering, assume it's the title
            if len(potential_title_parts) == 1:
                title_to_guess = potential_title_parts[0]
                logger.debug(f"Split by '{sep}', filtered release info, using single remaining part: '{title_to_guess}'")
                break # Use this part and stop processing separators
            else:
                # If 0 or >1 parts remain, the split is ambiguous or filtered everything.
                # Fall back to the original cleaned title before splitting.
                logger.debug(f"Split by '{sep}', but {len(potential_title_parts)} parts remain after filtering. Falling back to pre-split title: '{cleaned_title}'")
                title_to_guess = cleaned_title
                break # Stop processing separators after first ambiguous split

    # If no separator was found, title_to_guess remains the original cleaned_title

    # --- End Pre-processing ---

    if len(title_to_guess) < 3:
        logger.debug(f"Title too short after cleanup: '{title_to_guess}' from '{window_title}'")
        return None

    try:
        # Use guessit for final parsing and media type identification
        guess = guessit(title_to_guess)
        
        result = {
            'raw_title': window_title,
            'cleaned_title': cleaned_title,
        }

        # Add detected media type
        if 'type' in guess:
            result['type'] = guess['type']
        else:
            result['type'] = 'unknown'

        # Add main title
        if 'title' in guess:
            result['title'] = guess['title']
        else:
            result['title'] = cleaned_title.strip()

        # Add year if available
        if 'year' in guess:
            result['year'] = guess['year']

        # Add TV show specific information
        if guess.get('type') == 'episode':
            if 'season' in guess:
                result['season'] = guess['season']
            if 'episode' in guess:
                result['episode'] = guess['episode']
            if 'episode_title' in guess:
                result['episode_title'] = guess['episode_title']

        # Format display title for human-readable output
        display_title = result['title']
        if 'year' in result and isinstance(result['year'], int):
            display_title += f" ({result['year']})"
        result['display_title'] = display_title

        # Add formatted episode info for display
        if guess.get('type') == 'episode' and 'season' in guess and 'episode' in guess:
            result['formatted_episode'] = f"S{guess['season']:02d}E{guess['episode']:02d}"
            result['display_title'] += f" {result['formatted_episode']}"

        logger.debug(f"Parsed media: {result}")
        return result

    except Exception as e:
        logger.error(f"Error parsing media title '{cleaned_title}': {e}")
        # Return basic info in case of error
        return {
            'raw_title': window_title,
            'title': cleaned_title.strip(),
            'display_title': cleaned_title.strip(),
            'type': 'unknown'
        }

def parse_movie_title(window_title_or_info):
    """
    Legacy function kept for backward compatibility.
    Delegates to parse_media_title but returns just the title string.
    """
    media_info = parse_media_title(window_title_or_info)
    if media_info:
        return media_info.get('display_title')
    return None

def parse_filename_from_path(filepath):
    """
    Extract and parse media information from a file path.
    Uses the filename portion (without extension) as input to guessit.
    
    Args:
        filepath (str): Full file path from player API
        
    Returns:
        str: Cleaned media title or None if parsing fails
    """
    if not filepath:
        return None
        
    try:
        # Extract just the filename from the path
        filename = os.path.basename(filepath)
        logger.debug(f"Extracted filename: '{filename}' from path: '{filepath}'")
        
        # Skip non-video files
        common_video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', 
                                  '.webm', '.m4v', '.mpg', '.mpeg', '.ts', '.vob']
        file_ext = os.path.splitext(filename.lower())[1]
        
        if file_ext and file_ext not in common_video_extensions:
            logger.debug(f"Skipping non-video file extension: {file_ext}")
            return None
            
        # Use parse_media_title to get all media information
        media_info = parse_media_title(filename)
        
        if media_info:
            # Return the display title which includes year and episode if present
            return media_info['display_title']
        
    except Exception as e:
        logger.error(f"Error parsing filename '{filepath}': {e}")
    
    return None

def get_file_metadata(file_path):
    """
    Extract metadata from a media file including file size, resolution, and other properties.
    
    Args:
        file_path (str): Path to the media file
        
    Returns:
        dict: Dictionary containing file metadata
    """
    metadata = {}
    
    if not file_path or not os.path.exists(file_path):
        return metadata
        
    try:
        # Get file size
        file_stat = os.stat(file_path)
        file_size = file_stat.st_size
        metadata["file_size"] = file_size
        metadata["formatted_file_size"] = format_file_size(file_size)
        
        # Extract file name and use guessit to determine resolution
        filename = os.path.basename(file_path)
        guess = guessit(filename)
        
        # Get resolution from guessit
        if 'screen_size' in guess:
            resolution = str(guess['screen_size'])
            
            # Map common resolutions to more descriptive formats
            resolution_map = {
                '4K': '4K (2160p)',
                '2160p': '4K (2160p)',
                '1080p': 'Full HD (1080p)',
                '720p': 'HD (720p)',
                '480p': 'SD (480p)',
                '540p': 'qHD (540p)'
            }
            
            metadata["resolution"] = resolution_map.get(resolution, resolution)
        else:
            # Fallback to filename pattern matching if guessit didn't find resolution
            filename_lower = filename.lower()
            if "2160p" in filename_lower or "4k" in filename_lower or "uhd" in filename_lower:
                metadata["resolution"] = "4K (2160p)"
            elif "1080p" in filename_lower or "fullhd" in filename_lower or "fhd" in filename_lower:
                metadata["resolution"] = "Full HD (1080p)"
            elif "720p" in filename_lower or "hd" in filename_lower:
                metadata["resolution"] = "HD (720p)"
            elif "480p" in filename_lower or "sd" in filename_lower:
                metadata["resolution"] = "SD (480p)"
            elif "540p" in filename_lower:
                metadata["resolution"] = "qHD (540p)"
            else:
                metadata["resolution"] = "Unknown"
        
        # Get file extension
        _, file_ext = os.path.splitext(file_path)
        if file_ext:
            metadata["file_format"] = file_ext.lstrip('.').upper()
        
        # Get parent directory name
        parent_dir = os.path.basename(os.path.dirname(file_path))
        if parent_dir:
            metadata["folder"] = parent_dir
            
        # Get file creation and modification time
        metadata["created_at"] = datetime.fromtimestamp(file_stat.st_ctime).isoformat()
        metadata["modified_at"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
    except Exception as e:
        logger.error(f"Error getting file metadata for {file_path}: {e}")
        
    return metadata

def format_file_size(size_bytes):
    """
    Format file size to human-readable format
    
    Args:
        size_bytes (int): Size in bytes
        
    Returns:
        str: Formatted size string (e.g., "3.45 GB")
    """
    if size_bytes is None:
        return "Unknown"
        
    # Define units and thresholds
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    if size_bytes == 0:
        return "0 B"
        
    # Calculate the appropriate unit
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024
        i += 1
        
    # Format with 2 decimal places if not bytes
    if i == 0:
        return f"{int(size_bytes)} {units[i]}"
    else:
        return f"{size_bytes:.2f} {units[i]}"