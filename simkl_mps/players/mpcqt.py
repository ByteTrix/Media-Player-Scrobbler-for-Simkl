"""
Media Player Classic Qute Theater (MPC-QT) integration for Media Player Scrobbler for SIMKL.
Allows getting position and duration data from MPC-QT through its web interface.
"""

import re
import logging
import requests
import platform
import os
from pathlib import Path

# Only import Windows-specific modules on Windows
PLATFORM = platform.system().lower()
if PLATFORM == 'windows':
    try:
        import winreg
    except ImportError:
        winreg = None

# Configure module logging
logger = logging.getLogger(__name__)

# MPC variables pattern
PATTERN = re.compile(r'\<p id=\"([a-z]+)\"\>(.*?)\<', re.MULTILINE)

class MPCQTIntegration:
    """MPC-QT integration via web interface"""
    
    def __init__(self, base_url=None):
        """
        Initialize MPC-QT integration.
        
        Args:
            base_url: Optional base URL for MPC-QT web interface. If None, auto-detect will be used.
        """
        self.name = 'mpc-qt'
        self.platform = platform.system().lower()
        self.default_ports = [13579]  # MPC-QT uses the same port as MPC-HC
        
        # Set up base URL
        if base_url:
            self.base_url = base_url
        else:
            # Try to auto-detect port from registry
            self.base_url = self._auto_detect_url()
            
        # Session for requests
        self.session = requests.Session()
        self.session.timeout = 1.0  # Short timeout to prevent hanging
        
        # Flag to remember which port worked last
        self.working_port = None
        
        logger.info(f"MPC-QT integration initialized with base URL: {self.base_url}")

    def _auto_detect_url(self):
        """Auto-detect MPC-QT web interface URL from registry"""
        if self.platform != 'windows':
            return "http://localhost:13579"  # Default port for non-Windows
            
        try:
            # Try to get port from registry - MPC-QT may use its own registry key in the future
            port = self._read_registry_port()
            if port:
                logger.info(f"Found MPC-QT port in registry: {port}")
                return f"http://localhost:{port}"
        except Exception as e:
            logger.debug(f"Could not read MPC-QT port from registry: {e}")
            
        # Default to standard port
        logger.debug("Using default MPC-QT port 13579")
        return "http://localhost:13579"
        
    def _read_registry_port(self):
        """Read MPC-QT web interface port from Windows registry"""
        try:
            # MPC-QT might create its own registry key in the future
            # Currently it would use the standard web interface port 13579
            qt_path = "Software\\MPC-QT\\Settings"
            hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, qt_path)
            port = winreg.QueryValueEx(hkey, "WebServerPort")[0]
            return port
        except FileNotFoundError:
            # If not found, just use default
            return 13579
        except Exception as e:
            logger.debug(f"Error reading MPC-QT port from registry: {e}")
            return 13579
            
    def _get_variables_url(self, port=None):
        """Get the variables.html URL for the specified port"""
        if port:
            return f"http://localhost:{port}/variables.html"
        elif self.working_port:
            return f"http://localhost:{self.working_port}/variables.html"
        else:
            base = self.base_url.split(':')
            if len(base) >= 3:  # Protocol + host + port
                host = base[1].strip('/')
                port = base[2].split('/')[0]  # Remove path if any
                return f"http://{host}:{port}/variables.html"
            else:
                return f"{self.base_url}/variables.html"
    
    def get_vars(self, port=None):
        """Get variables from MPC-QT web interface"""
        url = self._get_variables_url(port)
        try:
            response = self.session.get(url, timeout=0.5)
            if response.status_code == 200:
                text = response.content.decode("utf-8", errors="ignore")
                matches = PATTERN.findall(text)
                if port:
                    self.working_port = port  # Remember working port
                return dict(matches)
            return None
        except requests.RequestException:
            return None
    
    def get_position_duration(self, process_name=None):
        """
        Get current position and duration from MPC-QT player.
        
        Args:
            process_name: Process name (ignored, used for consistency with other integrations)
            
        Returns:
            tuple: (position_seconds, duration_seconds) or (None, None) if unavailable
        """
        # First try the working port if we have one
        if self.working_port:
            variables = self.get_vars(self.working_port)
            if variables and variables.get('duration', '0') != '0':
                position = int(variables.get('position', 0)) / 1000.0  # MPC-QT reports in milliseconds
                duration = int(variables.get('duration', 0)) / 1000.0
                return position, duration
                
        # If no working port or it failed, try all default ports
        for port in self.default_ports:
            if port == self.working_port:
                continue  # Already tried this one
                
            variables = self.get_vars(port)
            if variables and variables.get('duration', '0') != '0':
                position = int(variables.get('position', 0)) / 1000.0  # MPC-QT reports in milliseconds
                duration = int(variables.get('duration', 0)) / 1000.0
                logger.info(f"Successfully connected to MPC-QT web interface on port {port}")
                self.working_port = port  # Remember this working port
                return position, duration
                
        return None, None  # Failed to get position/duration
        
    def is_paused(self):
        """
        Check if MPC-QT playback is paused
        
        Returns:
            bool: True if paused, False if playing, None if unknown
        """
        # Try working port first
        if self.working_port:
            variables = self.get_vars(self.working_port)
            if variables:
                state = variables.get('state', '')
                return state == '2'  # MPC-QT state 2 = paused
        
        # If no working port or it failed, try all default ports
        for port in self.default_ports:
            if port == self.working_port:
                continue  # Already tried this one
                
            variables = self.get_vars(port)
            if variables:
                state = variables.get('state', '')
                return state == '2'  # MPC-QT state 2 = paused
                
        return None  # Couldn't determine pause state
    
    def get_current_filepath(self, process_name=None):
        """
        Get the currently playing file path from MPC-QT
        
        Args:
            process_name: Optional process name for consistency with other integrations
            
        Returns:
            str or None: The file path if available, None otherwise
        """
        if self.working_port:
            variables = self.get_vars(self.working_port)
            if variables:
                filepath = variables.get('filepath', '')
                if filepath:
                    logger.debug(f"Retrieved filepath from MPC-QT: {filepath}")
                    return filepath
        
        # If working port didn't work, try all default ports
        for port in self.default_ports:
            if port == self.working_port:
                continue
            
            variables = self.get_vars(port)
            if variables:
                filepath = variables.get('filepath', '')
                if filepath:
                    logger.debug(f"Retrieved filepath from MPC-QT on port {port}: {filepath}")
                    self.working_port = port  # Remember working port
                    return filepath
        
        return None