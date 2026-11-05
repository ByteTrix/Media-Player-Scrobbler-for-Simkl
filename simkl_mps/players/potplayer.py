"""
PotPlayer integration module for Media Player Scrobbler for SIMKL.
Provides functionality to interact with PotPlayer using Windows messaging API.
"""

import logging
import os
import platform
import re


# Setup module logger
logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {
    '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts', '.mpg', '.mpeg'
}

# Only import Windows-specific modules on Windows
PLATFORM = platform.system().lower()
win32gui = None
win32con = None
win32process = None
psutil = None
if PLATFORM == 'windows':
    try:
        import win32gui
        import win32con
        import win32process
        import psutil
    except ImportError:
        win32gui = None
        win32con = None
        win32process = None
        psutil = None
        logger.warning("PotPlayer integration requires pywin32 and psutil on Windows")

# PotPlayer Windows Message constants (WM_USER = 0x0400)
PPM_GET_VOLUME = 0x5000
PPM_SET_VOLUME = 0x5001
PPM_GET_TOTAL_TIME_MS = 0x5002
PPM_GET_PLAYBACK_TIME_MS = 0x5004
PPM_SET_PLAYBACK_TIME_MS = 0x5005
PPM_GET_PLAYBACK_STATUS = 0x5006  # -1=stopped, 1=paused, 2=running (playing)
PPM_SET_PLAYBACK_STATUS = 0x5007  # 0=toggle, 1=pause, 2=play

def find_potplayer_hwnd():
    """Find PotPlayer window handle."""
    if not win32gui:
        return None
    try:
        hwnd = win32gui.FindWindow("PotPlayer64", None)
        if hwnd:
            return hwnd
        return win32gui.FindWindow("PotPlayer", None)
    except Exception as e:
        logger.debug(f"Error finding PotPlayer window: {e}")
        return None

def get_playback_ms(hwnd):
    """Get current playback position in milliseconds."""
    if not win32gui or not win32con:
        return None
    try:
        return win32gui.SendMessage(hwnd, win32con.WM_USER, PPM_GET_PLAYBACK_TIME_MS, 0)
    except Exception as e:
        logger.debug(f"Error getting playback position: {e}")
        return None

def get_total_ms(hwnd):
    """Get total duration in milliseconds."""
    if not win32gui or not win32con:
        return None
    try:
        return win32gui.SendMessage(hwnd, win32con.WM_USER, PPM_GET_TOTAL_TIME_MS, 0)
    except Exception:
        return None

def format_time(ms):
    """Format milliseconds into HH:MM:SS format."""
    if ms is None:
        return "00:00:00"
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}"

