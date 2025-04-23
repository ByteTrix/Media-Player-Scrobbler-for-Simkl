"""
PotPlayer integration for Media Player Scrobbler for SIMKL.
Allows getting position and duration data from PotPlayer via its WebRemote interface.
"""

import os
import re
import json
import logging
import requests
import platform
import winreg
from pathlib import Path
from urllib.parse import quote

# Configure module logging
logger = logging.getLogger(__name__)

class PotPlayerIntegration:
    """
    Class for interacting with PotPlayer's WebRemote interface.
    Used to get playback position and duration for more accurate scrobbling.
    """
    
    def __init__(self, base_url=None):
        """
        Initialize PotPlayer integration.
        
        Args:
            base_url: Optional base URL for PotPlayer web interface. If None, auto-detect will be used.
        """
        self.name = 'potplayer'
        self.platform = platform.system().lower()
        self.default_ports = [80, 8080, 8000]  # Common PotPlayer WebRemote ports
        
        # Set up base URL
        if base_url:
            self.base_url = base_url
        else:
            # Try to auto-detect settings from registry/config
            self.base_url = self._auto_detect_url()
            
        # Session for requests
        self.session = requests.Session()
        self.session.timeout = 1.0  # Short timeout to prevent hanging
        
        # Flag to remember which port worked last
        self.working_port = None
        self.working_password = None

    def _auto_detect_url(self):
        """Auto-detect PotPlayer WebRemote URL from registry or config files"""
        if self.platform != 'windows':
            logger.warning("PotPlayer is primarily a Windows application")
            return "http://localhost:8080"  # Default fallback
            
        try:
            # Get WebRemote settings from registry
            port, password = self._read_registry_settings()
            if port:
                logger.info(f"Found PotPlayer WebRemote port in registry: {port}")
                self.working_port = port
                self.working_password = password
                return f"http://localhost:{port}"
        except Exception as e:
            logger.debug(f"Could not read PotPlayer settings from registry: {e}")
            
        # Default to common ports
        logger.debug("Using default PotPlayer ports for detection")
        return "http://localhost:8080"  # Common default
        
    def _read_registry_settings(self):
        """Read PotPlayer WebRemote settings from Windows registry"""
        try:
            # PotPlayer registry path
            potplayer_path = r"Software\DAUM\PotPlayer64"
            hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, potplayer_path)
            
            # Try to find WebRemote settings
            # Note: Actual registry entries may vary based on PotPlayer version and configuration
            try:
                port = winreg.QueryValueEx(hkey, "WebRemotePort")[0]
                password = winreg.QueryValueEx(hkey, "WebRemotePassword")[0]
                return port, password
            except FileNotFoundError:
                # Registry entries not found, try alternate paths
                alternate_path = r"Software\DAUM\PotPlayer"
                try:
                    hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, alternate_path)
                    port = winreg.QueryValueEx(hkey, "WebRemotePort")[0]
                    password = winreg.QueryValueEx(hkey, "WebRemotePassword")[0]
                    return port, password
                except:
                    return None, None
        except Exception as e:
            logger.debug(f"Error reading PotPlayer settings from registry: {e}")
            return None, None
            
    def _find_config_file(self):
        """Find PotPlayer config file locations"""
        # Common PotPlayer config locations
        config_paths = []
        
        if self.platform == 'windows':
            # Check ProgramData location (common for all users)
            program_data = os.environ.get('PROGRAMDATA')
            if program_data:
                config_paths.append(Path(program_data) / "PotPlayer" / "PotPlayerMini64.ini")
                
            # Check user appdata location
            appdata = os.environ.get('APPDATA')
            if appdata:
                config_paths.append(Path(appdata) / "PotPlayer" / "PotPlayerMini64.ini")
                
            # Check installation directory (common location)
            program_files = os.environ.get('PROGRAMFILES')
            if program_files:
                config_paths.append(Path(program_files) / "DAUM" / "PotPlayer" / "PotPlayerMini64.ini")
                
        for config_path in config_paths:
            if config_path.exists():
                return config_path
                
        return None
            
    def _get_command_url(self, command, port=None, params=None):
        """
        Create URL for PotPlayer WebRemote command
        
        Args:
            command: Command name to send
            port: Port to use (optional)
            params: Additional parameters as dictionary
            
        Returns:
            Complete URL for the command
        """
        if port:
            base = f"http://localhost:{port}"
        elif self.working_port:
            base = f"http://localhost:{self.working_port}"
        else:
            base = self.base_url
            
        url = f"{base}/{command}"
        
        # Add password if we have one
        if params is None:
            params = {}
            
        if self.working_password:
            params['password'] = self.working_password
            
        # Convert params to query string
        if params:
            query_parts = []
            for key, value in params.items():
                if value is not None:
                    query_parts.append(f"{key}={quote(str(value))}")
            if query_parts:
                url += "?" + "&".join(query_parts)
                
        return url
    
    def get_status(self, port=None):
        """
        Get current playback status from PotPlayer
        
        Args:
            port: Port to use (optional)
            
        Returns:
            Dictionary with status information or None if failed
        """
        url = self._get_command_url("status", port)
        try:
            response = self.session.get(url, timeout=0.5)
            if response.status_code == 200:
                if port:
                    self.working_port = port  # Remember working port
                # Parse response - could be JSON or plain text
                try:
                    return response.json()
                except json.JSONDecodeError:
                    # Parse text response format
                    data = {}
                    text = response.text
                    for line in text.splitlines():
                        if ":" in line:
                            key, value = line.split(":", 1)
                            data[key.strip()] = value.strip()
                    return data
            return None
        except requests.RequestException:
            return None
    
    def get_position_duration(self, process_name=None):
        """
        Get current position and duration from PotPlayer.
        
        Args:
            process_name: Process name (ignored, used for consistency with other integrations)
            
        Returns:
            tuple: (position_seconds, duration_seconds) or (None, None) if unavailable
        """
        # First try the working port if we have one
        if self.working_port:
            status = self.get_status(self.working_port)
            if status:
                return self._extract_position_duration(status)
                
        # If no working port or it failed, try all default ports
        for port in self.default_ports:
            if port == self.working_port:
                continue  # Already tried this one
                
            status = self.get_status(port)
            if status:
                logger.info(f"Successfully connected to PotPlayer WebRemote on port {port}")
                self.working_port = port  # Remember this working port
                return self._extract_position_duration(status)
                
        return None, None  # Failed to get position/duration
        
    def _extract_position_duration(self, status):
        """
        Extract position and duration from status response
        
        Args:
            status: Status data from PotPlayer
            
        Returns:
            tuple: (position_seconds, duration_seconds) or (None, None)
        """
        # Check if we have actual data (different versions might use different field names)
        if not status:
            return None, None
            
        # Try various field names that might contain position/duration
        position = None
        duration = None
        
        # Check for fields in JSON response format
        if isinstance(status, dict):
            # Current position field names
            position_fields = ['position', 'currentposition', 'current', 'pos', 'time', 'currentTime']
            for field in position_fields:
                if field in status and status[field] not in (None, '', '0'):
                    try:
                        # Convert to float, handling different formats
                        pos_val = status[field]
                        if isinstance(pos_val, (int, float)):
                            position = float(pos_val)
                        else:
                            # Try to convert from string formats like "00:01:23"
                            time_parts = pos_val.split(':')
                            if len(time_parts) == 3:
                                # HH:MM:SS format
                                position = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(time_parts[2])
                            elif len(time_parts) == 2:
                                # MM:SS format
                                position = float(time_parts[0]) * 60 + float(time_parts[1])
                            else:
                                # Try direct conversion
                                position = float(pos_val)
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Duration field names
            duration_fields = ['duration', 'length', 'total', 'totalTime']
            for field in duration_fields:
                if field in status and status[field] not in (None, '', '0'):
                    try:
                        # Convert to float, handling different formats
                        dur_val = status[field]
                        if isinstance(dur_val, (int, float)):
                            duration = float(dur_val)
                        else:
                            # Try to convert from string formats
                            time_parts = dur_val.split(':')
                            if len(time_parts) == 3:
                                # HH:MM:SS format
                                duration = float(time_parts[0]) * 3600 + float(time_parts[1]) * 60 + float(time_parts[2])
                            elif len(time_parts) == 2:
                                # MM:SS format
                                duration = float(time_parts[0]) * 60 + float(time_parts[1])
                            else:
                                # Try direct conversion
                                duration = float(dur_val)
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Return results if we have both values
        if position is not None and duration is not None:
            return position, duration
        else:
            return None, None