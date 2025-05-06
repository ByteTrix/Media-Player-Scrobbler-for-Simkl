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
        """Ensure the watch history viewer files exist in the user's app data directory, always copying from the bundled source."""
        import shutil
        user_dir = pathlib.Path.home() / "kavinthangavel" / "simkl-mps" / "watch-history-viewer"
        source_dir = self._get_source_dir()
        # Always copy all files from source_dir to user_dir, overwriting if needed
        if not user_dir.exists():
            user_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            dest = user_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        logger.info(f"Ensured watch-history-viewer is up-to-date in user directory: {user_dir}")

    def _get_source_dir(self):
        """Find the source directory for the watch history viewer files (cross-platform, bundled in temp when frozen)."""
        import sys
        from pathlib import Path
        if getattr(sys, 'frozen', False):
            # PyInstaller bundle: _MEIPASS points to the temp extraction dir
            # The folder is bundled as simkl_mps/watch-history-viewer
            return Path(sys._MEIPASS) / "simkl_mps" / "watch-history-viewer"
        else:
            # Development: use the source folder
            return Path(__file__).parent / "watch-history-viewer"

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
        """Add a new entry to watch history, or update existing show entries with new episodes"""
        
        # Check if we already have this item in the history
        existing_entry = None
        existing_entry_index = -1

        # Find existing entry by simkl_id regardless of type
        # This ensures we always update existing shows rather than creating new entries
        for i, entry in enumerate(self.history):
            if entry.get("simkl_id") == media_item.get("simkl_id"):
                existing_entry = entry
                existing_entry_index = i
                break

        # --- Handle TV Shows/Anime ---
        if existing_entry and media_item.get("type") in ["tv", "show", "anime"] and "episode" in media_item:
            episode_number = media_item.get("episode")

            # Always ensure season and episode are set at the top level with the latest watched
            if "season" in media_item:
                existing_entry["season"] = media_item.get("season")
            
            if "episode" in media_item:
                existing_entry["episode"] = media_item.get("episode")

            # Update basic metadata from the new media_item
            if "poster_url" in media_item and media_item.get("poster_url"): # Use poster_url
                existing_entry["poster_url"] = media_item.get("poster_url")
            if "year" in media_item and media_item.get("year"):
                existing_entry["year"] = media_item.get("year")
            if "overview" in media_item and media_item.get("overview"):
                existing_entry["overview"] = media_item.get("overview")
            if "runtime" in media_item and media_item.get("runtime"):
                existing_entry["runtime"] = media_item.get("runtime")
            if "ids" in media_item and media_item.get("ids"):
                existing_entry["ids"] = media_item.get("ids")
                # Ensure imdb_id is at the top level if present in ids (for consistency)
                if "imdb" in media_item.get("ids", {}):
                    existing_entry["imdb_id"] = media_item["ids"]["imdb"]

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
                logger.info(f"Added episode {episode_number} to existing show '{existing_entry['title']}' (ID: {existing_entry['simkl_id']})")

            # Update overall show watched_at and episode count
            existing_entry["watched_at"] = datetime.now().isoformat()
            existing_entry["episodes_watched"] = len(existing_entry.get("episodes", [])) # Recalculate count

            # Move the updated show entry to the top of the list (most recently watched)
            if existing_entry_index != -1:
                self.history.pop(existing_entry_index)
                self.history.insert(0, existing_entry)

        # --- Handle Movies ---
        elif existing_entry and media_item.get("type") == "movie":
            # Update watched_at timestamp and file info for the existing movie
            existing_entry["watched_at"] = datetime.now().isoformat()
            
            # Update metadata from new media_item
            if "poster_url" in media_item and media_item.get("poster_url"): # Use poster_url
                existing_entry["poster_url"] = media_item.get("poster_url")
            if "year" in media_item and media_item.get("year"):
                existing_entry["year"] = media_item.get("year")
            if "overview" in media_item and media_item.get("overview"):
                existing_entry["overview"] = media_item.get("overview")
            if "runtime" in media_item and media_item.get("runtime"):
                existing_entry["runtime"] = media_item.get("runtime")
            if "ids" in media_item and media_item.get("ids"):
                existing_entry["ids"] = media_item.get("ids")
                # Ensure imdb_id is at the top level if present in ids
                if "imdb" in media_item.get("ids", {}):
                    existing_entry["imdb_id"] = media_item["ids"]["imdb"]
                    
            # Update file path and metadata if provided
            if media_file_path:
                existing_entry["file_path"] = str(media_file_path)
                existing_entry.update(self._get_file_metadata(media_file_path))

            # Move the updated movie entry to the top of the list
            if existing_entry_index != -1:
                self.history.pop(existing_entry_index)
                self.history.insert(0, existing_entry)
                logger.info(f"Updated movie '{existing_entry['title']}' (ID: {existing_entry['simkl_id']})")

        # --- Handle New Entries (Movie or TV Show not found) ---
        elif not existing_entry:
            # Create new history entry
            history_entry = {
                "simkl_id": media_item.get("simkl_id"),
                "title": media_item.get("title", "Unknown Title"),
                "type": media_item.get("type", "movie"),
                "watched_at": datetime.now().isoformat(),
                "poster_url": media_item.get("poster_url", ""), # Use poster_url
                "year": media_item.get("year"),
                "runtime": media_item.get("runtime"),
                "overview": media_item.get("overview"),
                "ids": media_item.get("ids", {})
            }

            # Always add season/episode for TV shows
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

            # For TV shows/anime, also add episode information to the episodes list
            if history_entry["type"] in ["tv", "show", "anime"] and "episode" in media_item:
                history_entry["episodes_watched"] = 1
                history_entry["total_episodes"] = media_item.get("total_episodes")

                # Initialize episodes list with the first episode
                history_entry["episodes"] = [{
                    "number": media_item.get("episode"),
                    "title": media_item.get("episode_title", f"Episode {media_item.get('episode')}"),
                    "watched_at": datetime.now().isoformat()
                }]
                
                # Add file information to episode if available
                if media_file_path and "episodes" in history_entry:
                    history_entry["episodes"][0]["file_path"] = str(media_file_path)
                    history_entry["episodes"][0].update(self._get_file_metadata(media_file_path))
                
                logger.info(f"Created new show entry for '{history_entry['title']}' (ID: {history_entry['simkl_id']}) with episode {media_item.get('episode')}")
            else:
                logger.info(f"Created new movie entry for '{history_entry['title']}' (ID: {history_entry['simkl_id']})")
            
            # Add the new entry to the beginning of the list
            self.history.insert(0, history_entry)

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