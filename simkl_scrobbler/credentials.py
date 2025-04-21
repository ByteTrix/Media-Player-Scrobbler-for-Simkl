"""
Manages Simkl API credentials.

Client ID and Secret are injected during the build process.
Access Token is loaded from a .env file in the user's application data directory.
"""
import pathlib
import logging
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# --- Injected by build process ---
# These placeholders are replaced by the build workflow using secrets.
SIMKL_CLIENT_ID = "SIMKL_CLIENT_ID_PLACEHOLDER"
SIMKL_CLIENT_SECRET = "SIMKL_CLIENT_SECRET_PLACEHOLDER"
# --- End of injected values ---

# Determine the path for the .env file storing the access token
APP_NAME_FOR_PATH = "simkl-scrobbler"
USER_SUBDIR_FOR_PATH = "kavinthangavel"
try:
    # Prefer user-specific directory
    APP_DATA_DIR_FOR_PATH = pathlib.Path.home() / USER_SUBDIR_FOR_PATH / APP_NAME_FOR_PATH
    APP_DATA_DIR_FOR_PATH.mkdir(parents=True, exist_ok=True)
    ENV_FILE_PATH = APP_DATA_DIR_FOR_PATH / ".simkl_scrobbler.env"
    logger.debug(f"Using env file path: {ENV_FILE_PATH}")
except Exception as e:
    # Fallback to current directory if home cannot be determined
    logger.warning(f"Could not determine home directory ({e}), using fallback env path.")
    ENV_FILE_PATH = pathlib.Path(".simkl_scrobbler.env")

# Load Access Token ONLY from the specific .env file
SIMKL_ACCESS_TOKEN = None
if ENV_FILE_PATH.exists():
    logger.debug(f"Loading access token from {ENV_FILE_PATH}")
    config = dotenv_values(ENV_FILE_PATH)
    SIMKL_ACCESS_TOKEN = config.get("SIMKL_ACCESS_TOKEN")
    if not SIMKL_ACCESS_TOKEN:
        logger.warning(f"Found env file at {ENV_FILE_PATH}, but SIMKL_ACCESS_TOKEN key is missing or empty.")
else:
    logger.debug(f"Env file not found at {ENV_FILE_PATH}")


def get_credentials():
    """
    Retrieves the Simkl API credentials.

    Returns:
        dict: A dictionary containing 'client_id', 'client_secret',
              and 'access_token'. Values might be None if not configured
              or if the build process failed.
    """
    client_id = SIMKL_CLIENT_ID if SIMKL_CLIENT_ID != "SIMKL_CLIENT_ID_PLACEHOLDER" else None
    client_secret = SIMKL_CLIENT_SECRET if SIMKL_CLIENT_SECRET != "SIMKL_CLIENT_SECRET_PLACEHOLDER" else None
    access_token = SIMKL_ACCESS_TOKEN # Loaded at module level

    # Log a warning if the build injection seems to have failed
    if not client_id or not client_secret:
         logger.warning("Client ID or Secret appears missing. Build injection might have failed.")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
    }

def get_env_file_path():
    """
    Returns the calculated path to the .env file used for the access token.

    Returns:
        pathlib.Path: The path object for the .env file.
    """
    return ENV_FILE_PATH