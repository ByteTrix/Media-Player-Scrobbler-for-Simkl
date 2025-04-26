"""
Handles interactions with the Simkl API.

Provides functions for searching movies, marking them as watched,
retrieving details, and handling the OAuth device authentication flow.
"""
import requests
import time
import logging
import socket
import platform
import sys
try:
    from simkl_mps import __version__
except ImportError:
    __version__ = "unknown"

APP_NAME = "simkl-mps"
PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}"
OS_NAME = platform.system()
USER_AGENT = f"{APP_NAME}/{__version__} (Python {PY_VER}; {OS_NAME})"

logger = logging.getLogger(__name__)

SIMKL_API_BASE_URL = 'https://api.simkl.com'


def is_internet_connected():
    """
    Checks for a working internet connection.

    Attempts to connect to Simkl API, Google, and Cloudflare with short timeouts.

    Returns:
        bool: True if a connection to any service is successful, False otherwise.
    """
    check_urls = [
        ('https://api.simkl.com', 1.5),
        ('https://www.google.com', 1.0),
        ('https://www.cloudflare.com', 1.0)
    ]
    for url, timeout in check_urls:
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            logger.debug(f"Internet connectivity check successful via {url}")
            return True
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError, socket.error) as e:
            logger.debug(f"Internet connectivity check failed for {url}: {e}")
            continue
    logger.warning("Internet connectivity check failed for all services.")
    return False

def _add_user_agent(headers):
    headers = dict(headers) if headers else {}
    headers["User-Agent"] = USER_AGENT
    return headers

def search_movie(title, client_id, access_token):
    """
    Searches for a movie by title on Simkl using the /search/movie endpoint.

    Args:
        title (str): The movie title to search for.
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        dict | None: The first matching movie result dictionary, or None if
                      not found, credentials missing, or an API error occurs.
    """
    if not is_internet_connected():
        logger.warning(f"Simkl API: Cannot search for movie '{title}', no internet connection.")
        return None
    if not client_id or not access_token:
        logger.error("Simkl API: Missing Client ID or Access Token for movie search.")
        return None

    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    headers = _add_user_agent(headers)
    params = {'q': title, 'extended': 'full'}

    try:
        logger.info(f"Simkl API: Searching for movie '{title}'...")
        response = requests.get(f'{SIMKL_API_BASE_URL}/search/movie', headers=headers, params=params)

        if response.status_code != 200:
            error_details = ""
            try:
                # Try to get JSON details first
                error_details = response.json()
            except requests.exceptions.JSONDecodeError:
                # Fallback to raw text if JSON parsing fails
                error_details = response.text
            logger.error(f"Simkl API: Movie search failed for '{title}'. Status: {response.status_code}. Response: {error_details}")
            return None

        # Proceed only if status code was 200
        results = response.json()
        logger.info(f"Simkl API: Found {len(results) if results else 0} results for '{title}'.")
        
        if not results:
            logger.info(f"Simkl API: No direct match for '{title}', attempting fallback search.")
            return _fallback_search_movie(title, client_id, access_token)

        if results:
            first_result = results[0]
            if 'movie' not in first_result and first_result.get('type') == 'movie':
                reshaped_result = {'movie': first_result}
                logger.info(f"Simkl API: Reshaped search result for '{title}'.")
                return reshaped_result
                
            if 'movie' in first_result and 'ids' in first_result['movie']:
                ids = first_result['movie']['ids']
                simkl_id_alt = ids.get('simkl_id')
                if simkl_id_alt and not ids.get('simkl'):
                    logger.info(f"Simkl API: Found ID under 'simkl_id', adding 'simkl' key for consistency.")
                    first_result['movie']['ids']['simkl'] = simkl_id_alt
                elif not ids.get('simkl') and not simkl_id_alt:
                     logger.warning(f"Simkl API: No 'simkl' or 'simkl_id' found in IDs for '{title}'.")

        return results[0] if results else None

    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Network error searching for '{title}': {e}", exc_info=True)
        return None

