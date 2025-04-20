"""
Media Tracker module for SIMKL Scrobbler.
This is the main coordinator module that brings together all components.
"""

import os
import sys
import time
import logging
import pathlib
import platform
from datetime import datetime

# Import our modular components
from simkl_scrobbler.window_detection import get_active_window_info, get_all_windows_info
from simkl_scrobbler.movie_scrobbler import MovieScrobbler
from simkl_scrobbler.monitor import Monitor
from simkl_scrobbler.media_cache import MediaCache
from simkl_scrobbler.backlog_cleaner import BacklogCleaner
from simkl_scrobbler.simkl_api import search_movie, get_movie_details, mark_as_watched, is_internet_connected

# Configure module logging
logger = logging.getLogger(__name__)

# Platform detection
PLATFORM = platform.system().lower()

class MediaTracker:
    """
    Main media tracker class that coordinates all components.
    This is a simplified version that uses our modular structure.
    """

    def __init__(self, app_data_dir, client_id=None, access_token=None, testing_mode=False):
        self.app_data_dir = app_data_dir 
        self.client_id = client_id
        self.access_token = access_token
        self.testing_mode = testing_mode
        
        # Create monitor with auto-search callback
        self.monitor = Monitor(
            app_data_dir=self.app_data_dir,
            client_id=self.client_id,
            access_token=self.access_token,
            testing_mode=self.testing_mode
        )
        # Set up the search callback
        self.monitor.set_search_callback(self.search_and_cache_movie)

    def start(self):
        """Start the media tracker"""
        logger.info("Starting Media Tracker")
        return self.monitor.start()

    def stop(self):
        """Stop the media tracker"""
        logger.info("Stopping Media Tracker")
        return self.monitor.stop()

    def set_credentials(self, client_id, access_token):
        """Set the API credentials"""
        self.client_id = client_id
        self.access_token = access_token
        self.monitor.set_credentials(client_id, access_token)

    def search_and_cache_movie(self, title):
        """
        Search for a movie and cache the result.
        This is called by the monitor when it detects a new movie.
        """
        if not title or not self.client_id or not self.access_token:
            return None

        logger.info(f"Searching for movie: {title}")

        # Check if we're online first
        if not is_internet_connected():
            logger.warning("Cannot search for movie - no internet connection")
            return None

        try:
            # Search for the movie
            movie = search_movie(title, self.client_id, self.access_token)
            
            if not movie:
                logger.warning(f"No match found for '{title}'")
                return None

            # Extract movie details
            simkl_id = None
            movie_name = title  # Default to the original title if extraction fails
            
            # Try to extract from different response formats
            if 'movie' in movie and 'ids' in movie['movie']:
                ids = movie['movie']['ids']
                simkl_id = ids.get('simkl') or ids.get('simkl_id')
                movie_name = movie['movie'].get('title', title)
            elif 'ids' in movie:
                ids = movie['ids']
                simkl_id = ids.get('simkl') or ids.get('simkl_id')
                movie_name = movie.get('title', title)
                
            if not simkl_id:
                logger.warning(f"No Simkl ID found in search result for '{title}'")
                return None
                
            logger.info(f"Found match: '{movie_name}' (ID: {simkl_id})")
            
            # Get more details including runtime if available
            runtime = None
            try:
                details = get_movie_details(simkl_id, self.client_id, self.access_token)
                if details and 'runtime' in details:
                    runtime = details['runtime']
                    logger.info(f"Movie runtime: {runtime} minutes")
            except Exception as e:
                logger.error(f"Error getting movie details: {e}")
                # Continue without runtime
            
            # Cache the movie info
            self.monitor.cache_movie_info(title, simkl_id, movie_name, runtime)
            
            return {
                'simkl_id': simkl_id,
                'title': movie_name,
                'runtime': runtime
            }
            
        except Exception as e:
            logger.error(f"Error searching for movie '{title}': {e}")
            return None

    def process_backlog(self):
        """Process the backlog - delegates to scrobbler"""
        # Access the scrobbler's backlog processing via the monitor
        return self.monitor.scrobbler.process_backlog()