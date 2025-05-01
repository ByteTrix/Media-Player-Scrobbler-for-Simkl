"""
Manages Simkl API credentials.

Client ID and Secret are injected during the build process.
Access Token is loaded from a .env file in the user's application data directory.
"""
import pathlib
import logging
import os
from dotenv import dotenv_values, load_dotenv

logger = logging.getLogger(__name__)


# --- Injected by build process ---
# These placeholders are replaced by the build workflow using secrets.
CLIENT_ID_PLACEHOLDER = "SIMKL_CLIENT_ID_PLACEHOLDER"
CLIENT_SECRET_PLACEHOLDER = "SIMKL_CLIENT_SECRET_PLACEHOLDER"
# --- End of injected values ---

SIMKL_CLIENT_ID = CLIENT_ID_PLACEHOLDER
SIMKL_CLIENT_SECRET = CLIENT_SECRET_PLACEHOLDER

SIMKL_CLIENT_ID="063e363a1596eb693066cf3b9848be8d2c4a6d9ef300666c9f19ef5980312b27"
SIMKL_CLIENT_SECRET="1e2781d773564774c6788bf64b871374b2cee2b31eaed361488821ffc7c5bba9"


APP_NAME_FOR_PATH = "simkl-mps"
USER_SUBDIR_FOR_PATH = "kavinthangavel"
try:

    APP_DATA_DIR_FOR_PATH = pathlib.Path.home() / USER_SUBDIR_FOR_PATH / APP_NAME_FOR_PATH
    APP_DATA_DIR_FOR_PATH.mkdir(parents=True, exist_ok=True)
    ENV_FILE_PATH = APP_DATA_DIR_FOR_PATH / ".simkl_mps.env"
    logger.debug(f"Using env file path: {ENV_FILE_PATH}")
except Exception as e:

    logger.warning(f"Could not determine home directory ({e}), using fallback env path.")
    ENV_FILE_PATH = pathlib.Path(".simkl_mps.env")


DEV_CREDS_PATH = pathlib.Path(".env")


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

    Client ID/Secret are read from module-level variables (injected at build).
    Access Token and User ID are read directly from the .env file *each time* this function
    is called to ensure the latest values are used.

    Returns:
        dict: A dictionary containing 'client_id', 'client_secret',
              'access_token', and 'user_id'. Values might be None if not configured
              or if the build/init process failed.
    """

    client_id = SIMKL_CLIENT_ID
    client_secret = SIMKL_CLIENT_SECRET
    
    if not client_id or not client_secret:
        logger.debug("Build-injected credentials not found, trying development sources...")
        
        client_id = os.environ.get("SIMKL_CLIENT_ID")
        client_secret = os.environ.get("SIMKL_CLIENT_SECRET")
        
        if (not client_id or not client_secret) and DEV_CREDS_PATH.exists():
            logger.debug(f"Loading development credentials from {DEV_CREDS_PATH}")
            dev_config = dotenv_values(DEV_CREDS_PATH)
            client_id = client_id or dev_config.get("SIMKL_CLIENT_ID")
            client_secret = client_secret or dev_config.get("SIMKL_CLIENT_SECRET")

 
    access_token = None
    user_id = None
    env_file_path = get_env_file_path() 
    if env_file_path.exists():
        logger.debug(f"Reading credentials from {env_file_path} inside get_credentials()")
        config = dotenv_values(env_file_path)
        access_token = config.get("SIMKL_ACCESS_TOKEN")
        user_id = config.get("SIMKL_USER_ID")
        
        if user_id:
            logger.debug(f"Found user ID in env file: {user_id}")
        else:
            logger.debug("User ID not found in env file")
            
        if not access_token:
             logger.warning(f"Found env file at {env_file_path}, but SIMKL_ACCESS_TOKEN key is missing or empty.")
    else:
         logger.debug(f"Env file not found at {env_file_path} inside get_credentials()")

    if not client_id or not client_secret:
         logger.warning("Client ID or Secret not found. For local development, create a dev_credentials.env file with SIMKL_CLIENT_ID and SIMKL_CLIENT_SECRET.")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
        "user_id": user_id
    }

def get_env_file_path():
    """
    Returns the calculated path to the .env file used for the access token.

    Returns:
        pathlib.Path: The path object for the .env file.
    """
    return ENV_FILE_PATH