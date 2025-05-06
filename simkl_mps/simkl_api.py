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

        # Process the response to find and reshape the movie item
        results_json = response.json()
        logger.info(f"Simkl API: Found {len(results_json) if isinstance(results_json, list) else 'N/A'} results for '{title}'.")

        final_result_item = None

        if isinstance(results_json, list) and results_json: # Primary search has results in a list
            final_result_item = results_json[0]
        elif not isinstance(results_json, list) and results_json is not None : # Unexpected primary search response format but not empty
            logger.warning(f"Simkl API: Unexpected primary search response format for '{title}'. Expected list, got {type(results_json)}. Response: {results_json}")
            # final_result_item remains None, fallback will be attempted.
        
        # Try fallback if primary search yielded no usable result, was empty, or malformed
        if not final_result_item: 
            logger.info(f"Simkl API: No direct match or usable result from primary search for '{title}', attempting fallback search.")
            final_result_item = _fallback_search_movie(title, client_id, access_token)
            # _fallback_search_movie returns a single item (dict) or None

        if final_result_item: # If we have an item from primary or fallback
            if isinstance(final_result_item, dict):
                # Determine if the item is a movie based on 'type' or 'endpoint_type'
                is_movie_type = (final_result_item.get('type') == 'movie' or \
                                 final_result_item.get('endpoint_type') == 'movies')

                if is_movie_type:
                    # If it's a movie type, ensure it's wrapped in {'movie': ...} structure
                    if 'movie' not in final_result_item:
                        logger.info(f"Simkl API: Reshaping search result for '{title}' into {{'movie': ...}} structure.")
                        final_result_item = {'movie': final_result_item}
                    
                    # ID consistency check: ensure 'simkl' id exists if 'simkl_id' is present
                    # This operates on the inner movie dictionary.
                    if 'movie' in final_result_item and \
                       isinstance(final_result_item.get('movie'), dict) and \
                       'ids' in final_result_item['movie']:
                        ids = final_result_item['movie']['ids']
                        simkl_id_alt = ids.get('simkl_id') 
                        if simkl_id_alt and not ids.get('simkl'):
                            logger.info(f"Simkl API: Found ID under 'simkl_id' in movie object, adding 'simkl' key for consistency.")
                            final_result_item['movie']['ids']['simkl'] = simkl_id_alt
                        elif not ids.get('simkl') and not simkl_id_alt:
                             logger.warning(f"Simkl API: No 'simkl' or 'simkl_id' found in movie IDs for '{title}'.")
                    # Return the processed (possibly reshaped) movie item
                    return final_result_item
                else: # Not identified as a movie type
                     logger.warning(f"Simkl API: Search for movie '{title}' returned a non-movie item: Type='{final_result_item.get('type')}', EndpointType='{final_result_item.get('endpoint_type')}'. Discarding.")
                     return None # Explicitly return None if it's not a movie type
            else: # final_result_item is not a dict (unexpected)
                logger.warning(f"Simkl API: Expected dictionary for final_result_item from search, got {type(final_result_item)}. Discarding.")
                return None
        else: # No results from primary or fallback
            logger.info(f"Simkl API: No movie results found for '{title}' after primary and fallback search.")
            return None

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

def search_file(file_path, client_id, part=None):
    """
    Searches for media based on a file path using the Simkl /search/file endpoint.

    Args:
        file_path (str): The full path to the media file.
        client_id (str): Simkl API client ID.
        part (int, optional): The part number (e.g., for multi-part files). Defaults to None.

    Returns:
        dict | None: The parsed JSON response from Simkl, or None if an error occurs.
    """
    if not is_internet_connected():
        logger.warning(f"Simkl API: Cannot search for file '{file_path}', no internet connection.")
        return None
    if not client_id:
        logger.error("Simkl API: Missing Client ID for file search.")
        return None

    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id
    }
    headers = _add_user_agent(headers)
    data = {'file': file_path}
    if part is not None:
        data['part'] = part

    logger.info(f"Simkl API: Searching by file: '{file_path}' (Part: {part if part else 'N/A'})...")
    try:
        response = requests.post(f'{SIMKL_API_BASE_URL}/search/file', headers=headers, json=data)

        if response.status_code != 200:
            error_details = ""
            try:
                error_details = response.json()
            except requests.exceptions.JSONDecodeError:
                error_details = response.text
            logger.error(f"Simkl API: File search failed for '{file_path}'. Status: {response.status_code}. Response: {error_details}")
            return None

        results = response.json()
        logger.info(f"Simkl API: File search successful for '{file_path}'.")
        return results

    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Network error during file search for '{file_path}': {e}", exc_info=True)
        return None

