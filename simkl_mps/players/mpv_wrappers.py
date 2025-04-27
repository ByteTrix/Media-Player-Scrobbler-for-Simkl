"""
MPV Wrappers integration for Media Player Scrobbler for SIMKL.
This module provides support for media players that use MPV as a backend.
"""

import logging
import platform
import os
import re
import sys
import json
from pathlib import Path
from configparser import ConfigParser
from functools import wraps

from simkl_mps.players.mpv import MPVIntegration, MPVError

logger = logging.getLogger(__name__)

# Regular expression to match IPC path in MPV arguments
ARG_PAT = re.compile(r'--input-ipc-server=(?P<ipc_path>[^\'" ]+)')

# List of known MPV wrapper applications across platforms
MPV_WRAPPERS = {
    "Windows": [
        # Format: [executable_name, display_name, config_hint]
        ["mpvnet.exe", "MPV.net", "%APPDATA%\\mpv.net\\mpv.conf"],
        ["smplayer.exe", "SMPlayer", "%APPDATA%\\SMPlayer\\mpv\\mpv.conf"],
        ["syncplay.exe", "Syncplay", "%APPDATA%\\Syncplay\\mpv.conf"]
    ],
    "Darwin": [  # macOS
        # Format: [executable_name, display_name, config_hint]
        ["iina", "IINA", "~/.config/mpv/mpv.conf or ~/Library/Application Support/io.iina.iina/mpv.conf"],
        ["mpv.app", "MPV", "~/.config/mpv/mpv.conf"],
        ["io.iina.IINA", "IINA", "~/.config/mpv/mpv.conf or ~/Library/Application Support/io.iina.iina/mpv.conf"],
        ["smplayer", "SMPlayer", "~/.config/smplayer/mpv/mpv.conf"],
        ["syncplay", "Syncplay", "~/.config/Syncplay/mpv.conf"],
    ],
    "Linux": [
        # Format: [executable_name, display_name, config_hint]
        ["celluloid", "Celluloid (GNOME MPV)", "~/.config/mpv/mpv.conf"],
        ["haruna", "Haruna Player", "~/.config/haruna/mpv.conf"],
        ["smplayer", "SMPlayer", "~/.config/smplayer/mpv/mpv.conf"],
        ["iina", "IINA", "~/.config/mpv/mpv.conf"],  # macOS app running through Darling or similar
        ["mpv.net", "MPV.net", "~/.config/mpv.net/mpv.conf"],
        ["syncplay", "Syncplay", "~/.config/syncplay/mpv.conf"],
    ]
}

# Common config path locations 
CONFIG_PATHS = {
    "SMPlayer": {
        "Windows": [
            "%APPDATA%\\SMPlayer\\smplayer.ini", 
            "%USERPROFILE%\\.config\\smplayer\\smplayer.ini",
            "%USERPROFILE%\\.smplayer\\smplayer.ini"
        ],
        "Darwin": [
            "~/Library/Preferences/org.smplayer.SMPlayer.plist", 
            "~/.config/smplayer/smplayer.ini",
            "~/.smplayer/smplayer.ini"
        ],
        "Linux": [
            "~/.config/smplayer/smplayer.ini",
            "~/.smplayer/smplayer.ini"
        ]
    },
    "Syncplay": {
        "Windows": [
            "%APPDATA%\\syncplay.ini",
            "%APPDATA%\\Syncplay\\syncplay.ini",
            "%LOCALAPPDATA%\\Syncplay\\syncplay.ini",
        ],
        "Darwin": [
            "~/.config/syncplay.ini",
            "~/.syncplay",
        ],
        "Linux": [
            "~/.config/syncplay.ini",
            "~/.syncplay",
        ]
    }
}

def with_custom_ipc_path(func):
    """
    Decorator to handle custom IPC path logic for MPV wrapper methods.
    Temporarily sets the custom IPC path if needed, calls the original method,
    then restores the original path.
    """
    @wraps(func)
    def wrapper(self, process_name=None, *args, **kwargs):
        if not process_name:
            return func(self, process_name, *args, **kwargs)
        
        # Check for custom IPC path for this process
        custom_ipc_path = self._get_custom_ipc_path(process_name)
        if not custom_ipc_path:
            return func(self, process_name, *args, **kwargs)
        
        # Get wrapper info for logging
        wrapper_exe, wrapper_name, _ = self.get_wrapper_info(process_name)
        wrapper_display = wrapper_name or process_name
        logger.debug(f"Using custom IPC path for {wrapper_display}: {custom_ipc_path}")
        
        # Temporarily change the IPC path
        original_ipc_path = self.mpv_integration.ipc_path
        self.mpv_integration.ipc_path = custom_ipc_path
        
        try:
            # Call the original method with the custom IPC path
            return func(self, process_name, *args, **kwargs)
        except Exception as e:
            # Log any errors
            if isinstance(e, MPVError):
                logger.warning(f"Error in {func.__name__} for {wrapper_display}: {e}")
            else:
                logger.error(f"Unexpected error in {func.__name__} for {wrapper_display}: {e}", exc_info=True)
            return None if func.__name__ != "get_position_duration" else (None, None)
        finally:
            # Always restore the original IPC path
            self.mpv_integration.ipc_path = original_ipc_path
    
    return wrapper

