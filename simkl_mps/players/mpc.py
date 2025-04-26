"""
Media Player Classic (MPC-HC/BE) integration for Media Player Scrobbler for SIMKL.
Allows getting position and duration data from MPC-HC and MPC-BE.
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

class MPCIntegration:
    """Base class for MPC-HC/BE integration"""
    
    def __init__(self, base_url=None):
        """
        Initialize MPC integration.
        
        Args:
            base_url: Optional base URL for MPC web interface. If None, auto-detect will be used.
        """
        self.name = 'mpc'
        self.platform = platform.system().lower()
        self.default_ports = [13579, 13580, 13581, 13582]  # Common MPC ports
        
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

    def _auto_detect_url(self):
        """Auto-detect MPC web interface URL from registry"""
        if self.platform != 'windows':
            return "http://localhost:13579"  # Default port for non-Windows
            
        try:
            # Try to get port from registry
            port = self._read_registry_port()
            if port:
                logger.info(f"Found MPC port in registry: {port}")
                return f"http://localhost:{port}"
        except Exception as e:
            logger.debug(f"Could not read MPC port from registry: {e}")
            
        # Default to common ports
        logger.debug("Using default MPC ports for detection")
        return "http://localhost:13579"  # Will try other ports dynamically
        
    def _read_registry_port(self):
        """Read MPC web interface port from Windows registry"""
        try:
            # Try MPC-HC first
            hc_path = "Software\\MPC-HC\\MPC-HC\\Settings"
            hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, hc_path)
            port = winreg.QueryValueEx(hkey, "WebServerPort")[0]
            return port
        except FileNotFoundError:
            try:
                # Then try MPC-BE paths
                be_path1 = "Software\\MPC-BE\\WebServer"
                hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, be_path1)
                port = winreg.QueryValueEx(hkey, "Port")[0]
                return port
            except FileNotFoundError:
                try:
                    # Old versions of MPC-BE
                    be_path2 = "Software\\MPC-BE\\Settings"
                    hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, be_path2)
                    port = winreg.QueryValueEx(hkey, "WebServerPort")[0]
                    return port
                except FileNotFoundError:
                    return None
        except Exception as e:
            logger.debug(f"Error reading MPC port from registry: {e}")
            return None
            
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
        """Get variables from MPC web interface"""
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
        Get current position and duration from MPC player.
        
        Args:
            process_name: Process name (ignored, used for consistency with other integrations)
            
        Returns:
            tuple: (position_seconds, duration_seconds) or (None, None) if unavailable
        """
        # First try the working port if we have one
        if self.working_port:
            variables = self.get_vars(self.working_port)
            if variables and variables.get('duration', '0') != '0':
                position = int(variables.get('position', 0)) / 1000.0  # MPC reports in milliseconds
                duration = int(variables.get('duration', 0)) / 1000.0
                return position, duration
                
        # If no working port or it failed, try all default ports
        for port in self.default_ports:
            if port == self.working_port:
                continue  # Already tried this one
                
            variables = self.get_vars(port)
            if variables and variables.get('duration', '0') != '0':
                position = int(variables.get('position', 0)) / 1000.0  # MPC reports in milliseconds
                duration = int(variables.get('duration', 0)) / 1000.0
                logger.info(f"Successfully connected to MPC web interface on port {port}")
                self.working_port = port  # Remember this working port
                return position, duration
                
        return None, None  # Failed to get position/duration
        
    def is_paused(self):
        """
        Check if MPC playback is paused
        
        Returns:
            bool: True if paused, False if playing, None if unknown
        """
        # Try working port first
        if self.working_port:
            variables = self.get_vars(self.working_port)
            if variables:
                state = variables.get('state', '')
                return state == '2'  # MPC state 2 = paused
        
        # If no working port or it failed, try all default ports
        for port in self.default_ports:
            if port == self.working_port:
                continue  # Already tried this one
                
            variables = self.get_vars(port)
            if variables:
                state = variables.get('state', '')
                return state == '2'  # MPC state 2 = paused
                
        return None  # Couldn't determine pause state


# Convenience class for direct import
class MPCHCIntegration(MPCIntegration):
    """MPC-HC specific integration (same as base class)"""
    def __init__(self, base_url=None):
        super().__init__(base_url)
        self.name = 'mpc-hc'