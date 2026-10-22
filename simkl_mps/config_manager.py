import copy
import json
import os
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "simkl-mps" # Define app name for config directory

# Default user subdirectory
DEFAULT_USER_SUBDIR = "kavin"  # Updated from kavinthangavel
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
DEFAULT_MIN_REWATCH_WATCH_SECONDS = 180
DEFAULT_SETTINGS = {
    "watch_completion_threshold": DEFAULT_THRESHOLD,
    "user_subdir": DEFAULT_USER_SUBDIR,
    "auto_sync_interval": 120,  # Auto sync backlog every 2 minutes by default
    "disable_notifications": False,  # Show all notifications by default
    "allow_rewatch": False,
    "min_rewatch_watch_seconds": DEFAULT_MIN_REWATCH_WATCH_SECONDS,
    "enable_realtime_scrobble": True,
    "enable_playback_resume": True,
    "resume_start_tolerance_seconds": 30,
    "allow_dirs": [],
    "deny_dirs": []
}

# Last settings read/written OK; fallback so a corrupt read doesn't blank allow_dirs.
_last_good_settings = None

# Retry the rename: on Windows os.replace fails while another handle holds the file.
_REPLACE_RETRIES = 5
_REPLACE_DELAY_SECONDS = 0.1


def _backup_path():
    """Sibling backup file, e.g. settings.json.bak."""
    return SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".bak")


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _atomic_write_json(target_path, settings_dict):
    """Write JSON to target_path via a temp file + atomic rename. Returns True on success."""
    tmp_file = target_path.with_name(target_path.name + ".tmp")
    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(settings_dict, f, indent=4)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # some filesystems (network/virtual) don't support fsync
    except Exception as e:
        log.error(f"Could not write temp settings file {tmp_file}: {e}")
        _remove_quietly(tmp_file)
        return False

    last_error = None
    for _ in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp_file, target_path)  # atomic rename
            return True
        except OSError as e:
            last_error = e
            time.sleep(_REPLACE_DELAY_SECONDS)
    log.error(f"Could not replace {target_path} after {_REPLACE_RETRIES} tries: {last_error}")
    _remove_quietly(tmp_file)
    return False


