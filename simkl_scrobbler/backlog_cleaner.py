"""
Backlog cleaner module for SIMKL Scrobbler.
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

    def __init__(self, app_data_dir: pathlib.Path, backlog_file="backlog.json", threshold_days=None):
        self.app_data_dir = app_data_dir
        self.backlog_file = self.app_data_dir / backlog_file # Use app_data_dir
        self.backlog = self._load_backlog()
        self.threshold_days = threshold_days  # New parameter for old entries threshold

    def _load_backlog(self):
        """Load the backlog from file"""
        if os.path.exists(self.backlog_file):
            try:
                # Specify encoding for reading JSON
                with open(self.backlog_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:  # Only try to parse if file is not empty
                        f.seek(0) # Reset file pointer before reading again for JSON parsing
                        return json.load(f)
                    else:
                        logger.debug("Backlog file exists but is empty. Starting with empty backlog.") # Changed to debug
                        return []
            except json.JSONDecodeError as e:
                logger.error(f"Error loading backlog: {e}")
                logger.info("Creating new empty backlog due to loading error")
                # Set backlog to empty list and then save it
                self.backlog = []
                self._save_backlog() # Call without arguments
                return [] # Return the newly created empty backlog
            except Exception as e:
                logger.error(f"Error loading backlog: {e}")
        return []

    def _save_backlog(self):
        """Save the backlog to file"""
        try:
            # Specify encoding for writing JSON
            with open(self.backlog_file, 'w', encoding='utf-8') as f:
                json.dump(self.backlog, f, indent=4) # Add indent for readability
        except Exception as e:
            logger.error(f"Error saving backlog: {e}")

    def add(self, simkl_id, title):
        """Add a movie to the backlog"""
        entry = {
            "simkl_id": simkl_id,
            "title": title,
            "timestamp": datetime.now().isoformat()
        }

        # Don't add duplicates
        for item in self.backlog:
            if item.get("simkl_id") == simkl_id:
                return

        self.backlog.append(entry)
        self._save_backlog()
        logger.info(f"Added '{title}' to backlog for future syncing")

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