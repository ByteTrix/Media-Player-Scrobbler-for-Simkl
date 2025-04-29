import json
import os
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "simkl-mps" # Define app name for config directory

# Default user subdirectory - this can be customized
DEFAULT_USER_SUBDIR = "kavinthangavel"  
USER_SUBDIR = DEFAULT_USER_SUBDIR  # Use default initially

# Initialize settings directory paths
def initialize_paths(custom_subdir=None):
    """Initialize or update app paths with optional custom subdirectory"""
    global USER_SUBDIR, SETTINGS_DIR, SETTINGS_FILE, APP_DATA_DIR
    
    # Update USER_SUBDIR if custom_subdir is provided
    if custom_subdir:
        USER_SUBDIR = custom_subdir
    
    # Set up the various directories and files
    APP_DATA_DIR = Path.home() / USER_SUBDIR / APP_NAME
    SETTINGS_DIR = APP_DATA_DIR  # Keep settings in the same directory
    SETTINGS_FILE = SETTINGS_DIR / "settings.json"
    
    return APP_DATA_DIR

# Initialize with default paths
APP_DATA_DIR = initialize_paths()

# Default settings
DEFAULT_THRESHOLD = 80
DEFAULT_SETTINGS = {
    "watch_completion_threshold": DEFAULT_THRESHOLD,
    "user_subdir": DEFAULT_USER_SUBDIR,
    "auto_sync_interval": 120  # Auto sync backlog every 2 minutes by default
}

def load_settings():
    """Loads settings from the JSON file in the user config directory."""
    if not SETTINGS_FILE.exists():
        log.info(f"Settings file not found at {SETTINGS_FILE}. Using defaults.")
        # Ensure the directory exists before potentially saving defaults
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error(f"Could not create settings directory {SETTINGS_DIR}: {e}")
            # Return defaults without attempting to save if dir creation fails
            return DEFAULT_SETTINGS.copy()
        # Save default settings on first load if file doesn't exist
        save_settings(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            
            # Ensure all default settings exist, otherwise add them
            settings_updated = False
            for key, default_value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = default_value
                    settings_updated = True
            
            # Validate threshold value
            try:
                current_threshold = int(settings['watch_completion_threshold'])
                if not (1 <= current_threshold <= 100):
                    log.warning(f"Invalid watch_completion_threshold '{current_threshold}' in {SETTINGS_FILE}. Resetting to {DEFAULT_THRESHOLD}.")
                    settings['watch_completion_threshold'] = DEFAULT_THRESHOLD
                    settings_updated = True
            except (ValueError, TypeError):
                 log.warning(f"Non-integer watch_completion_threshold '{settings.get('watch_completion_threshold')}' in {SETTINGS_FILE}. Resetting to {DEFAULT_THRESHOLD}.")
                 settings['watch_completion_threshold'] = DEFAULT_THRESHOLD
                 settings_updated = True

            # Save the file only if defaults were added or invalid values corrected
            if settings_updated:
                save_settings(settings)
                
            return settings
    except (json.JSONDecodeError, IOError) as e:
        log.error(f"Error loading settings from {SETTINGS_FILE}: {e}. Using defaults.")
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        log.error(f"An unexpected error occurred while loading settings: {e}. Using defaults.")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings_dict):
    """Saves the provided settings dictionary to the JSON file in the user config directory."""
    try:
        # Ensure parent directory exists
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_dict, f, indent=4)
        log.info(f"Settings saved successfully to {SETTINGS_FILE}")
    except OSError as e:
         log.error(f"Could not create or write to settings directory/file {SETTINGS_FILE}: {e}")
    except IOError as e:
        log.error(f"Error saving settings to {SETTINGS_FILE}: {e}")
    except Exception as e:
        log.error(f"An unexpected error occurred while saving settings: {e}")


def get_setting(key, default=None):
    """Gets a specific setting value."""
    settings = load_settings() # load_settings now handles validation/defaults
    return settings.get(key, default)


def set_setting(key, value):
    """Sets a specific setting value and saves it."""
    # Validate certain settings before saving
    if key == 'watch_completion_threshold':
        try:
            int_value = int(value)
            if not (1 <= int_value <= 100):
                log.error(f"Attempted to set invalid watch_completion_threshold: {value}. Must be between 1 and 100.")
                return # Do not save invalid value
            value = int_value # Ensure it's saved as an integer
        except (ValueError, TypeError):
             log.error(f"Attempted to set non-integer watch_completion_threshold: {value}.")
             return # Do not save invalid value
    
    if key == 'user_subdir' and value != get_setting('user_subdir'):
        log.info(f"Updating user subdirectory from '{get_setting('user_subdir')}' to '{value}'")
        # Reinitialize paths with the new user_subdir
        initialize_paths(value)
        
        # Now we need to reload settings to get all the settings from the new location
        settings = load_settings()  # This will now load from (or create at) the new location
        settings[key] = value # set the new value
        save_settings(settings)     # This will save to the new location
        
        log.info(f"Updated app data directory to: {APP_DATA_DIR}")
        return

def get_app_data_dir():
    """Returns the current app data directory path."""
    return APP_DATA_DIR