def add_to_history(payload, client_id, access_token):
    """
    Adds items (movies, shows, episodes) to the user's Simkl watch history.

    Args:
        payload (dict): The data payload conforming to the Simkl /sync/history API.
                        Example: {'movies': [...], 'shows': [...]}
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        dict | None: The parsed JSON response from Simkl on success, None otherwise.
    """
    if not is_internet_connected():
        logger.warning("Simkl API: Cannot add item to history, no internet connection.")
        return None
    if not client_id or not access_token:
        logger.error("Simkl API: Missing Client ID or Access Token for adding to history.")
        return None
    if not payload:
        logger.error("Simkl API: Empty payload provided for adding to history.")
        return None

    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    headers = _add_user_agent(headers)

    # Determine item type for logging (best effort)
    item_description = "item(s)"
    if 'movies' in payload and payload['movies']:
        item_description = f"movie(s): {[m.get('ids', {}).get('simkl', 'N/A') for m in payload['movies']]}"
    elif 'shows' in payload and payload['shows']:
        item_description = f"show(s)/episode(s): {[s.get('ids', {}).get('simkl', 'N/A') for s in payload['shows']]}"
    elif 'episodes' in payload and payload['episodes']:
         item_description = f"episode(s): {[e.get('ids', {}).get('simkl', 'N/A') for e in payload['episodes']]}"


    logger.info(f"Simkl API: Adding {item_description} to history...")
    try:
        response = requests.post(f'{SIMKL_API_BASE_URL}/sync/history', headers=headers, json=payload)

        if 200 <= response.status_code < 300:
            logger.info(f"Simkl API: Successfully added {item_description} to history.")
            try:
                return response.json()
            except requests.exceptions.JSONDecodeError:
                 logger.warning("Simkl API: History update successful but response was not valid JSON.")
                 return {"status": "success", "message": "Non-JSON response received but status code indicated success."} # Return a success indicator
        else:
            error_details = ""
            try:
                error_details = response.json()
            except requests.exceptions.JSONDecodeError:
                error_details = response.text
            logger.error(f"Simkl API: Failed to add {item_description} to history. Status: {response.status_code}. Response: {error_details}")
            # Don't raise_for_status here, allow caller to handle based on None return
            return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Simkl API: Connection error adding {item_description} to history: {e}")
        logger.info(f"Simkl API: Item(s) {item_description} will be added to backlog for future syncing.")
        return None # Indicate failure but allow backlog processing
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error adding {item_description} to history: {e}", exc_info=True)
        return None

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
            
            # Ensure essential fields exist for watch history
            movie_details['simkl_id'] = simkl_id  # Add simkl_id explicitly for the history
            
            # Get IMDb ID if available
            if 'ids' in movie_details:
                imdb_id = movie_details['ids'].get('imdb')
                if imdb_id:
                    # Store IMDb ID directly in the movie_details for easy access
                    movie_details['imdb_id'] = imdb_id
                    logger.info(f"Simkl API: Retrieved IMDb ID: {imdb_id} for '{title}'")
            
            # Get poster URL if available
            if 'poster' not in movie_details and 'images' in movie_details:
                if movie_details['images'].get('poster'):
                    # Store only the poster ID, not the full URL
                    movie_details['poster'] = movie_details['images']['poster']
                    logger.info(f"Added poster ID for {title}")
            
            # Ensure type is set for history filtering
            if 'type' not in movie_details:
                movie_details['type'] = 'movie'

            logger.info(f"Simkl API: Retrieved details for '{title}' ({year}), Runtime: {runtime} min.")
            if not movie_details.get('runtime'):
                logger.warning(f"Simkl API: Runtime information missing for '{title}' (ID: {simkl_id}).")
        return movie_details
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error getting movie details for ID {simkl_id}: {e}", exc_info=True)
        return None

def get_show_details(simkl_id, client_id, access_token):
    """
    Retrieves detailed show information from Simkl.

    Args:
        simkl_id (int | str): The Simkl ID of the show.
        client_id (str): Simkl API client ID.
        access_token (str): Simkl API access token.

    Returns:
        dict | None: A dictionary containing detailed show information,
                     or None if an error occurs or parameters are missing.
    """
    if not client_id or not access_token or not simkl_id:
        logger.error("Simkl API: Missing required parameters for get_show_details.")
        return None

    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    headers = _add_user_agent(headers)
    params = {'extended': 'full'}
    try:
        logger.info(f"Simkl API: Fetching details for show/anime ID {simkl_id}...")
        response = requests.get(f'{SIMKL_API_BASE_URL}/tv/{simkl_id}', headers=headers, params=params)
        response.raise_for_status()
        show_details = response.json()
        if show_details:
            title = show_details.get('title', 'N/A')
            year = show_details.get('year', 'N/A')
            show_type = show_details.get('type', 'show')  # 'show' or 'anime'
            
            # Ensure essential fields exist for watch history
            show_details['simkl_id'] = simkl_id  # Add simkl_id explicitly for the history
            
            # Get IMDb ID if available
            if 'ids' in show_details:
                imdb_id = show_details['ids'].get('imdb')
                if imdb_id:
                    # Store IMDb ID directly in the show_details for easy access
                    # Also ensure it's in the ids sub-dictionary for consistency with cache
                    show_details['imdb_id'] = imdb_id
                    show_details['ids']['imdb'] = imdb_id
                    logger.info(f"Simkl API: Retrieved IMDb ID: {imdb_id} for '{title}'")

                anilist_id = show_details['ids'].get('anilist')
                if anilist_id:
                    show_details['ids']['anilist'] = anilist_id # Ensure it's in the ids sub-dictionary
                    logger.info(f"Simkl API: Retrieved Anilist ID: {anilist_id} for '{title}'")
            
            # Get poster URL if available
            if 'poster' not in show_details and 'images' in show_details:
                if show_details['images'].get('poster'):
                    # Store only the poster ID, not the full URL
                    show_details['poster'] = show_details['images']['poster']
                    logger.info(f"Added poster ID for {title}")
            
            if 'poster' in show_details and not 'poster_url' in show_details:
                show_details['poster_url'] = show_details['poster']
                
            # Ensure type is set for history filtering
            if 'type' not in show_details:
                show_details['type'] = show_type

            logger.info(f"Simkl API: Retrieved details for {show_type} '{title}' ({year}).")
            
            # Additional debug logging
            logger.debug(f"Show details for {title} (ID: {simkl_id}): {show_details}")
        return show_details
    except requests.exceptions.RequestException as e:
        logger.error(f"Simkl API: Error getting show details for ID {simkl_id}: {e}", exc_info=True)
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