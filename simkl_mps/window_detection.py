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
            import Xlib.display
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

def is_movie(window_title):
    """Determine if the media is likely a movie using guessit."""
    if not window_title:
        return False

    # Skip titles that are just "Audio" or similar generic names
    if window_title.lower() in ["audio", "video", "media", "no file"]:
        logger.debug(f"Ignoring generic media title: '{window_title}'")
        return False

    try:
        guess = guessit(window_title)
        media_type = guess.get('type')

        if media_type == 'movie':
            if 'episode' not in guess and 'season' not in guess:
                 return True
            else:
                 logger.debug(f"Guessit identified as movie but found episode/season: {guess}")
                 return False
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
        if process_name and not any(player in process_name for player in CURRENT_PLATFORM_PLAYERS):
            return None
    elif isinstance(window_title_or_info, str):
        window_title = window_title_or_info
    else:
        return None

    if not window_title:
        return None

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

    if not is_movie(window_title):
         return None

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
        # Final guessit call on the chosen title string
        guess = guessit(title_to_guess)
        if 'title' in guess:
             if len(guess['title']) > 2:
                  if 'year' in guess:
                       if isinstance(guess['year'], int) and 1880 < guess['year'] < datetime.now().year + 2:
                            return f"{guess['title']} ({guess['year']})"
                       else:
                            return guess['title']
                  else:
                       return guess['title']
             else:
                  logger.debug(f"Guessit title '{guess['title']}' too short, using cleaned title.")
        return cleaned_title.strip()

    except Exception as e:
         logger.error(f"Error using guessit for title parsing '{cleaned_title}': {e}")
         return cleaned_title.strip()