class PotPlayerIntegration:
    """
    Class for interacting with PotPlayer using Windows messaging API.
    Provides position and duration data for accurate scrobbling.
    """
    
    def __init__(self):
        self.name = 'potplayer'
        self.platform = platform.system().lower()
        self.last_hwnd = None
        self.last_window_title = None
        self.cached_filename = None
        self.cached_filepath = None
        self._connection_logged = False

        if self.platform == 'windows' and not all([win32gui, win32con, win32process, psutil]):
            logger.error("PotPlayer integration requires pywin32 and psutil libraries on Windows")

    def get_position_duration(self, process_name=None):
        """
        Get current playback position and duration from PotPlayer.
        
        Args:
            process_name: Optional process name for debugging
            
        Returns:
            tuple: (position, duration) in seconds, or (None, None) if unavailable
        """
        if self.platform != 'windows' or not all([win32gui, win32con]):
            return None, None
        
        hwnd = find_potplayer_hwnd()
        if not hwnd:
            self.last_hwnd = None
            self.last_window_title = None
            self.cached_filename = None
            self.cached_filepath = None
            return None, None
        
        try:
            pos_ms = get_playback_ms(hwnd)
            total_ms = get_total_ms(hwnd)
            
            if pos_ms is None or total_ms is None or total_ms <= 0:
                return None, None
            
            position = pos_ms / 1000.0
            duration = total_ms / 1000.0
            
            if position < 0:
                position = 0.0
            elif position > duration:
                position = duration
            
            self.last_hwnd = hwnd
            
            if not self._connection_logged:
                logger.info("Successfully connected to PotPlayer via Windows messaging")
                self._connection_logged = True
            
            return round(position, 2), round(duration, 2)
            
        except Exception as e:
            logger.debug(f"Error getting position/duration from PotPlayer: {e}")
            return None, None

    def is_paused(self):
        """
        Check if PotPlayer playback is paused.
        
        Returns:
            bool: True if paused, False if playing, None if unknown
        """
        if self.platform != 'windows' or not win32gui or not win32con:
            return None
            
        hwnd = find_potplayer_hwnd()
        if not hwnd:
            return None
            
        try:
            state = win32gui.SendMessage(hwnd, win32con.WM_USER, PPM_GET_PLAYBACK_STATUS, 0)
            return state != 2  # 2 = Running / Playing. 1 = Paused. -1 or 0 = Stopped.
        except Exception as e:
            logger.debug(f"Error checking pause state: {e}")
            return None

    def seek_absolute(self, seconds: float) -> bool:
        """
        Seek to absolute position in seconds in PotPlayer.
        
        Args:
            seconds: Target playback position in seconds.
            
        Returns:
            bool: True if seek command sent successfully, False otherwise.
        """
        if self.platform != 'windows' or not win32gui or not win32con:
            return False
            
        hwnd = find_potplayer_hwnd()
        if not hwnd:
            return False
            
        try:
            target_ms = max(0, int(round(seconds * 1000.0)))
            win32gui.SendMessage(hwnd, win32con.WM_USER, PPM_SET_PLAYBACK_TIME_MS, target_ms)
            logger.info(f"PotPlayer seek to {seconds:.1f}s ({target_ms}ms) succeeded")
            return True
        except Exception as e:
            logger.debug(f"Error seeking PotPlayer: {e}")
            return False

    def get_current_filepath(self, process_name=None):
        """
        Get the filepath of the currently playing file in PotPlayer.
        
        Args:
            process_name: Optional process name for consistency with other integrations
            
        Returns:
            str: Filepath of the current media, or None if unavailable
        """
        if self.platform != 'windows' or not win32gui:
            return self.cached_filepath or self.cached_filename
            
        hwnd = find_potplayer_hwnd()
        if not hwnd:
            return self.cached_filepath or self.cached_filename
            
        try:
            window_title = win32gui.GetWindowText(hwnd)
            if not window_title or window_title == "PotPlayer":
                return self.cached_filepath or self.cached_filename

            if self.last_window_title == window_title:
                return self.cached_filepath or self.cached_filename

            self.last_window_title = window_title
            
            clean_title = window_title
            if " - PotPlayer" in clean_title:
                clean_title = clean_title.replace(" - PotPlayer", "").strip()
            
            if self._is_menu_state(clean_title):
                logger.debug(f"Detected menu state: '{clean_title}', attempting process handle fallback")
                resolved_from_process = self._resolve_full_path(None, hwnd)
                if resolved_from_process:
                    if self.cached_filepath != resolved_from_process:
                        logger.debug(f"Resolved PotPlayer media via handle fallback: '{resolved_from_process}'")
                    self.cached_filepath = resolved_from_process
                    self.cached_filename = os.path.basename(resolved_from_process)
                    return resolved_from_process

                return self.cached_filepath or self.cached_filename
            
            cleaned_filename = self._clean_filename(clean_title)
            if cleaned_filename:
                # Try the raw title first (keeps "[Group]" tags the real file has), then the
                # cleaned name (handles title-only appendages like "(With subtitles)").
                resolved_path = (self._resolve_full_path(clean_title, hwnd)
                                 or self._resolve_full_path(cleaned_filename, hwnd))
                if resolved_path:
                    if self.cached_filepath != resolved_path:
                        logger.debug(f"Resolved PotPlayer media to full path: '{resolved_path}'")
                    self.cached_filepath = resolved_path
                    self.cached_filename = os.path.basename(resolved_path)
                    return resolved_path

                # Fallback: return cleaned filename if full path not available
                if self.cached_filename != cleaned_filename:
                    logger.debug(f"Cached PotPlayer filename: '{cleaned_filename}'")
                self.cached_filename = cleaned_filename
                self.cached_filepath = cleaned_filename
                return cleaned_filename

            return self.cached_filepath or self.cached_filename
                
        except Exception as e:
            logger.debug(f"Error getting filepath from PotPlayer: {e}")
            return self.cached_filepath or self.cached_filename

    def _get_process_from_hwnd(self, hwnd):
        """Return psutil.Process for the PotPlayer window handle."""
        if not hwnd or not psutil or not win32process:
            return None

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid:
                return psutil.Process(pid)
        except (psutil.Error, ValueError, RuntimeError) as exc:
            logger.debug(f"Unable to resolve PotPlayer process: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Unexpected error resolving PotPlayer process: {exc}")
        return None

    def _resolve_full_path(self, filename, hwnd):
        """Attempt to resolve the full path for the provided filename using process handles."""
        process = self._get_process_from_hwnd(hwnd)
        if not process:
            return None

        target_basename = os.path.basename(filename).lower() if filename else None

        # Try open file handles first
        video_handles = []
        try:
            for open_file in process.open_files():
                candidate_path = open_file.path
                if not candidate_path:
                    continue
                candidate_basename = os.path.basename(candidate_path).lower()
                is_video = os.path.splitext(candidate_basename)[1].lower() in VIDEO_EXTENSIONS
                if is_video:
                    video_handles.append(candidate_path)
                if target_basename:
                    target_stem, target_ext = os.path.splitext(target_basename)
                    # exact match, or stem match when the title hid the extension (video only,
                    # so we don't grab a same-named .srt)
                    if candidate_basename == target_basename or (
                        is_video and not target_ext
                        and os.path.splitext(candidate_basename)[0] == target_stem
                    ):
                        return candidate_path
                elif is_video:
                    return candidate_path
            # log what was open, for diagnosing resolution failures
            logger.debug(
                f"PotPlayer open_files() found no match for '{target_basename}'. "
                f"Open video files: {video_handles or 'none'}"
            )
        except Exception as exc:  # pragma: no cover - defensive
            if psutil and isinstance(exc, (psutil.AccessDenied, psutil.NoSuchProcess)):
                logger.debug(f"Access denied enumerating PotPlayer open files: {exc}")
            else:
                logger.debug(f"Unexpected error inspecting PotPlayer open files: {exc}")

        # Fallback: check command-line arguments (works when file opened via CLI)
        try:
            for arg in process.cmdline()[1:]:
                if not arg:
                    continue
                arg_basename = os.path.basename(arg).lower()
                if target_basename:
                    if arg_basename == target_basename and os.path.exists(arg):
                        return arg
                else:
                    if os.path.exists(arg) and os.path.splitext(arg_basename)[1].lower() in VIDEO_EXTENSIONS:
                        return arg
        except Exception as exc:  # pragma: no cover - defensive
            if psutil and isinstance(exc, (psutil.AccessDenied, psutil.NoSuchProcess)):
                logger.debug(f"Unable to resolve PotPlayer media via cmdline due to access restrictions: {exc}")
            elif isinstance(exc, (FileNotFoundError, OSError)):
                logger.debug(f"Unable to resolve PotPlayer media via cmdline: {exc}")
            else:
                logger.debug(f"Unexpected error inspecting PotPlayer cmdline: {exc}")

        return None

    def _is_menu_state(self, title):
        """Check if the title represents a menu/UI state rather than a filename."""
        if not title:
            return True
            
        menu_patterns = [
            r'^Chapter \d+',
            r'^Show main menu',
            r'^Open file',
            r'^Preferences',
            r'^Settings', 
            r'^\d{2}:\d{2}:\d{2}',
            r'Speed: \d+%',
            r'Volume: \d+%',
            r'Seeking to',
            r'Loading',
            r'Buffering',
        ]
        
        return any(re.match(pattern, title, re.IGNORECASE) for pattern in menu_patterns)

    def _clean_filename(self, filename):
        """Clean up filename by removing subtitle indicators and other appendages."""
        if not filename:
            return None
        
        cleaned = filename
        
        # Remove leading release-group style tags (e.g., [SubsPlease], [1/4])
        while True:
            updated = re.sub(r'^\[[^\]]+\]\s*', '', cleaned, flags=re.IGNORECASE)
            if updated == cleaned:
                break
            cleaned = updated

        cleaned = re.sub(r'\s*\(With subtitles\)$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\[Subtitles.*?\]$', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        
        if len(cleaned) < 3:
            return None
            
        if (any(ext in cleaned.lower() for ext in ['.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'])
            or any(pattern in cleaned for pattern in ['1080p', '720p', '4K', '2160p', 'x264', 'x265', 'HEVC', 'BluRay', 'WEB-DL'])):
            return cleaned
            
        return None
