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
            logger.error(f"Simkl API: Movie search failed for '{title}' with status {response.status_code}.")
            try: 
                logger.error(f"Simkl API Error details: {response.json()}")
            except: 
                logger.error(f"Simkl API Error response text: {response.text}")
            return None

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

def get_device_code(client_id):
    """
    Initiates the Simkl OAuth device authentication flow.

    Args:
        client_id (str): The Simkl application client ID.

    Returns:
        dict | None: A dictionary containing 'user_code', 'verification_url',
                      'device_code', 'interval', and 'expires_in', or None on error.
    """
    if not client_id:
        logger.error("Simkl API: Client ID is required to initiate device authentication.")
        return None
    url = f"{SIMKL_API_BASE_URL}/oauth/pin?client_id={client_id}"
    headers = {'Content-Type': 'application/json'}
    headers = _add_user_agent(headers)
    logger.info("Simkl API: Requesting device code for authentication...")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if all(k in data for k in ("user_code", "verification_url", "device_code")):
            logger.info("Simkl API: Device code received successfully.")
            return data
        else:
            logger.error(f"Simkl API: Unexpected response format from device code endpoint: {data}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error requesting device code: {e}", exc_info=True)
        if e.response is not None:
            logger.error(f"Simkl API: Response status: {e.response.status_code}")
            try: 
                logger.error(f"Simkl API: Response body: {e.response.json()}")
            except: 
                logger.error(f"Simkl API: Response body: {e.response.text}")
    return None

def poll_for_token(client_id, user_code, interval, expires_in):
    """Polls Simkl to check if the user has authorized the device."""
    if not client_id or not user_code:
        logger.error("Missing arguments for poll_for_token.")
        return None

    url = f"{SIMKL_API_BASE_URL}/oauth/pin/{user_code}?client_id={client_id}"
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id
    }
    headers = _add_user_agent(headers)
    print("Waiting for user authorization (this may take a minute)...")
    
    time.sleep(18)
    
    start_time = time.time()
    poll_count = 0
    
    while time.time() - start_time < expires_in:
        poll_count += 1
        try:
            response = requests.get(url, headers=headers)
            
            response_data = None
            try:
                response_data = response.json()
            except ValueError:
                logger.warning(f"Non-JSON response: {response.text}")
            
            if response.status_code == 200:
                if not response_data:
                    logger.warning("Empty response with status 200")
                    time.sleep(interval)
                    continue
                    
                if response_data.get('result') == 'OK' and 'access_token' in response_data:
                    print("[NICE] Authorization successful!")
                    return response_data
                elif response_data.get('result') == 'KO':
                    print("✗ Authorization denied by user")
                    return None
                else:
                    if poll_count % 3 == 0:
                        print(f"Still waiting for authorization... ({int(time.time() - start_time)}s elapsed)")
                    time.sleep(interval)
            
            elif response.status_code == 400:
                if poll_count % 10 == 0:
                    print(".", end="", flush=True)
                time.sleep(interval)
                
            elif response.status_code == 404:
                print("✗ Device code expired or not found")
                return None
                
            else:
                logger.warning(f"Unexpected status code: {response.status_code}")
                if response_data:
                    logger.warning("Response data contains unexpected content. Logging skipped for security reasons.")
                time.sleep(interval)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error while polling: {str(e)}")
            time.sleep(2)

    print("\n Authentication timed out")
    return None

def authenticate(client_id=None):
    """
    Handles the complete Simkl OAuth device authentication flow.

    Args:
        client_id (str): The Simkl application client ID.

    Returns:
        str | None: The obtained access token, or None if authentication fails.
    """
    if not client_id:
        logger.critical("Simkl API: Authentication cannot proceed without a Client ID.")
        return None

    logger.info("Initiating Simkl Device Authentication...")
    device_info = get_device_code(client_id)
    if not device_info:
        logger.error("Simkl API: Failed to obtain device code.")
        print("ERROR: Could not obtain device code from Simkl.")
        return None

    user_code = device_info.get('user_code')
    verification_url = device_info.get('verification_url')
    interval = max(device_info.get('interval', 5), 3)
    expires_in = 60
    logger.info(f"Simkl API: Using auth interval={interval}s, expires_in={expires_in}s.")

    if not all([user_code, verification_url]):
        logger.error("Simkl API: Incomplete device information received from Simkl.")
        print("ERROR: Incomplete authentication information received from Simkl.")
        return None

    print("=" * 60)
    print("ACTION REQUIRED:")
    print(f"1. Go to: {verification_url}")
    print(f"2. Enter the code: {user_code}")
    print(f"   (Code is valid for approximately {int(expires_in/60)} minute(s))")
    print("=" * 60)

    access_token_info = poll_for_token(client_id, user_code, interval, expires_in)

    if access_token_info and 'access_token' in access_token_info:
        token = access_token_info['access_token']
        logger.info("Simkl API: Authentication successful, token obtained.")
        print("\nAuthentication Complete. Access token received.\n")
        return token
    else:
        logger.error("Simkl API: Authentication process failed, timed out, or was denied.")
        print("\nERROR: Authentication failed, timed out, or was denied by user.\nIf you need more time, please run the 'init' command again.")
        return None