def _fallback_search_movie(title, client_id, access_token):
    """
    Internal fallback search using the /search/all endpoint.

    Args:
        title (str): The movie title.
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        dict | None: The first movie result from the general search, or None.
    """
    logger.info(f"Simkl API: Performing fallback search for '{title}'...")
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    headers = _add_user_agent(headers)
    params = {'q': title, 'type': 'movie', 'extended': 'full'}
    try:
        response = requests.get(f'{SIMKL_API_BASE_URL}/search/all', headers=headers, params=params)
        if response.status_code != 200:
            logger.error(f"Simkl API: Fallback search failed for '{title}' with status {response.status_code}.")
            return None
        results = response.json()
        logger.info(f"Simkl API: Fallback search found {len(results) if results else 0} total results.")
        if not results:
            return None
            
        movie_results = [r for r in results if r.get('type') == 'movie']
        if movie_results:
            found_title = movie_results[0].get('title', title)
            logger.info(f"Simkl API: Found movie '{found_title}' in fallback search.")
            return movie_results[0]
        logger.info(f"Simkl API: No movie type results found in fallback search for '{title}'.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Network error during fallback search for '{title}': {e}", exc_info=True)
        return None

def mark_as_watched(simkl_id, client_id, access_token):
    """
    Marks a movie as watched on Simkl.

    Args:
        simkl_id (int | str): The Simkl ID of the movie.
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        bool: True if successfully marked as watched, False otherwise.
    """
    if not is_internet_connected():
        logger.warning(f"Simkl API: Cannot mark movie ID {simkl_id} as watched, no internet connection.")
        return False
    if not client_id or not access_token:
        logger.error("Simkl API: Missing Client ID or Access Token for marking as watched.")
        return False

    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    headers = _add_user_agent(headers)
    data = {'movies': [{'ids': {'simkl': simkl_id}, 'status': 'completed'}]}

    logger.info(f"Simkl API: Marking movie ID {simkl_id} as watched...")
    try:
        response = requests.post(f'{SIMKL_API_BASE_URL}/sync/history', headers=headers, json=data)
        
        if 200 <= response.status_code < 300:
            logger.info(f"Simkl API: Successfully marked movie ID {simkl_id} as watched.")
            return True
        else:
            logger.error(f"Simkl API: Failed to mark movie ID {simkl_id} as watched. Status: {response.status_code}")
            response.raise_for_status()
            return False
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Simkl API: Connection error marking movie ID {simkl_id} as watched: {e}")
        logger.info(f"Simkl API: Movie ID {simkl_id} will be added to backlog for future syncing.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error marking movie ID {simkl_id} as watched: {e}", exc_info=True)
        return False

def get_movie_details(simkl_id, client_id, access_token):
    """
    Retrieves detailed movie information from Simkl.

    Args:
        simkl_id (int | str): The Simkl ID of the movie.
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        dict | None: A dictionary containing detailed movie information,
                      or None if an error occurs or parameters are missing.
    """
    if not client_id or not access_token or not simkl_id:
        logger.error("Simkl API: Missing required parameters for get_movie_details.")
        return None

    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    headers = _add_user_agent(headers)
    params = {'extended': 'full'}
    try:
        logger.info(f"Simkl API: Fetching details for movie ID {simkl_id}...")
        response = requests.get(f'{SIMKL_API_BASE_URL}/movies/{simkl_id}', headers=headers, params=params)
        response.raise_for_status()
        movie_details = response.json()
        if movie_details:
            title = movie_details.get('title', 'N/A')
            year = movie_details.get('year', 'N/A')
            runtime = movie_details.get('runtime', 'N/A')
            logger.info(f"Simkl API: Retrieved details for '{title}' ({year}), Runtime: {runtime} min.")
            if not movie_details.get('runtime'):
                logger.warning(f"Simkl API: Runtime information missing for '{title}' (ID: {simkl_id}).")
        return movie_details
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error getting movie details for ID {simkl_id}: {e}", exc_info=True)
        return None

