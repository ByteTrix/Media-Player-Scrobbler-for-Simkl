"""
Media cache module for Media Player Scrobbler for SIMKL.
Handles caching of identified media to avoid repeated searches.
"""

import os
import json
import logging
import pathlib

logger = logging.getLogger(__name__)

class MediaCache:
    """Cache for storing identified media to avoid repeated searches"""

    def __init__(self, app_data_dir: pathlib.Path, cache_file="media_cache.json"):
        self.app_data_dir = app_data_dir
        self.cache_file = self.app_data_dir / cache_file # Use app_data_dir
        self.cache = self._load_cache()

    def _load_cache(self):
        """Load the cache from file"""
        if os.path.exists(self.cache_file):
            try:
                # Specify encoding for reading JSON
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding cache file {self.cache_file}: {e}")
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
        return {}

    def _save_cache(self):
        """Save the cache to file"""
        try:
            # Specify encoding for writing JSON
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=4) # Add indent for readability
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def get(self, title):
        """Get movie info from cache"""
        return self.cache.get(title.lower())

    def set(self, title, movie_info):
        """Store movie info in cache"""
        self.cache[title.lower()] = movie_info
        self._save_cache()

    def get_all(self):
        """Get all cached movie info"""
        return self.cache