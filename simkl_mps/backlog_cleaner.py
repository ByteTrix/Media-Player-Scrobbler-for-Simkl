"""
Backlog cleaner module for Media Player Scrobbler for SIMKL.
Handles tracking of watched movies to sync when connection is restored.
"""

import os
import json
import logging
import pathlib
from datetime import datetime

# Configure module logging
logger = logging.getLogger(__name__)

class BacklogCleaner:
    """Manages a backlog of watched movies to sync when connection is restored"""

    def __init__(self, app_data_dir: pathlib.Path, backlog_file="backlog.json"):
        self.app_data_dir = app_data_dir
        self.backlog_file = self.app_data_dir / backlog_file # Use app_data_dir
        self.backlog = self._load_backlog()
        # threshold_days parameter removed as it was unused

    def _load_backlog(self):
        """Load the backlog from file, creating the file if it does not exist."""
        if not os.path.exists(self.app_data_dir):
            try:
                os.makedirs(self.app_data_dir, exist_ok=True)
                logger.info(f"Created app data directory: {self.app_data_dir}")
            except Exception as e:
                logger.error(f"Failed to create app data directory: {e}")
                return []
        if os.path.exists(self.backlog_file):
            try:
                with open(self.backlog_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        f.seek(0)
                        return json.load(f)
                    else:
                        logger.debug("Backlog file exists but is empty. Starting with empty backlog.")
                        return []
            except json.JSONDecodeError as e:
                logger.error(f"Error loading backlog: {e}")
                logger.info("Creating new empty backlog due to loading error")
                self.backlog = []
                self._save_backlog()
                return []
            except Exception as e:
                logger.error(f"Error loading backlog: {e}")
        else:
            # File does not exist, create it
            try:
                with open(self.backlog_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                logger.info(f"Created new backlog file: {self.backlog_file}")
            except Exception as e:
                logger.error(f"Failed to create backlog file: {e}")
            return []
        return []

    def _save_backlog(self):
        """Save the backlog to file"""
        try:
            # Specify encoding for writing JSON
            with open(self.backlog_file, 'w', encoding='utf-8') as f:
                json.dump(self.backlog, f, indent=4) # Add indent for readability
        except Exception as e:
            logger.error(f"Error saving backlog: {e}")

    def add(self, simkl_id, title, additional_data=None):
        """
        Add a media item to the backlog
        
        Args:
            simkl_id: The Simkl ID of the media 
            title: Title of the media
            additional_data: Dictionary with additional data (type, season, episode, etc.)
        """
        # Create the basic entry
        entry = {
            "simkl_id": simkl_id,
            "title": title,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add additional data if provided (type, season, episode, etc.)
        if additional_data and isinstance(additional_data, dict):
            for key, value in additional_data.items():
                if key not in entry:  # Don't overwrite existing keys
                    entry[key] = value
        
        # Convert backlog from list to dict if needed (for backward compatibility)
        if isinstance(self.backlog, list):
            new_backlog = {}
            for item in self.backlog:
                item_id = item.get("simkl_id")
                if item_id:
                    new_backlog[str(item_id)] = item
            self.backlog = new_backlog

        # Don't add duplicates - update existing entry
        if str(simkl_id) in self.backlog:
            # Update existing entry
            self.backlog[str(simkl_id)].update(entry)
            logger.debug(f"Updated backlog entry for '{title}' (ID: {simkl_id})")
        else:
            # Add new entry
            self.backlog[str(simkl_id)] = entry
            logger.info(f"Added '{title}' to backlog for future syncing")
            
        self._save_backlog()

    def get_pending(self):
        """Get all pending backlog entries"""
        return self.backlog

    def remove(self, simkl_id):
        """Remove an entry from the backlog"""
        self.backlog = [item for item in self.backlog if item.get("simkl_id") != simkl_id]
        self._save_backlog()

    def clear(self):
        """Clear the entire backlog"""
        self.backlog = []
        self._save_backlog()

    def process_backlog(self, client_id, access_token):
        """
        Process all items in the backlog.
        
        Args:
            client_id: The client ID for the SIMKL API
            access_token: The access token for the SIMKL API
            
        Returns:
            dict: Status of processing {'processed': count, 'attempted': total, 'failed': boolean}
        """
        if not self._load_backlog():
            logger.warning("No backlog to process or backlog file couldn't be loaded.")
            return {'processed': 0, 'attempted': 0, 'failed': False}
        
        from simkl_mps.simkl_api import add_to_history, search_movie, search_file
        
        success_count = 0
        failure_occurred = False
        total_attempted = len(self.backlog)
        
        if not total_attempted:
            return {'processed': 0, 'attempted': 0, 'failed': False}
        
        logger.info(f"Processing {total_attempted} backlog entries...")
        processed_ids = []
        
        for simkl_id, item_data in self.backlog.items():
            # Extract basic data
            title = item_data.get('title', 'Unknown')
            media_type = item_data.get('type', 'movie')  # Default to movie if not specified
            season = item_data.get('season')
            episode = item_data.get('episode')
            
            # Check if this is a temp/guessit ID that needs resolution
            is_temp_id = isinstance(simkl_id, str) and simkl_id.startswith("temp_")
            is_guessit_id = isinstance(simkl_id, str) and simkl_id.startswith("guessit_")

            if is_guessit_id:
                # Skip guessit items for now as filepath is not stored
                logger.warning(f"[Backlog] Skipping item '{title}' (ID: {simkl_id}). "
                               f"Processing guessit-based items requires 'original_filepath' "
                               f"to be stored in the backlog, which is not currently implemented.")
                failure_occurred = True # Mark as failure for this cycle
                continue

            if is_temp_id:
                resolved_id = None
                resolved_type = None
                logger.info(f"[Backlog] Resolving temporary ID for '{title}' using title search...")
                try:
                    # Try resolving using title search (primarily for movies added offline)
                    movie_result = search_movie(title, client_id, access_token)
                    if movie_result:
                        if 'movie' in movie_result and 'ids' in movie_result['movie']:
                            resolved_id = movie_result['movie']['ids'].get('simkl')
                            resolved_type = 'movie'
                        elif 'ids' in movie_result: # Direct ID structure
                            resolved_id = movie_result['ids'].get('simkl')
                            resolved_type = 'movie' # Assume movie for simple case
                except Exception as e:
                    logger.error(f"[Backlog] Error during title search for '{title}': {e}")

                # If resolution failed, skip and mark as failed
                if not resolved_id:
                    logger.warning(f"[Backlog] Could not resolve temporary ID for '{title}' using title search. Will retry later.")
                    failure_occurred = True
                    continue

                # Update for next step
                logger.info(f"[Backlog] Resolved '{title}' to Simkl ID {resolved_id} (Type: {resolved_type})")
                simkl_id = resolved_id
                media_type = resolved_type # Update media type based on resolution

            # --- Payload Construction and API Call ---
            # At this point, simkl_id should be a valid integer ID
            try:
                # Ensure simkl_id is an integer before proceeding
                try:
                    simkl_id_int = int(simkl_id)
                except (ValueError, TypeError):
                     logger.error(f"[Backlog] Invalid Simkl ID '{simkl_id}' for item '{title}'. Skipping.")
                     failure_occurred = True
                     continue

                # Build appropriate payload based on media type
                payload = None
                log_item_desc = f"media '{title}' (ID: {simkl_id_int})" # Default description

                if media_type == 'movie':
                    payload = {"movies": [{"ids": {"simkl": simkl_id_int}}]}
                    log_item_desc = f"movie '{title}' (ID: {simkl_id_int})"
                elif media_type == 'show':
                    # TV Shows require season and episode
                    if season is not None and episode is not None:
                        try:
                            payload = {
                                "shows": [{
                                    "ids": {"simkl": simkl_id_int},
                                    "seasons": [{"number": int(season), "episodes": [{"number": int(episode)}]}]
                                }]
                            }
                            log_item_desc = f"show '{title}' S{season}E{episode} (ID: {simkl_id_int})"
                        except (ValueError, TypeError):
                             logger.warning(f"[Backlog] Invalid season/episode number for show '{title}' (S:{season}, E:{episode}). Skipping.")
                             failure_occurred = True
                             continue # Skip this item
                    else:
                        logger.warning(f"[Backlog] Missing season/episode for show '{title}'. Skipping.")
                        failure_occurred = True
                        continue # Skip this item
                elif media_type == 'anime':
                    # Anime requires episode number (no season in payload)
                    if episode is not None:
                        try:
                            payload = {
                                "shows": [{ # Still uses 'shows' key for anime
                                    "ids": {"simkl": simkl_id_int},
                                    "episodes": [{"number": int(episode)}]
                                }]
                            }
                            log_item_desc = f"anime '{title}' E{episode} (ID: {simkl_id_int})"
                        except (ValueError, TypeError):
                             logger.warning(f"[Backlog] Invalid episode number for anime '{title}' (E:{episode}). Skipping.")
                             failure_occurred = True
                             continue # Skip this item
                    else:
                        logger.warning(f"[Backlog] Missing episode for anime '{title}'. Skipping.")
                        failure_occurred = True
                        continue # Skip this item
                else:
                    # Unknown or unspecified type - try as movie as a fallback
                    logger.warning(f"[Backlog] Unknown or missing media type '{media_type}' for '{title}'. Treating as movie.")
                    payload = {"movies": [{"ids": {"simkl": simkl_id_int}}]}
                    log_item_desc = f"movie '{title}' (ID: {simkl_id_int}, treated as movie)"

                # If payload construction failed (e.g., missing info), skip API call
                if payload is None:
                    # Failure already logged and marked above
                    continue

                # Add to history with the appropriate payload
                logger.info(f"[Backlog] Syncing {log_item_desc}")
                result = add_to_history(payload, client_id, access_token)

                if result:
                    logger.info(f"[Backlog] Successfully synced {log_item_desc} to Simkl history.")
                    processed_ids.append(str(simkl_id)) # Use original key (string) for removal
                    success_count += 1
                else:
                    logger.warning(f"[Backlog] Failed to add {log_item_desc} to history via API. Will retry later.")
                    failure_occurred = True
            except Exception as e:
                logger.error(f"[Backlog] Unexpected error processing item '{title}' (ID: {simkl_id}): {e}", exc_info=True)
                failure_occurred = True
        
        # Remove successfully processed items from backlog
        for item_id in processed_ids:
            self.remove(item_id)
        
        logger.info(f"[Backlog] Processing completed: {success_count}/{total_attempted} items synced.")
        return {'processed': success_count, 'attempted': total_attempted, 'failed': failure_occurred}