class MPVWrapperIntegration:
    """
    Class for handling MPV wrapper applications that use MPV as their backend.
    This class extends the functionality of the core MPVIntegration class
    to support various MPV-based players.
    """
    
    def __init__(self):
        self.platform = platform.system()
        # Use the core MPV integration for actual IPC communication
        self.mpv_integration = MPVIntegration()
        self.known_wrappers = self._get_wrappers_for_platform()
        self.wrappers_regex = self._compile_wrapper_regex()
        # Dynamically update configuration paths based on platform
        self._update_config_paths()
        # Cache for IPC paths to avoid repeated config file reads
        self._ipc_path_cache = {}
        logger.info(f"MPV Wrapper Integration initialized with {len(self.known_wrappers)} known wrappers")
    
    def _update_config_paths(self):
        """
        Update configuration paths with platform-specific paths that are more likely to exist.
        """
        try:
            # Add additional common SMPlayer config locations
            if self.platform == "Windows":
                CONFIG_PATHS["SMPlayer"]["Windows"].append(str(Path.home() / ".smplayer" / "smplayer.ini"))
                
                # Try to get the user config dir if appdirs is available
                try:
                    import appdirs
                    config_dir = Path(appdirs.user_config_dir("smplayer", roaming=True, appauthor=False))
                    CONFIG_PATHS["SMPlayer"]["Windows"].append(str(config_dir / "smplayer.ini"))
                except ImportError:
                    logger.debug("appdirs module not available for SMPlayer config path detection")
            elif self.platform == "Linux":
                CONFIG_PATHS["SMPlayer"]["Linux"].append(str(Path.home() / ".config" / "smplayer" / "smplayer.ini"))
                CONFIG_PATHS["SMPlayer"]["Linux"].append(str(Path.home() / ".local" / "share" / "smplayer" / "smplayer.ini"))
            
            # Add Syncplay additional paths based on read_player_cfg logic
            try:
                import appdirs
                if self.platform == "Windows":
                    # Add both roaming and local app data directories
                    roaming_dir = Path(appdirs.user_data_dir(appname="Syncplay", roaming=True))
                    local_dir = Path(appdirs.user_data_dir(appname="Syncplay", roaming=False))
                    
                    for dir_path in [roaming_dir, local_dir]:
                        for filename in ["syncplay.ini", ".syncplay"]:
                            config_path = str(dir_path / filename)
                            if config_path not in CONFIG_PATHS["Syncplay"]["Windows"]:
                                CONFIG_PATHS["Syncplay"]["Windows"].append(config_path)
                else:
                    # Unix-like systems (Linux/macOS)
                    # Check XDG_CONFIG_HOME and home directory
                    xdg_config = Path(os.getenv('XDG_CONFIG_HOME', "~/.config")).expanduser()
                    home_dir = Path.home()
                    
                    platform_key = "Linux" if self.platform == "Linux" else "Darwin"
                    
                    for dir_path in [xdg_config / "syncplay", xdg_config / "Syncplay", home_dir]:
                        for filename in ["syncplay.ini", ".syncplay"]:
                            config_path = str(dir_path / filename)
                            if config_path not in CONFIG_PATHS["Syncplay"][platform_key]:
                                CONFIG_PATHS["Syncplay"][platform_key].append(config_path)
            except ImportError:
                logger.debug("appdirs module not available for Syncplay additional config path detection")
                
            logger.debug(f"Updated config paths for {self.platform}")
        except Exception as e:
            logger.warning(f"Failed to update config paths: {e}")
    
    def _get_wrappers_for_platform(self):
        """Get the list of known MPV wrappers for the current platform."""
        return MPV_WRAPPERS.get(self.platform, [])
    
    def _compile_wrapper_regex(self):
        """Compile a regex pattern to match MPV wrapper process names."""
        if not self.known_wrappers:
            return None
        
        # Extract just the executable names
        wrapper_exes = [wrapper[0] for wrapper in self.known_wrappers]
        
        # Create a regex pattern that matches any of the wrapper executables
        # This handles cases like "smplayer.exe" and variation cases
        pattern = r'|'.join([re.escape(exe.lower()) for exe in wrapper_exes])
        if pattern:
            return re.compile(pattern)
        return None
    
    def is_mpv_wrapper(self, process_name):
        """
        Check if the given process name is a known MPV wrapper.
        
        Args:
            process_name (str): The process name to check
            
        Returns:
            bool: True if the process is a known MPV wrapper, False otherwise
        """
        if not process_name or not self.wrappers_regex:
            return False
        
        process_lower = process_name.lower()
        
        return bool(self.wrappers_regex.search(process_lower))
    
    def get_wrapper_info(self, process_name):
        """
        Get information about an MPV wrapper from its process name.
        
        Args:
            process_name (str): The process name to check
            
        Returns:
            tuple: (executable_name, display_name, config_hint) or (None, None, None)
        """
        if not process_name:
            return None, None, None
        
        process_lower = process_name.lower()
        for wrapper_info in self.known_wrappers:
            if wrapper_info[0].lower() in process_lower:
                return wrapper_info
        
        return None, None, None
    
    def _expand_path(self, path_str):
        """
        Expand environment variables and user directory in a path string.
        
        Args:
            path_str (str): The path string to expand
            
        Returns:
            Path: The expanded path
        """
        if not path_str:
            return None
        
        # Replace environment variables
        path_str = os.path.expandvars(path_str)
        # Replace ~ with user home directory
        path_str = os.path.expanduser(path_str)
        
        return Path(path_str)
    
    def _normalize_ipc_path(self, ipc_path):
        """
        Normalize IPC path to ensure it's in the correct format.
        For Windows pipe paths, this handles any escaped backslashes.
        
        Args:
            ipc_path (str): The IPC path to normalize
            
        Returns:
            str: The normalized IPC path
        """
        if not ipc_path:
            return ipc_path
            
        # Fix for Windows pipe paths with escaped backslashes
        if self.platform == "Windows" and r"\\\\" in ipc_path and "pipe" in ipc_path:
            # Convert escaped backslashes to regular backslashes
            normalized_path = ipc_path.replace(r"\\", "\\")
            logger.debug(f"Normalized Windows pipe path: '{ipc_path}' -> '{normalized_path}'")
            return normalized_path
            
        return ipc_path
    
    def _read_config_file(self, player_name, config_path, extract_func):
        """
        Generic method to read a config file and extract IPC path using a provided function.
        
        Args:
            player_name (str): Name of the player for logging
            config_path (Path): Path to the config file
            extract_func (callable): Function to extract IPC path from the config
            
        Returns:
            str or None: The IPC path if found, None otherwise
        """
        if not config_path or not config_path.exists():
            return None
        
        logger.debug(f"Reading {player_name} config from: {config_path}")
        
        try:
            if self.platform == "Darwin" and str(config_path).endswith(".plist"):
                logger.debug(f"macOS plist files are not yet supported for {player_name}")
                return None
            
            result = extract_func(config_path)
            if result:
                # Normalize the path to fix escaped backslashes
                result = self._normalize_ipc_path(result)
                logger.info(f"Found {player_name} MPV IPC path: {result}")
            return result
        except Exception as e:
            logger.error(f"Error reading {player_name} config file {config_path}: {e}", exc_info=True)
            return None
    
    def _extract_smplayer_ipc(self, config_path):
        """Extract IPC path from SMPlayer config file."""
        config = ConfigParser(allow_no_value=True, strict=False)
        config.optionxform = lambda option: option  # Preserve case
        config.read(config_path, encoding="utf-8-sig")
        
        if "advanced" in config.sections():
            mpv_options = config.get("advanced", "mplayer_additional_options", fallback="")
            if mpv_options:
                # Look for --input-ipc-server pattern
                match = ARG_PAT.search(mpv_options)
                if match:
                    return match.group("ipc_path")
        return None
    
    def _extract_syncplay_ipc(self, config_path):
        """Extract IPC path from Syncplay config file."""
        try:
            config = ConfigParser(allow_no_value=True, strict=False)
            config.optionxform = lambda option: option  # Preserve case
            config.read(config_path, encoding="utf-8-sig")
            
            # First check if MPV is the selected player
            section_name = "client-settings" if "client-settings" in config.sections() else "client_settings"
            if section_name not in config.sections():
                logger.debug(f"Syncplay config file {config_path} does not have a {section_name} section")
                return None
            
            selected_player = config.get(section_name, "mediaplayer", fallback="")
            if not selected_player or selected_player.lower() != "mpv":
                logger.debug(f"Syncplay is not using MPV (current: {selected_player})")
                return None
            
            # Try to get player arguments
            arg_option = "perplayerarguments"
            if not config.has_option(section_name, arg_option):
                logger.debug(f"Syncplay config does not have {arg_option} option")
                return None
            
            mpv_args = config.get(section_name, arg_option, fallback="")
            
            # Try to parse JSON first (newer Syncplay versions)
            try:
                args_dict = json.loads(mpv_args)
                mpv_specific_args = args_dict.get("mpv", "")
                
                # Look for --input-ipc-server pattern
                match = ARG_PAT.search(mpv_specific_args)
                if match:
                    return match.group("ipc_path")
            except (json.JSONDecodeError, TypeError):
                # If not JSON, try direct string parsing (older Syncplay versions)
                match = ARG_PAT.search(mpv_args)
                if match:
                    return match.group("ipc_path")
            
            return None
        except Exception as e:
            logger.error(f"Error parsing Syncplay config {config_path}: {e}")
            return None
    
    def _read_player_config(self, player_name, extract_func):
        """
        Read configuration files for a specific player.
        
        Args:
            player_name (str): Name of the player (key in CONFIG_PATHS)
            extract_func (callable): Function to extract IPC path from config
            
        Returns:
            str or None: The IPC path if found, None otherwise
        """
        if player_name not in CONFIG_PATHS or self.platform not in CONFIG_PATHS[player_name]:
            logger.debug(f"No config paths defined for {player_name} on {self.platform}")
            return None
        
        config_paths = CONFIG_PATHS[player_name][self.platform]
        for config_path_str in config_paths:
            config_path = self._expand_path(config_path_str)
            result = self._read_config_file(player_name, config_path, extract_func)
            if result:
                return result
        
        return None
    
    def _get_custom_ipc_path(self, process_name):
        """
        Get a custom IPC path for specific known wrappers.
        Uses cached values when available to avoid repeated config file reads.
        
        Args:
            process_name (str): The process name to check
            
        Returns:
            str or None: The IPC path if found, None otherwise
        """
        if not process_name:
            return None
        
        process_lower = process_name.lower()
        
        # Check cache first
        if process_lower in self._ipc_path_cache:
            cached_path = self._ipc_path_cache[process_lower]
            logger.debug(f"Using cached IPC path for {process_lower}: {cached_path}")
            return cached_path
        
        # Not in cache, need to read from config
        ipc_path = None
        
        # SMPlayer-specific configuration
        if "smplayer" in process_lower:
            ipc_path = self._read_player_config("SMPlayer", self._extract_smplayer_ipc)
        
        # Syncplay-specific configuration
        elif "syncplay" in process_lower:
            ipc_path = self._read_player_config("Syncplay", self._extract_syncplay_ipc)
        
        # Cache the result (even if it's None, to avoid repeated lookups)
        self._ipc_path_cache[process_lower] = ipc_path
        return ipc_path
    
    @with_custom_ipc_path
    def get_position_duration(self, process_name):
        """
        Get playback position and duration from an MPV wrapper player.
        
        Args:
            process_name (str): The process name of the player
            
        Returns:
            tuple: (position_seconds, duration_seconds) or (None, None)
        """
        if not self.is_mpv_wrapper(process_name):
            return None, None
        
        wrapper_exe, wrapper_name, _ = self.get_wrapper_info(process_name)
        if not wrapper_exe:
            return None, None
            
        logger.debug(f"MPV wrapper detected: {wrapper_name} ({process_name})")
        
        # Use the core MPV integration to get position and duration
        pos, dur = self.mpv_integration.get_position_duration(process_name)
        
        if pos is not None and dur is not None:
            logger.debug(f"Retrieved position data from {wrapper_name}: position={pos}s, duration={dur}s")
            return pos, dur
        else:
            logger.debug(f"{wrapper_name} integration couldn't get position/duration data")
            return None, None
    
    @with_custom_ipc_path
    def get_current_filepath(self, process_name=None):
        """
        Get the filepath of the currently playing file in the MPV wrapper.
        
        Args:
            process_name (str, optional): The process name to check for a custom IPC path
            
        Returns:
            str or None: The filepath if found, None otherwise
        """
        return self.mpv_integration.get_current_filepath()
    
    @with_custom_ipc_path
    def is_paused(self, process_name=None):
        """
        Check if playback is paused in the MPV wrapper.
        
        Args:
            process_name (str, optional): The process name to check for a custom IPC path
            
        Returns:
            bool or None: True if paused, False if playing, None if unknown
        """
        return self.mpv_integration.is_paused()