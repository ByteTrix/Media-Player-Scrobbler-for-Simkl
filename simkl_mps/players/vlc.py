"""
VLC integration module for Media Player Scrobbler for SIMKL.
Provides functionality to interact with VLC's web interface across platforms.
"""

import os
import sys
import json
import logging
import requests
import platform
from pathlib import Path
from configparser import ConfigParser

# Setup module logger
logger = logging.getLogger(__name__)

class VLCIntegration:
    """
    Class for interacting with VLC's web interface across platforms.
    Used to get playback position and duration for more accurate scrobbling.
    """
    
    def __init__(self):
        self.name = 'vlc'
        self.platform = platform.system().lower()
        self.last_successful_config = None
        self.session = requests.Session()
        
        # Try to read VLC configuration
        try:
            self.vlc_config = self._read_vlc_config()
            logger.debug(f"Found VLC configuration: {self.vlc_config}")
        except Exception as e:
            logger.debug(f"Could not read VLC configuration: {e}")
            self.vlc_config = {"port": 8080, "password": ""}
    
    def _read_vlc_config(self):
        """Read VLC configuration from platform-specific locations."""
        config = {}
        
        # Determine VLC preferences path based on platform
        if self.platform == "darwin":  # macOS
            prefs_paths = [Path("~/Library/Preferences/org.videolan.vlc").expanduser()]
            config_file = "vlcrc"
        elif self.platform == "win32" or self.platform == "windows":  # Windows
            prefs_paths = [
                Path(os.environ.get("APPDATA", "")) / "vlc",
                Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Roaming" / "vlc"
            ]
            config_file = "vlcrc"
        else:  # Linux/Unix
            prefs_paths = [
                Path("~/.config/vlc").expanduser(),
                Path("~/snap/vlc/common/").expanduser(),
                Path("~/.var/app/org.videolan.VLC/config/vlc").expanduser(),  # Flatpak
            ]
            config_file = "vlcrc"
        
        # Try to read from each possible location
        vlcrc = ConfigParser(strict=False, inline_comment_prefixes="#")
        vlcrc.optionxform = lambda option: option
        
        found_config = False
        for prefs_path in prefs_paths:
            vlcrc_path = prefs_path / config_file
            if vlcrc_path.exists():
                try:
                    vlcrc.read(vlcrc_path, encoding="utf-8-sig")
                    found_config = True
                    logger.debug(f"Found VLC config at {vlcrc_path}")
                    break
                except Exception as e:
                    logger.debug(f"Error reading {vlcrc_path}: {e}")
        
        if not found_config:
            logger.debug("Could not find VLC configuration file")
            return {"port": 8080, "password": ""}
        
        # Extract port and password
        try:
            port = vlcrc.get("core", "http-port", fallback=8080)
            # Convert to int if possible
            try:
                port = int(port)
            except ValueError:
                port = 8080
        except Exception:
            port = 8080
        
        try:
            password = vlcrc.get("lua", "http-password", fallback="")
        except Exception:
            password = ""
        
        return {"port": port, "password": password}
    
    def get_position_duration(self, process_name=None):
        """
        Get current playback position and duration from VLC.
        
        Args:
            process_name: Optional process name for debugging
            
        Returns:
            tuple: (position, duration) in seconds, or (None, None) if unavailable
        """
        # If we have a successful config from a previous call, try it first
        if self.last_successful_config:
            position, duration = self._try_vlc_config(self.last_successful_config)
            if position is not None and duration is not None:
                return position, duration
        
        # Try with configuration from vlcrc first
        config = {"port": self.vlc_config["port"], "password": self.vlc_config["password"]}
        position, duration = self._try_vlc_config(config)
        if position is not None and duration is not None:
            return position, duration
        
        # Try common fallback configurations
        common_configs = [
            {"port": 8080, "password": ""},
            {"port": 8080, "password": "admin"},
            {"port": 8080, "password": "simkl"},
            {"port": 9090, "password": ""},
            {"port": 8888, "password": ""}
        ]
        
        # Add the vlcrc password with different ports if it's not empty
        if self.vlc_config["password"] and self.vlc_config["password"] not in ["", "admin", "simkl"]:
            for port in [8080, 9090, 8888]:
                common_configs.append({"port": port, "password": self.vlc_config["password"]})
        
        for config in common_configs:
            position, duration = self._try_vlc_config(config)
            if position is not None and duration is not None:
                return position, duration
        
        # If we reach here, we couldn't connect to VLC
        return None, None
    
    def _try_vlc_config(self, config):
        """
        Try to connect to VLC with the given configuration.
        
        Args:
            config: Dictionary with port and password
            
        Returns:
            tuple: (position, duration) in seconds, or (None, None) if unavailable
        """
        port = config["port"]
        password = config["password"]
        status_url = f"http://localhost:{port}/requests/status.json"
        
        try:
            # Setup session with auth if password is provided
            if password:
                self.session.auth = ('', password)  # VLC uses empty username
            else:
                self.session.auth = None
            
            # Try to connect with timeout
            response = self.session.get(status_url, timeout=1.0)
            response.raise_for_status()
            data = response.json()
            
            # Check if we received valid data
            if 'time' in data and 'length' in data:
                position = data.get('time')
                duration = data.get('length')
                
                # Get additional info for logging
                filename = data.get('information', {}).get('category', {}).get('meta', {}).get('filename', 'Unknown file')
                
                logger.info(f"Successfully connected to VLC web interface on port {port}")
                logger.debug(f"VLC is playing: {filename}")
                logger.debug(f"Retrieved position data from VLC: position={position}s, duration={duration}s")
                
                # Save successful config for future attempts
                self.last_successful_config = config
                
                # Validate data
                if isinstance(position, (int, float)) and isinstance(duration, (int, float)) and duration > 0 and position >= 0:
                    position = min(position, duration)  # Ensure position doesn't exceed duration
                    return round(position, 2), round(duration, 2)
            
            logger.debug(f"Connected to VLC on port {port} but no valid position/duration data")
        except requests.exceptions.RequestException as e:
            logger.debug(f"Could not connect to VLC on port {port} with auth={password != ''}: {str(e)}")
        except Exception as e:
            logger.debug(f"Error processing VLC data: {e}")
        
        return None, None
    
    def get_current_filepath(self):
        """
        Get the filepath of the currently playing file in VLC.
        
        Returns:
            str: Filepath of the current media, or None if unavailable
        """
        if not self.last_successful_config:
            # Try to get position/duration first to establish a connection
            self.get_position_duration()
            if not self.last_successful_config:
                return None
        
        port = self.last_successful_config["port"]
        password = self.last_successful_config["password"]
        playlist_url = f"http://localhost:{port}/requests/playlist.json"
        
        try:
            # Setup session with auth if password is provided
            if password:
                self.session.auth = ('', password)
            else:
                self.session.auth = None
            
            # Get playlist data
            response = self.session.get(playlist_url, timeout=1.0)
            response.raise_for_status()
            playlist_data = response.json()
            
            # Search for current item
            file_data = self._search_dict_for_current(playlist_data)
            if file_data and 'uri' in file_data:
                uri = file_data['uri']
                # Convert URI to path
                return self._file_uri_to_path(uri)
        except Exception as e:
            logger.debug(f"Error getting current filepath from VLC: {e}")
        
        return None
    
    def _search_dict_for_current(self, dict_):
        """Find a dict which has 'current' key."""
        if isinstance(dict_, list):
            for d in dict_:
                data = self._search_dict_for_current(d)
                if data:
                    return data
        elif 'current' in dict_:
            return dict_
        elif 'children' in dict_:
            return self._search_dict_for_current(dict_['children'])
        return None
    
    def _file_uri_to_path(self, uri):
        """Convert file URI to path."""
        if uri.startswith('file:///'):
            # Remove 'file://' prefix and handle URL encoding
            from urllib.parse import unquote
            if sys.platform == 'win32' or sys.platform == 'windows':
                # On Windows, file URIs look like file:///C:/path/to/file
                path = unquote(uri[8:])
            else:
                # On Unix-like systems, file URIs look like file:///path/to/file
                path = unquote(uri[7:])
            return path
        return uri  # Return as-is if not a file URI