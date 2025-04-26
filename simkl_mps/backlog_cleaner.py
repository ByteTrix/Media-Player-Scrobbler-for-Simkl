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