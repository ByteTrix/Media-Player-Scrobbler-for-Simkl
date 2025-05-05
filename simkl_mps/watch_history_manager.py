"""
Watch history manager module for Media Player Scrobbler for SIMKL.
Tracks and manages local history of watched media.
"""

import os
import json
import logging
import pathlib
from datetime import datetime
import webbrowser
import shutil
import sys
import mimetypes

logger = logging.getLogger(__name__)

class WatchHistoryManager:
    """Manages a local history of watched movies and TV shows"""

    def __init__(self, app_data_dir: pathlib.Path, history_file="watch_history.json"):
        self.app_data_dir = app_data_dir
        self.history_file = self.app_data_dir / history_file
        self.history = self._load_history()
        if self.history is None:
            logger.error("Failed to load history, initializing to empty list.")
            self.history = []
        
        # Make sure we have the viewer files in the app_data_dir
        self._ensure_viewer_exists()
        
    def _load_history(self):
        """Load the history from file, creating the file if it does not exist."""
        if not os.path.exists(self.app_data_dir):
            try:
                os.makedirs(self.app_data_dir, exist_ok=True)
                logger.info(f"Created app data directory: {self.app_data_dir}")
            except Exception as e:
                logger.error(f"Failed to create app data directory: {e}")
                return []
                
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        f.seek(0)
                        return json.load(f)
                    else:
                        logger.debug("History file exists but is empty. Starting with empty history.")
                        return []
            except json.JSONDecodeError as e:
                logger.error(f"Error loading history: {e}")
                logger.info("Creating new empty history due to loading error")
                self.history = []
                self._save_history()
                return []
            except Exception as e:
                logger.error(f"Error loading history: {e}")
        else:
            # File does not exist, create it
            try:
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                logger.info(f"Created new history file: {self.history_file}")
            except Exception as e:
                logger.error(f"Failed to create history file: {e}")
            return []
        return []

    def _save_history(self):
        """Save the history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=4)
            return True # Indicate success
        except Exception as e:
            logger.error(f"Error saving history: {e}")
            return False # Indicate failure

    def add(self, media_info):
        """
        Add a media item to the history
        
        Args:
            media_info (dict): Dictionary containing media metadata
                Required keys: simkl_id, title
                Optional keys: poster_url, year, type, overview, runtime
        """
        if not media_info or not media_info.get('simkl_id') or not media_info.get('title'):
            logger.error(f"Invalid media info for history: {media_info}")
            return False
            
        # Add watched timestamp
        media_info['watched_at'] = datetime.now().isoformat()
        
        # Set default media type if not provided
        if 'type' not in media_info:
            media_info['type'] = 'movie'
            
        # Check if this item already exists in history
        existing_idx = None
        for idx, item in enumerate(self.history):
            if item.get('simkl_id') == media_info.get('simkl_id') and item.get('type') == media_info.get('type'):
                existing_idx = idx
                break
        
        if existing_idx is not None:
            # Update existing entry
            self.history[existing_idx] = media_info
            logger.info(f"Updated '{media_info['title']}' in watch history")
        else:
            # Add new entry
            self.history.append(media_info)
            logger.info(f"Added '{media_info['title']}' to watch history")
            
        self._save_history()
        return True

    def get_history(self, limit=None, offset=0, sort_by="watched_at", sort_order="desc"):
        """
        Get history entries
        
        Args:
            limit (int, optional): Maximum number of entries to return
            offset (int, optional): Starting offset for pagination
            sort_by (str, optional): Field to sort by (watched_at, title)
            sort_order (str, optional): Sort order (asc, desc)
            
        Returns:
            list: History entries
        """
        if not self.history:
            return []
            
        # Make a copy of the history to avoid modifying the original
        sorted_history = list(self.history)
        
        # Sort the history
        if (sort_by == "title"):
            sorted_history.sort(key=lambda x: x.get('title', '').lower(), 
                                reverse=(sort_order.lower() == "desc"))
        else:  # Default sort by watched_at
            sorted_history.sort(key=lambda x: x.get('watched_at', ''), 
                                reverse=(sort_order.lower() == "desc"))
        
        # Apply pagination if requested
        if limit:
            return sorted_history[offset:offset+limit]
        return sorted_history[offset:]

    def get_entry(self, simkl_id, media_type="movie"):
        """Get a specific entry from history"""
        for item in self.history:
            if item.get('simkl_id') == simkl_id and item.get('type', 'movie') == media_type:
                return item
        return None

    def remove(self, simkl_id, media_type="movie"):
        """Remove a specific entry from history"""
        initial_length = len(self.history)
        self.history = [item for item in self.history 
                        if not (item.get('simkl_id') == simkl_id and item.get('type', 'movie') == media_type)]
        
        if len(self.history) != initial_length:
            self._save_history()
            return True
        return False

    def clear(self):
        """Clear the entire history"""
        self.history = []
        self._save_history()
        return True
        
    def _ensure_viewer_exists(self):
        """
        Make sure the watch history viewer files exist in the app_data_dir
        Copies them from the installed package only if they don't exist or are outdated
        """
        try:
            # Target directory for the viewer files
            viewer_dir = self.app_data_dir / "watch-history-viewer"
            if not viewer_dir.exists():
                os.makedirs(viewer_dir, exist_ok=True)
            logger.info(f"Created watch history viewer directory: {viewer_dir}")
            
            # Find the source files
            source_dir = self._get_source_dir()
            
            if not source_dir or not source_dir.exists():
                logger.error(f"Could not find source directory for watch history viewer files.")
                return # Cannot proceed without source

            # Files we need to check/copy
            required_files = ["index.html", "style.css", "script.js"]
            needs_copy = False # Flag to track if any copy operation is needed

            # Check each required file and copy if missing or outdated
            for file_name in required_files:
                source_file = source_dir / file_name
                target_file = viewer_dir / file_name
                file_needs_update = False

                if not target_file.exists():
                    file_needs_update = True
                    logger.debug(f"File '{file_name}' missing in target directory.")
                elif source_file.exists() and os.path.getmtime(source_file) > os.path.getmtime(target_file):
                    file_needs_update = True
                    logger.debug(f"File '{file_name}' is outdated in target directory.")
                
                if file_needs_update:
                    if source_file.exists():
                        try:
                            shutil.copy2(source_file, target_file)
                            logger.debug(f"Copied '{file_name}' from {source_dir} to {viewer_dir}")
                            needs_copy = True # Mark that at least one copy happened
                        except Exception as copy_err:
                             logger.error(f"Failed to copy '{file_name}' from {source_file} to {target_file}: {copy_err}")
                    else:
                        logger.warning(f"Source file '{source_file}' not found for copying.")

            # Update asset files if needed (similar logic: copy if missing or newer)
            source_assets = source_dir / "assets"
            target_assets = viewer_dir / "assets"
            if source_assets.exists() and source_assets.is_dir():
                if not target_assets.exists():
                    try:
                        os.makedirs(target_assets, exist_ok=True)
                        logger.debug(f"Created assets directory: {target_assets}")
                    except Exception as mkdir_err:
                        logger.error(f"Failed to create assets directory {target_assets}: {mkdir_err}")
                        # Continue without assets if directory creation fails

                if target_assets.exists(): # Proceed only if target assets dir exists or was created
                    for asset_file in source_assets.iterdir():
                        if asset_file.is_file():
                            target_asset_file = target_assets / asset_file.name
                            asset_needs_update = False
                            if not target_asset_file.exists():
                                asset_needs_update = True
                            elif os.path.getmtime(asset_file) > os.path.getmtime(target_asset_file):
                                asset_needs_update = True

                            if asset_needs_update:
                                try:
                                    shutil.copy2(asset_file, target_asset_file)
                                    logger.debug(f"Copied asset '{asset_file.name}' to {target_assets}")
                                    needs_copy = True # Mark that at least one copy happened
                                except Exception as asset_copy_err:
                                    logger.error(f"Failed to copy asset '{asset_file.name}' to {target_asset_file}: {asset_copy_err}")
            
            if needs_copy:
                 logger.info("Watch history viewer files updated successfully.")
            else:
                 logger.debug("Watch history viewer files are up-to-date.") # More accurate log message
        except Exception as e:
            logger.error(f"Error ensuring watch history viewer exists: {e}", exc_info=True)
            
    def _get_source_dir(self):
        """Find the source directory for the watch history viewer files"""
        # Check if running from package or from source
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # If we're running from a frozen executable (PyInstaller) and _MEIPASS is available
            # _MEIPASS points to the temp directory where bundled files are extracted
            base_dir = pathlib.Path(sys._MEIPASS)
            logger.debug(f"Running frozen. Using base directory: {base_dir}")
            # The path inside the bundle depends on the spec file, common structure is:
            possible_dirs = [
                base_dir / "simkl_mps" / "watch-history-viewer", # If bundled preserving structure
                base_dir / "watch-history-viewer" # If bundled at top level
            ]
            # Check if the executable's directory also contains it (less common but possible)
            exe_dir = pathlib.Path(sys.executable).parent
            possible_dirs.extend([
                 exe_dir / "simkl_mps" / "watch-history-viewer",
                 exe_dir / "watch-history-viewer"
            ])
            # Check the possible directories for the frozen build
            for potential_dir in possible_dirs:
                logger.debug(f"Checking frozen path: {potential_dir}")
                if potential_dir.is_dir() and (potential_dir / "index.html").is_file():
                    logger.info(f"Found watch-history-viewer directory (frozen) at: {potential_dir}")
                    return potential_dir
            logger.warning(f"Could not find watch-history-viewer directory in standard frozen locations.")
            return None # Not found in expected frozen paths

        else:
            # If we're running from source (not frozen or _MEIPASS unavailable)
            try:
                # Get the absolute path to the directory containing this script (__file__)
                module_dir = pathlib.Path(__file__).resolve().parent
                source_viewer_dir = module_dir / "watch-history-viewer"
                logger.debug(f"Running from source. Checking relative path: {source_viewer_dir}")

                # Check the expected location relative to this file
                if source_viewer_dir.is_dir() and (source_viewer_dir / "index.html").is_file():
                    logger.info(f"Found watch-history-viewer directory (source) at: {source_viewer_dir}")
                    return source_viewer_dir
                else:
                    # Log specific failure reason
                    if not source_viewer_dir.is_dir():
                        logger.warning(f"Expected source directory not found or not a directory: {source_viewer_dir}")
                    elif not (source_viewer_dir / "index.html").is_file():
                        logger.warning(f"index.html not found in expected source directory: {source_viewer_dir}")
                    else:
                         logger.warning(f"Could not verify expected source directory: {source_viewer_dir}")
                    return None # Explicitly return None if not found

            except Exception as e:
                logger.error(f"Error determining source directory path: {e}", exc_info=True)
                return None # Return None on unexpected error

    def open_history(self):
        """Open the history page in the default web browser"""
        try:
            # Ensure the viewer exists
            self._ensure_viewer_exists()
            
            # Path to the viewer index.html
            viewer_path = self.app_data_dir / "watch-history-viewer" / "index.html"
            
            # If the viewer doesn't exist, show an error
            if not viewer_path.exists():
                logger.error(f"History viewer not found at: {viewer_path}")
                return False
                
            # Update the history data file next to the viewer
            self._update_history_data()
                
            # Open the viewer in the browser
            logger.info(f"Opening history viewer: {viewer_path}")
            webbrowser.open(f"file://{viewer_path}")
            return True
        except Exception as e:
            logger.error(f"Error opening history page: {e}")
            return False
            
    def _update_history_data(self):
        """Create or update the watch history data for the viewer"""
        try:
            # --- Reload history from file to ensure it's up-to-date ---
            self.history = self._load_history()
            logger.debug(f"Reloaded history from file. Found {len(self.history)} entries.")
            # -----------------------------------------------------------

            # Create the viewer directory if it doesn't exist
            viewer_dir = self.app_data_dir / "watch-history-viewer"
            if not viewer_dir.exists():
                os.makedirs(viewer_dir, exist_ok=True)

            # Log the paths we're using for debugging
            logger.info(f"App data directory: {self.app_data_dir}")
            logger.info(f"History file: {self.history_file}")
            logger.info(f"Viewer directory: {viewer_dir}")

            # Generate a data.js file that directly embeds the history data
            js_data_file = viewer_dir / "data.js"
            try:
                # Serialize the current history data to a JSON string
                # Use json.dumps to handle potential special characters correctly
                history_json_string = json.dumps(self.history, indent=None)  # No indent for JS variable
            except Exception as json_err:
                logger.error(f"Failed to serialize history data to JSON: {json_err}")
                history_json_string = "[]"  # Default to empty array on error

            with open(js_data_file, 'w', encoding='utf-8') as f:
                f.write(f"// Auto-generated by Media Player Scrobbler for SIMKL\n")
                f.write(f"// Last updated: {datetime.now().isoformat()}\n\n")

                # Write JavaScript that assigns the embedded data
                f.write(f"// This file contains the embedded watch history data\n")
                f.write(f"const HISTORY_DATA = {history_json_string};\n\n")

                # Add code to trigger processing once the main script is loaded
                # This assumes script.js defines processHistoryData or loadHistory
                f.write(f"""// Trigger history data processing once the main script likely loads\ndocument.addEventListener('DOMContentLoaded', () => {{\n    if (typeof processHistoryData === 'function') {{\n        console.log('Calling processHistoryData from data.js...');\n        processHistoryData();\n    }} else if (typeof loadHistory === 'function') {{\n        console.log('Calling loadHistory from data.js...');\n        loadHistory();\n    }} else {{\n        console.warn('Neither processHistoryData nor loadHistory found in main script.');\n    }}\n}});\n""")
            logger.info(f"Created data.js with embedded history data ({len(self.history)} entries)")

            # Add debugging information about the entries if available
            if self.history and len(self.history) > 0:
                for i, entry in enumerate(self.history[:3]):  # Log first 3 entries for debugging
                    title = entry.get('title', 'unknown')
                    simkl_id = entry.get('simkl_id', 'unknown')
                    watched_at = entry.get('watched_at', 'unknown')
                    logger.info(f"History entry {i+1}: '{title}' (ID: {simkl_id}, Watched: {watched_at})")
        except Exception as e:
            logger.error(f"Error updating history data: {e}", exc_info=True)
    
    def add_entry(self, media_item, media_file_path=None, watched_progress=100):
        """Add a new entry to watch history"""
        # Check if we already have this item in the history
        existing_entry = None
        existing_entry_index = -1

        # Find existing entry by simkl_id and type
        for i, entry in enumerate(self.history):
            if (entry.get("simkl_id") == media_item.get("simkl_id") and
                entry.get("type") == media_item.get("type")):
                existing_entry = entry
                existing_entry_index = i
                break

        # --- Handle TV Shows/Anime ---
        if existing_entry and media_item.get("type") in ["tv", "anime"] and "episode" in media_item:
            episode_number = media_item.get("episode")

            # Always ensure season and episode are set at the top level
            if "season" in media_item:
                existing_entry["season"] = media_item.get("season")
            
            if "episode" in media_item:
                existing_entry["episode"] = media_item.get("episode")

            # Ensure episodes list exists
            if "episodes" not in existing_entry:
                existing_entry["episodes"] = []

            # Check if this specific episode already exists
            episode_exists = False
            for ep in existing_entry.get("episodes", []):
                if ep.get("number") == episode_number:
                    # Update existing episode's watched_at and file info
                    ep["watched_at"] = datetime.now().isoformat()
                    if media_file_path:
                        ep["file_path"] = str(media_file_path)
                        ep.update(self._get_file_metadata(media_file_path))
                    episode_exists = True
                    break

            # Add new episode if it doesn't exist
            if not episode_exists:
                episode_data = {
                    "number": episode_number,
                    "title": media_item.get("episode_title", f"Episode {episode_number}"),
                    "watched_at": datetime.now().isoformat()
                }
                if media_file_path:
                    episode_data["file_path"] = str(media_file_path)
                    episode_data.update(self._get_file_metadata(media_file_path))
                existing_entry["episodes"].append(episode_data)

            # Update overall show watched_at and episode count
            existing_entry["watched_at"] = datetime.now().isoformat()
            existing_entry["episodes_watched"] = len(existing_entry.get("episodes", [])) # Recalculate count

            # Move the updated show entry to the top
            if existing_entry_index != -1:
                 self.history.pop(existing_entry_index)
                 self.history.insert(0, existing_entry)

        # --- Handle Movies ---
        elif existing_entry and media_item.get("type") == "movie":
            # Update watched_at timestamp and file info for the existing movie
            existing_entry["watched_at"] = datetime.now().isoformat()
            if media_file_path:
                existing_entry["file_path"] = str(media_file_path)
                existing_entry.update(self._get_file_metadata(media_file_path))
            # --- Removed metadata update loop for existing movies ---
            # Only watched_at and file info are updated now.

            # Move the updated movie entry to the top
            if existing_entry_index != -1:
                 self.history.pop(existing_entry_index)
                 self.history.insert(0, existing_entry)

        # --- Handle New Entries (Movie or TV Show not found) ---
        elif not existing_entry:
            # Create new history entry
            history_entry = {
                "simkl_id": media_item.get("simkl_id"),
                "title": media_item.get("title", "Unknown Title"),
                "type": media_item.get("type", "movie"),
                "watched_at": datetime.now().isoformat(),
                "poster_url": media_item.get("poster_url", ""),
                "year": media_item.get("year"),
                "runtime": media_item.get("runtime"),
                "overview": media_item.get("overview"),
                "ids": media_item.get("ids", {})
            }

            # Always add season/episode for TV shows regardless of existing episodes list
            if media_item.get("type") in ["tv", "show", "anime"]:
                if "season" in media_item:
                    history_entry["season"] = media_item.get("season")
                if "episode" in media_item:
                    history_entry["episode"] = media_item.get("episode")

            # Add file information if available
            if media_file_path:
                history_entry["file_path"] = str(media_file_path)
                history_entry.update(self._get_file_metadata(media_file_path))

            # Ensure imdb_id is at the top level if present in ids (for consistency)
            if "ids" in history_entry and "imdb" in history_entry["ids"]:
                 history_entry["imdb_id"] = history_entry["ids"]["imdb"]

            # --- Removed redundant season/episode copy block ---

            # For TV shows/anime, also add episode information to the episodes list
            if history_entry["type"] in ["tv", "anime"] and "episode" in media_item: # Check history_entry type
                history_entry["episodes_watched"] = 1
                history_entry["total_episodes"] = media_item.get("total_episodes") # Store total episodes if available

                # Initialize episodes list
                history_entry["episodes"] = [{
                    "number": media_item.get("episode"),
                    "title": media_item.get("episode_title", f"Episode {media_item.get('episode')}"),
                    "watched_at": datetime.now().isoformat()
                }]
                
                # Add file information to episode if available
                if media_file_path and "episodes" in history_entry:
                    history_entry["episodes"][0]["file_path"] = str(media_file_path)
                    history_entry["episodes"][0].update(self._get_file_metadata(media_file_path))
            
            # Add the new entry to the beginning of the list
            self.history.insert(0, history_entry)

            # --- ADD LOGGING ---
            # Remove excessive logging messages
            if media_item.get("type") in ["tv", "anime"]:
                 logger.debug(f"New TV/Anime item data - Season: {media_item.get('season')}, Episode: {media_item.get('episode')}")
            # --- END LOGGING ---

        # Limit history size if configured
        max_history = 500 # TODO: Make this configurable
        if max_history > 0 and len(self.history) > max_history:
            self.history = self.history[:max_history]
        
        return self._save_history()
    
    def _get_file_metadata(self, file_path):
        """Extract metadata from media file"""
        from simkl_mps.window_detection import get_file_metadata
        
        # Use the window_detection module to get file metadata
        return get_file_metadata(file_path)
        
    def _format_file_size(self, size_bytes):
        """Format file size to human-readable format"""
        if size_bytes is None:
            return "Unknown"
            
        # Define units and thresholds
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        if size_bytes == 0:
            return "0 B"
            
        # Calculate the appropriate unit
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024
            i += 1
            
        # Format with 2 decimal places if not bytes
        if i == 0:
            return f"{size_bytes} {units[i]}"
        else:
            return f"{size_bytes:.2f} {units[i]}"