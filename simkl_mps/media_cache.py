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
    """Cache for storing identified media (movies, TV shows, anime) to avoid repeated searches"""

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

    def get(self, key):
        """
        Get media info from cache
        
        Args:
            key: The key to look up (lowercase title, filename, or path)
        
        Returns:
            dict: Media info including type, ID, and episode details if applicable
        """
        return self.cache.get(key.lower())

    def set(self, key, media_info):
        """
        Store media info in cache
        
        Args:
            key: The key to store under (title, filename, or path)
            media_info: Dict with media details including 'type' ('movie', 'show', 'anime')
                        and applicable fields like 'simkl_id', 'season', 'episode'
        """
        self.cache[key.lower()] = media_info
        self._save_cache()
        
    def update(self, key, new_info):
        """
        Update existing media info in cache, preserving non-overwritten fields
        
        Args:
            key: The key to update (title, filename, or path)
            new_info: Dict with new/updated media details to merge
        """
        existing = self.get(key)
        if existing:
            # Merge new info with existing info, keeping existing values not in new_info
            existing.update(new_info)
            self.set(key, existing)
        else:
            # If no existing entry, just create one
            self.set(key, new_info)

    def remove(self, key):
        """
        Remove media info from cache
        
        Args:
            key: The key to remove
        
        Returns:
            bool: True if key was found and removed, False otherwise
        """
        if key.lower() in self.cache:
            del self.cache[key.lower()]
            self._save_cache()
            return True
        return False

    def get_by_simkl_id(self, simkl_id):
        """
        Find cached media by Simkl ID
        
        Args:
            simkl_id: The Simkl ID to search for
        
        Returns:
            tuple: (key, media_info) if found, otherwise (None, None)
        """
        simkl_id = str(simkl_id)  # Convert to string for comparison
        for key, info in self.cache.items():
            if info.get('simkl_id') == simkl_id or str(info.get('simkl_id')) == simkl_id:
                return key, info
        return None, None

    def get_all(self):
        """Get all cached media info"""
        return self.cache
        
    def get_by_type(self, media_type):
        """
        Get all cached entries of a specific media type
        
        Args:
            media_type: Type to filter by ('movie', 'show', 'anime')
            
        Returns:
            dict: Filtered cache entries {key: media_info}
        """
        return {key: info for key, info in self.cache.items() 
                if info.get('type') == media_type}