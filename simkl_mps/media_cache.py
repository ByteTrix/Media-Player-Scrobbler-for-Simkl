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

    def _filter_media_info(self, raw_info: dict) -> dict:
        filtered = {}
        
        # Core fields extraction with fallbacks
        simkl_id = raw_info.get('simkl_id')
        if simkl_id is not None:
            try: # Ensure simkl_id is an int if possible
                filtered['simkl_id'] = int(simkl_id)
            except ValueError:
                filtered['simkl_id'] = simkl_id # Keep as string if not convertible

        movie_name = raw_info.get('movie_name') or raw_info.get('title')
        if movie_name:
            filtered['movie_name'] = movie_name

        poster_url = raw_info.get('poster_url') or raw_info.get('poster')
        if poster_url:
            filtered['poster_url'] = poster_url
            
        # Type and Year
        if 'type' in raw_info:
            filtered['type'] = raw_info['type']
        if 'year' in raw_info:
            filtered['year'] = raw_info['year']
            
        # IDs sub-dictionary
        filtered_ids = {}
        raw_ids_dict = raw_info.get('ids', {})
        
        final_simkl_id_for_ids = raw_ids_dict.get('simkl') or raw_ids_dict.get('simkl_id')
        if final_simkl_id_for_ids is None and 'simkl_id' in filtered:
             final_simkl_id_for_ids = filtered['simkl_id']
        
        if final_simkl_id_for_ids is not None:
            try:
                filtered_ids['simkl'] = int(final_simkl_id_for_ids)
            except ValueError:
                 filtered_ids['simkl'] = final_simkl_id_for_ids

        imdb_id_val = raw_ids_dict.get('imdb') or raw_info.get('imdb_id')
        if imdb_id_val:
            filtered_ids['imdb'] = imdb_id_val
            
        anilist_id_val = raw_ids_dict.get('anilist')
        if anilist_id_val:
            filtered_ids['anilist'] = anilist_id_val
            
        if filtered_ids:
            filtered['ids'] = filtered_ids

        # Other allowed top-level fields
        allowed_other_fields_can_be_null = ['overview']
        allowed_other_fields_must_have_value = [
            'source', 'duration_seconds', 
            'original_input', 'original_filepath',
            'season', 'episode' 
        ]
        for field in allowed_other_fields_can_be_null:
            if field in raw_info:
                filtered[field] = raw_info[field]

        for field in allowed_other_fields_must_have_value:
            if field in raw_info and raw_info[field] is not None:
                filtered[field] = raw_info[field]
        
        return filtered

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
        Store media info in cache after filtering
        
        Args:
            key: The key to store under (title, filename, or path)
            media_info: Dict with raw media details
        """
        filtered_info = self._filter_media_info(media_info)
        self.cache[key.lower()] = filtered_info
        self._save_cache()
        
    def update(self, key, new_info_raw):
        """
        Update existing media info in cache, ensuring the final result is filtered.
        
        Args:
            key: The key to update (title, filename, or path)
            new_info_raw: Dict with new/updated raw media details to merge
        """
        current_filtered = self.get(key) 
        
        if current_filtered:
            merged_info_for_filtering = current_filtered.copy()
            merged_info_for_filtering.update(new_info_raw)
            self.set(key, merged_info_for_filtering) # self.set will apply _filter_media_info
        else:
            self.set(key, new_info_raw) # self.set will apply _filter_media_info

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