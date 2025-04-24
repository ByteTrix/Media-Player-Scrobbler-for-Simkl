"""
Infuse integration module for Media Player Scrobbler for SIMKL.
Provides functionality to interact with Infuse's RESTful API on Apple platforms.
"""

import logging
import json
import platform
import requests
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

# Setup module logger
logger = logging.getLogger(__name__)

class InfuseIntegration:
    """
    Class for interacting with Infuse's RESTful API on Apple platforms.
    Used to get playback position and duration for more accurate scrobbling.
    
    Infuse needs to have Web Access enabled in its settings for this to work.
    """
    
    def __init__(self):
        self.name = 'infuse'
        self.platform = platform.system().lower()
        self.last_successful_config = None
        self.session = requests.Session()
        self.host = "127.0.0.1"  # Default host
        self.default_ports = [5047, 52520, 8777]  # Common Infuse ports
        self.current_port = None
        self.last_check_time = 0
        self.check_interval = 5  # Seconds to wait before trying different ports
    
    def get_position_duration(self, process_name=None):
        """
        Get current playback position and duration from Infuse.
        
        Args:
            process_name: Optional process name for debugging
            
        Returns:
            tuple: (position, duration) in seconds, or (None, None) if unavailable
        """
        # Check if we should try a new connection
        current_time = time.time()
        if current_time - self.last_check_time > self.check_interval:
            self.last_check_time = current_time
            self.current_port = None  # Reset port so we try again
        
        # If we have a successful config from a previous call, try it first
        if self.last_successful_config:
            port = self.last_successful_config.get("port")
            position, duration = self._try_infuse_connection(port)
            if position is not None and duration is not None:
                return position, duration
        
        # Try all default ports
        for port in self.default_ports:
            position, duration = self._try_infuse_connection(port)
            if position is not None and duration is not None:
                return position, duration
        
        # If we reach here, we couldn't connect to Infuse
        return None, None
    
    def _try_infuse_connection(self, port):
        """
        Try to connect to Infuse with the given port.
        
        Args:
            port: Port number to connect to
            
        Returns:
            tuple: (position, duration) in seconds, or (None, None) if unavailable
        """
        if self.current_port == port:
            # We already tried this port recently and it didn't work
            return None, None
        
        status_url = f"http://{self.host}:{port}/api/v1/player/status"
        
        try:
            # Try to connect with timeout
            response = self.session.get(status_url, timeout=1.0)
            response.raise_for_status()
            data = response.json()
            
            # Extract playback information
            if data.get('status') == 'playing' and 'currentTime' in data and 'duration' in data:
                position = data.get('currentTime')
                duration = data.get('duration')
                
                # Get additional info for logging
                title = data.get('title', 'Unknown title')
                
                logger.info(f"Successfully connected to Infuse on port {port}")
                logger.debug(f"Infuse is playing: {title}")
                logger.debug(f"Retrieved position data from Infuse: position={position}s, duration={duration}s")
                
                # Save successful config for future attempts
                self.last_successful_config = {"port": port}
                self.current_port = port
                
                # Validate data
                if isinstance(position, (int, float)) and isinstance(duration, (int, float)) and duration > 0 and position >= 0:
                    position = min(position, duration)  # Ensure position doesn't exceed duration
                    return round(position, 2), round(duration, 2)
            
            logger.debug(f"Connected to Infuse on port {port} but no valid playback data")
        except requests.exceptions.RequestException as e:
            logger.debug(f"Could not connect to Infuse on port {port}: {str(e)}")
        except Exception as e:
            logger.debug(f"Error processing Infuse data: {e}")
        
        # Update current port to avoid retrying immediately
        self.current_port = port
        return None, None
    
    def get_current_filepath(self):
        """
        Get the filepath of the currently playing file in Infuse.
        
        Returns:
            str: Filepath of the current media, or None if unavailable
        """
        if not self.last_successful_config:
            # Try to get position/duration first to establish a connection
            self.get_position_duration()
            if not self.last_successful_config:
                return None
        
        port = self.last_successful_config.get("port")
        status_url = f"http://{self.host}:{port}/api/v1/player/status"
        
        try:
            # Get current status data
            response = self.session.get(status_url, timeout=1.0)
            response.raise_for_status()
            status_data = response.json()
            
            # Extract filepath or URL information
            if status_data.get('status') == 'playing' and 'url' in status_data:
                media_url = status_data.get('url')
                # Convert URL to path if possible
                if media_url.startswith('file://'):
                    parsed_url = urlparse(media_url)
                    file_path = unquote(parsed_url.path)
                    return file_path
                return media_url
            
            logger.debug("No valid media URL found in Infuse status")
        except Exception as e:
            logger.debug(f"Error getting current filepath from Infuse: {e}")
        
        return None