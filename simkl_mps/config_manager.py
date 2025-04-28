import json
import os
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "simkl-mps" # Define app name for config directory

# (Function get_user_config_dir removed as per user request)
# Determine the settings file path using the user-specified logic
USER_SUBDIR = "kavinthangavel" # User specified
SETTINGS_DIR = Path.home() / USER_SUBDIR / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
DEFAULT_THRESHOLD = 80


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
            return {"watch_completion_threshold": DEFAULT_THRESHOLD}
        # Save default settings on first load if file doesn't exist
        default_settings = {"watch_completion_threshold": DEFAULT_THRESHOLD}
        save_settings(default_settings)
        return default_settings
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            # Ensure the specific setting exists, otherwise add default
            threshold_updated = False
            if 'watch_completion_threshold' not in settings:
                settings['watch_completion_threshold'] = DEFAULT_THRESHOLD
                threshold_updated = True

            # Validate existing threshold value
            try:
                current_threshold = int(settings['watch_completion_threshold'])
                if not (1 <= current_threshold <= 100):
                    log.warning(f"Invalid watch_completion_threshold '{current_threshold}' in {SETTINGS_FILE}. Resetting to {DEFAULT_THRESHOLD}.")
                    settings['watch_completion_threshold'] = DEFAULT_THRESHOLD
                    threshold_updated = True
            except (ValueError, TypeError):
                 log.warning(f"Non-integer watch_completion_threshold '{settings.get('watch_completion_threshold')}' in {SETTINGS_FILE}. Resetting to {DEFAULT_THRESHOLD}.")
                 settings['watch_completion_threshold'] = DEFAULT_THRESHOLD
                 threshold_updated = True

            # Save the file only if the default was added or an invalid value was corrected
            if threshold_updated:
                save_settings(settings)
            return settings
    except (json.JSONDecodeError, IOError) as e:
        log.error(f"Error loading settings from {SETTINGS_FILE}: {e}. Using defaults.")
        return {"watch_completion_threshold": DEFAULT_THRESHOLD}
    except Exception as e:
        log.error(f"An unexpected error occurred while loading settings: {e}. Using defaults.")
        return {"watch_completion_threshold": DEFAULT_THRESHOLD}


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
    # Validate threshold value before saving
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

    settings = load_settings()
    settings[key] = value
    save_settings(settings)