def get_user_settings(client_id, access_token):
    """
    Retrieves user settings from Simkl, which includes the user ID.

    Args:
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        dict | None: A dictionary containing user settings, or None if an error occurs.
                      The user ID is found under ['user_id'] for easy access.
    """
    if not client_id or not access_token:
        logger.error("Simkl API: Missing required parameters for get_user_settings.")
        return None
    if not is_internet_connected():
        logger.warning("Simkl API: Cannot get user settings, no internet connection.")
        return None

    # Simplified headers to avoid potential issues with 412 Precondition Failed
    headers = {
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    headers = _add_user_agent(headers)
    
    # Try account endpoint first (most direct way to get user ID)
    account_url = f'{SIMKL_API_BASE_URL}/users/account'
    try:
        logger.info("Simkl API: Requesting user account information...")
        account_response = requests.get(account_url, headers=headers, timeout=15)
        
        if account_response.status_code == 200:
            account_info = account_response.json()
            # Check if account_info is not None before accessing it
            if account_info is not None:
                user_id = account_info.get('id')
                
                if user_id:
                    logger.info(f"Simkl API: Found User ID from account endpoint: {user_id}")
                    settings = {
                        'account': account_info,
                        'user': {'ids': {'simkl': user_id}},
                        'user_id': user_id
                    }
                    
                    # Save user ID to env file for future use
                    from simkl_mps.credentials import get_env_file_path
                    env_path = get_env_file_path()
                    _save_access_token(env_path, access_token, user_id)
                    
                    return settings
            else:
                logger.warning("Simkl API: Account info is None despite 200 status code")
        else:
            logger.warning(f"Simkl API: Account endpoint returned status code {account_response.status_code}")
            
    except requests.exceptions.RequestException as e:
        logger.warning(f"Simkl API: Error accessing account endpoint: {e}")
    
    # If account endpoint failed, try settings endpoint with simplified headers
    settings_url = f'{SIMKL_API_BASE_URL}/users/settings'
    try:
        logger.info("Simkl API: Requesting user settings information...")
        settings_response = requests.get(settings_url, headers=headers, timeout=15)
        
        if settings_response.status_code != 200:
            logger.error(f"Simkl API: Error getting user settings: {settings_response.status_code} {settings_response.text}")
            return None
            
        settings = settings_response.json()
        logger.info("Simkl API: User settings retrieved successfully.")
        
        # Ensure required structures exist
        if 'user' not in settings:
            settings['user'] = {}
        if 'ids' not in settings['user']:
            settings['user']['ids'] = {}
        
        # Extract user ID from various possible locations
        user_id = None
        
        # Check common paths for user ID
        if 'user' in settings and 'ids' in settings['user'] and 'simkl' in settings['user']['ids']:
            user_id = settings['user']['ids']['simkl']
        elif 'account' in settings and 'id' in settings['account']:
            user_id = settings['account']['id']
        elif 'id' in settings:
            user_id = settings['id']
        
        # If no user ID found, search deeper
        if not user_id:
            for key, value in settings.items():
                if isinstance(value, dict) and 'id' in value:
                    user_id = value['id']
                    break
        
        # Store the user ID in consistent locations
        if user_id:
            settings['user_id'] = user_id
            settings['user']['ids']['simkl'] = user_id
            logger.info(f"Simkl API: Found User ID: {user_id}")
            
            # Save user ID to env file for future use
            from simkl_mps.credentials import get_env_file_path
            env_path = get_env_file_path()
            _save_access_token(env_path, access_token, user_id)
        else:
            logger.warning("Simkl API: User ID not found in settings response")
            
        return settings
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error getting user settings: {e}")
        return None

def pin_auth_flow(client_id, redirect_uri="urn:ietf:wg:oauth:2.0:oob"):
    """
    Implements the OAuth 2.0 device authorization flow for Simkl authentication.
    
    Args:
        client_id (str): Simkl API client ID
        redirect_uri (str, optional): OAuth redirect URI. Defaults to device flow URI.
        
    Returns:
        str | None: The access token if authentication succeeds, None otherwise.
    """
    import time
    import requests
    import webbrowser
    from pathlib import Path
    from simkl_mps.credentials import get_env_file_path
    
    logger.info("Starting Simkl PIN authentication flow")
    
    if not is_internet_connected():
        logger.error("Cannot start authentication flow: no internet connection")
        print("[ERROR] No internet connection detected. Please check your connection and try again.")
        return None
    
    # Step 1: Request device code
    try:
        headers = _add_user_agent({"Content-Type": "application/json"})
        resp = requests.get(
            f"{SIMKL_API_BASE_URL}/oauth/pin",
            params={"client_id": client_id, "redirect": redirect_uri},
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to initiate PIN auth: {e}", exc_info=True)
        print("[ERROR] Could not contact Simkl for authentication. Please check your internet connection and try again.")
        return None
    
    # Extract authentication parameters
    user_code = data["user_code"]
    verification_url = data["verification_url"]
    expires_in = data.get("expires_in", 900)  # Default to 15 minutes if not provided
    pin_url = f"https://simkl.com/pin/{user_code}"
    interval = data.get("interval", 5)  # Default poll interval of 5 seconds
    
    # Display authentication instructions
    print("\n=== Simkl Authentication ===")
    print(f"1. We've opened your browser to: {pin_url}")
    print(f"   (If it didn't open, copy and paste this URL into your browser.)")
    print(f"2. Or go to: {verification_url} and enter the code: {user_code}")
    print(f"   (Code: {user_code})")
    print(f"   (You have {expires_in//60} minutes to complete authentication.)\n")
    
    # Open browser for user convenience
    try:
        # Use https:// protocol explicitly to avoid unknown protocol errors
        webbrowser.open(f"https://simkl.com/pin/{user_code}")
    except Exception as e:
        logger.warning(f"Failed to open browser: {e}")
        # Continue anyway, as user can manually navigate
    
    print("Waiting for you to authorize this application...")
    
    # Step 2: Poll for access token with adaptive backoff
    start_time = time.time()
    poll_headers = _add_user_agent({"Content-Type": "application/json"})
    current_interval = interval
    timeout_warning_shown = False
    
    while time.time() - start_time < expires_in:
        # Show a reminder halfway through the expiration time
        elapsed = time.time() - start_time
        if elapsed > (expires_in / 2) and not timeout_warning_shown:
            remaining_mins = int((expires_in - elapsed) / 60)
            print(f"\n[!] Reminder: You have about {remaining_mins} minutes left to complete authentication.")
            timeout_warning_shown = True
        
        try:
            poll = requests.get(
                f"{SIMKL_API_BASE_URL}/oauth/pin/{user_code}",
                params={"client_id": client_id},
                headers=poll_headers,
                timeout=10
            )
            
            if poll.status_code != 200:
                logger.warning(f"Pin verification returned status {poll.status_code}, retrying...")
                time.sleep(current_interval)
                continue
                
            result = poll.json()
            
            if result.get("result") == "OK":
                access_token = result.get("access_token")
                if access_token:
                    # Success! Save the token
                    print("\n[✓] Authentication successful!")
                    
                    # Get the user ID before saving
                    user_id = None
                    try:
                        print("Retrieving your Simkl user ID...")
                        # Try to get user ID from account endpoint first (more reliable)
                        auth_headers = {
                            'Content-Type': 'application/json',
                            'simkl-api-key': client_id,
                            'Authorization': f'Bearer {access_token}',
                            'Accept': 'application/json'
                        }
                        auth_headers = _add_user_agent(auth_headers)
                        
                        account_resp = requests.get(
                            f"{SIMKL_API_BASE_URL}/users/account", 
                            headers=auth_headers,
                            timeout=10
                        )
                        
                        if account_resp.status_code == 200:
                            account_data = account_resp.json()
                            user_id = account_data.get('id')
                            logger.info(f"Retrieved user ID during authentication: {user_id}")
                            print(f"[✓] Found your Simkl user ID: {user_id}")
                        
                        # If account endpoint failed, try settings
                        if not user_id:
                            settings = get_user_settings(client_id, access_token)
                            if settings and settings.get('user_id'):
                                user_id = settings.get('user_id')
                                logger.info(f"Retrieved user ID from settings: {user_id}")
                                print(f"[✓] Found your Simkl user ID: {user_id}")
                    except Exception as e:
                        logger.warning(f"Failed to retrieve user ID during authentication: {e}")
                        print("[!] Warning: Could not retrieve your Simkl user ID - some features may be limited.")
                    
                    # Save token (and user ID if available) to .env file
                    env_path = get_env_file_path()
                    if not _save_access_token(env_path, access_token, user_id):
                        print("[!] Warning: Couldn't save credentials to file, but you can still use them for this session.")
                    else:
                        print(f"[✓] Credentials saved to: {env_path}\n")
                    
                    # Important: After success, navigate the user back to Simkl main page to complete the experience
                    try:
                        webbrowser.open("https://simkl.com/")
                    except Exception as e:
                        logger.warning(f"Failed to open browser after authentication: {e}")
                    
                    # Validate the token works
                    if _validate_access_token(client_id, access_token):
                        logger.info("Access token validated successfully")
                        return access_token
                    else:
                        logger.error("Access token validation failed")
                        print("[ERROR] Authentication completed but token validation failed. Please try again.")
                        return None
                        
            elif result.get("result") == "KO":
                msg = result.get("message", "")
                if msg == "Authorization pending":
                    # Normal state while waiting for user
                    time.sleep(current_interval)
                elif msg == "Slow down":
                    # API rate limiting, increase interval
                    logger.warning("Received 'Slow down' response, increasing polling interval")
                    current_interval = min(current_interval * 2, 30)  # Max 30 seconds
                    time.sleep(current_interval)
                else:
                    logger.error(f"Authentication failed: {msg}")
                    print(f"[ERROR] Authentication failed: {msg}")
                    return None
            else:
                time.sleep(current_interval)
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error during polling: {e}")
            # Implement exponential backoff for connection issues
            current_interval = min(current_interval * 1.5, 20)
            time.sleep(current_interval)
    
    print("[ERROR] Authentication timed out. Please try again.")
    return None

def _save_access_token(env_path, access_token, user_id=None):
    """
    Helper function to save access token and user ID to .env file
    
    Args:
        env_path (str|Path): Path to the .env file
        access_token (str): The Simkl access token to save
        user_id (str|int, optional): The Simkl user ID to save
        
    Returns:
        bool: True if successful, False if an error occurred
    """
    try:
        from pathlib import Path
        
        env_path = Path(env_path)
        env_dir = env_path.parent
        
        # Create directory if it doesn't exist
        if not env_dir.exists():
            env_dir.mkdir(parents=True, exist_ok=True)
        
        lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        
        # Update or add the access token
        token_found = False
        user_id_found = False
        
        for i, line in enumerate(lines):
            if line.strip().startswith("SIMKL_ACCESS_TOKEN="):
                lines[i] = f"SIMKL_ACCESS_TOKEN={access_token}\n"
                token_found = True
            elif line.strip().startswith("SIMKL_USER_ID=") and user_id is not None:
                lines[i] = f"SIMKL_USER_ID={user_id}\n"
                user_id_found = True
        
        if not token_found:
            lines.append(f"SIMKL_ACCESS_TOKEN={access_token}\n")
        
        if user_id is not None and not user_id_found:
            lines.append(f"SIMKL_USER_ID={user_id}\n")
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        logger.info(f"Saved credentials to {env_path}")
        if user_id is not None:
            logger.info(f"Saved user ID {user_id} to {env_path}")
            
        return True
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}", exc_info=True)
        return False

def _validate_access_token(client_id, access_token):
    """Verify the access token works by making a simple API call"""
    try:
        headers = {
            'Content-Type': 'application/json',
            'simkl-api-key': client_id,
            'Authorization': f'Bearer {access_token}'
        }
        headers = _add_user_agent(headers)
        
        response = requests.get(
            f'{SIMKL_API_BASE_URL}/users/settings', 
            headers=headers,
            timeout=10
        )
        return response.status_code == 200
    except:
        return False