def _load_backup():
    """Parse the backup file (must be a dict), or None if missing/unreadable/wrong shape."""
    try:
        with open(_backup_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _fallback_settings():
    """Settings after a read error: in-memory cache, then .bak, then defaults."""
    global _last_good_settings
    if _last_good_settings is not None:
        log.warning("Falling back to last known good settings after a settings read error.")
        return copy.deepcopy(_last_good_settings)

    backup = _load_backup()
    if backup is not None:
        log.warning("Recovered settings from backup after a settings read error.")
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(backup)
        _last_good_settings = copy.deepcopy(merged)
        return merged

    log.error("No settings backup available; using defaults (allow-list is disabled).")
    return copy.deepcopy(DEFAULT_SETTINGS)


def _sanitize_dir_list(value):
    """Ensure allow/deny dir settings are stored as a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if isinstance(item, str) and item.strip()]
    return []

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
            return copy.deepcopy(DEFAULT_SETTINGS)
        # Save default settings on first load if file doesn't exist
        save_settings(copy.deepcopy(DEFAULT_SETTINGS))
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        if not isinstance(settings, dict):
            raise ValueError("settings.json is not a JSON object")
    except (json.JSONDecodeError, IOError, OSError, ValueError) as e:
        log.error(f"Error loading settings from {SETTINGS_FILE}: {e}. Falling back.")
        return _fallback_settings()
    except Exception as e:
        log.error(f"An unexpected error occurred while loading settings: {e}. Falling back.")
        return _fallback_settings()

    # File is closed now; save AFTER this, never inside the read block (Windows can't
    # rename over a file that's still open -> WinError 5).
    global _last_good_settings

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

    # Validate min_rewatch_watch_seconds
    try:
        current_rewatch_secs = int(settings.get('min_rewatch_watch_seconds', DEFAULT_MIN_REWATCH_WATCH_SECONDS))
        if current_rewatch_secs < 0:
            settings['min_rewatch_watch_seconds'] = DEFAULT_MIN_REWATCH_WATCH_SECONDS
            settings_updated = True
    except (ValueError, TypeError):
        settings['min_rewatch_watch_seconds'] = DEFAULT_MIN_REWATCH_WATCH_SECONDS
        settings_updated = True

    # Sanitize allow/deny directory lists
    for key in ("allow_dirs", "deny_dirs"):
        sanitized = _sanitize_dir_list(settings.get(key))
        if settings.get(key) != sanitized:
            settings[key] = sanitized
            settings_updated = True

    _last_good_settings = copy.deepcopy(settings)

    # Persist enrichment/corrections only now that the read handle is closed.
    if settings_updated:
        save_settings(settings)

    return settings


def save_settings(settings_dict):
    """Save settings atomically (temp file + rename) plus a .bak. Returns True on success."""
    global _last_good_settings

    # Sanitize the allow/deny lists before writing and caching, so a partial or malformed
    # save can't later be handed back by _fallback_settings with the allow-list dropped.
    to_save = dict(settings_dict) if isinstance(settings_dict, dict) else settings_dict
    if isinstance(to_save, dict):
        for key in ("allow_dirs", "deny_dirs"):
            to_save[key] = _sanitize_dir_list(to_save.get(key))

    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.error(f"Could not create settings directory {SETTINGS_DIR}: {e}")
        return False

    if not _atomic_write_json(SETTINGS_FILE, to_save):
        return False

    _last_good_settings = copy.deepcopy(to_save)
    _atomic_write_json(_backup_path(), to_save)  # best effort; failure isn't fatal
    log.info(f"Settings saved successfully to {SETTINGS_FILE}")
    return True


def get_setting(key, default=None):
    """Gets a specific setting value."""
    settings = load_settings() # load_settings now handles validation/defaults
    return settings.get(key, default)


def set_setting(key, value):
    """Sets a specific setting value and saves it."""
    log.debug(f"ConfigManager: set_setting received key='{key}', value='{value}' (type: {type(value)})")
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

    if key == 'min_rewatch_watch_seconds':
        try:
            int_value = int(value)
            if int_value < 0:
                log.error(f"Attempted to set invalid min_rewatch_watch_seconds: {value}. Must be >= 0.")
                return
            value = int_value
        except (ValueError, TypeError):
            log.error(f"Attempted to set non-integer min_rewatch_watch_seconds: {value}.")
            return

    if key in ('allow_dirs', 'deny_dirs'):
        value = _sanitize_dir_list(value)
    
    log.debug(f"ConfigManager: set_setting proceeding for key='{key}' before user_subdir check.")
    if key == 'user_subdir' and value != get_setting('user_subdir'):
        log.info(f"Updating user subdirectory from '{get_setting('user_subdir')}' to '{value}'")
        # Reinitialize paths with the new user_subdir
        initialize_paths(value)
        
        # Now we need to reload settings to get all the settings from the new location
        settings = load_settings()  # This will now load from (or create at) the new location
        settings[key] = value # set the new value
        log.debug(f"ConfigManager: set_setting (user_subdir branch) - settings to save: {settings}")
        save_settings(settings)     # This will save to the new location
        
        log.info(f"Updated app data directory to: {APP_DATA_DIR}")
        return
    else:
        # This branch is taken if key is not 'user_subdir' OR if it is 'user_subdir' but the value is not changing.
        # For any key (including 'user_subdir' if its value isn't changing, though less critical there),
        # load current settings, update the specific key, and save.
        current_settings = load_settings()
        current_settings[key] = value
        log.debug(f"ConfigManager: set_setting (non-user_subdir or non-changing user_subdir) - settings to save: {current_settings}")
        save_settings(current_settings)
        log.info(f"ConfigManager: Setting for '{key}' updated and saved.")

def get_app_data_dir():
    """Returns the current app data directory path."""
    return APP_DATA_DIR