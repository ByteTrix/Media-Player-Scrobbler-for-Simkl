import requests
import time
import logging
import socket
import os

# Set up logging
logger = logging.getLogger(__name__)

SIMKL_API_BASE_URL = 'https://api.simkl.com'

# Get the client ID from environment variable or the bundled value
DEFAULT_CLIENT_ID = os.getenv("SIMKL_CLIENT_ID")

# Include a backup hardcoded client ID as fallback - replace with your actual client ID
BUNDLED_CLIENT_ID = "your_simkl_client_id_here" 

def is_internet_connected():
    """
    Check if there's a working internet connection by attempting to connect to multiple reliable services.
    
    Returns:
        bool: True if internet is connected, False otherwise
    """
    # List of reliable services to check (with timeouts)
    check_urls = [
        ('https://api.simkl.com', 1.5),         # Primary: Simkl API
        ('https://www.google.com', 1.0),         # Backup: Google
        ('https://www.cloudflare.com', 1.0)      # Backup: Cloudflare
    ]
    
    for url, timeout in check_urls:
        try:
            # Try to connect with a short timeout for faster response
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return True
        except (requests.ConnectionError, requests.Timeout, socket.error) as e:
            logger.debug(f"Internet connectivity check failed for {url}: {e}")
            continue  # Try the next URL
            
    # If we've tried all URLs and none responded, we're offline
    return False

def search_movie(title, client_id, access_token):
    """
    Search for a movie by title on Simkl.
    
    Args:
        title: The movie title to search for
        client_id: Simkl API client ID
        access_token: Simkl API access token
        
    Returns:
        dict: The first matching movie result or None if not found
    """
    # First check internet connectivity
    if not is_internet_connected():
        logger.warning(f"Cannot search for movie '{title}': No internet connection")
        return None
        
    if not client_id or not access_token:
        logger.error("Missing Client ID or Access Token for search_movie.")
        return None
        
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {'q': title, 'extended': 'full'}
    
    try:
        logger.info(f"Searching Simkl for movie: '{title}'")
        response = requests.get(f'{SIMKL_API_BASE_URL}/search/movie', headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Simkl API error: {response.status_code}")
            try:
                error_data = response.json()
                logger.error(f"Error details: {error_data}")
            except:
                logger.error(f"Error response text: {response.text}")
            return None
            
        results = response.json()
        
        logger.info(f"Found {len(results) if results else 0} results for '{title}'")
        
        # Dump the raw search results to the log for debugging
        if results and len(results) > 0:
            logger.debug(f"Raw search results: {results}")
        
        if not results:
            return _fallback_search_movie(title, client_id, access_token)
        
        # Log the structure of the first result to help with debugging
        if results and len(results) > 0:
            # Check if the expected structure exists, if not, fix the structure
            first_result = results[0]
            logger.debug(f"First result structure: {first_result}")
            
            # Sometimes SIMKL returns results in a different format than expected
            # Check for both possible structures and reshape if needed
            if 'movie' not in first_result:
                if 'type' in first_result and first_result.get('type') == 'movie':
                    # Reshape the result to expected format
                    movie_data = first_result
                    # Create a new structure matching the expected format
                    reshaped_result = {
                        'movie': movie_data
                    }
                    logger.info(f"Reshaped search result for '{title}' to match expected format")
                    return reshaped_result
                
            # The originally expected structure
            if 'movie' in first_result and 'ids' in first_result['movie']:
                ids = first_result['movie']['ids']
                logger.debug(f"ID structure found: {ids}")
                
                # Check both potential ID keys
                simkl_id = ids.get('simkl')
                simkl_id_alt = ids.get('simkl_id')
                
                if simkl_id:
                    logger.info(f"Found SIMKL ID under 'simkl' key: {simkl_id}")
                elif simkl_id_alt:
                    logger.info(f"Found SIMKL ID under 'simkl_id' key: {simkl_id_alt}")
                    # If the ID is under 'simkl_id', add it under 'simkl' too for consistency
                    first_result['movie']['ids']['simkl'] = simkl_id_alt
                else:
                    logger.warning("No SIMKL ID found in response under expected keys")
            
        return results[0]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching Simkl for '{title}': {e}")
        return None

def _fallback_search_movie(title, client_id, access_token):
    """Fallback search method using the general search endpoint."""
    logger.info(f"Trying fallback search for '{title}'")
    
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {'q': title, 'type': 'movie', 'extended': 'full'}
    
    try:
        response = requests.get(f'{SIMKL_API_BASE_URL}/search/all', headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Fallback search failed with status: {response.status_code}")
            return None
            
        results = response.json()
        logger.info(f"Fallback search found {len(results) if results else 0} results")
        
        # Check if results is None or empty before trying to iterate
        if not results:
            return None
        
        movie_results = [r for r in results if r.get('type') == 'movie']
        
        if movie_results:
            logger.info(f"Found movie in fallback search: {movie_results[0].get('title', title)}")
            return movie_results[0]
        return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error in fallback search: {e}")
        return None

def mark_as_watched(simkl_id, client_id, access_token):
    """
    Mark a movie as watched in Simkl.
    
    Args:
        simkl_id: The Simkl ID of the movie
        client_id: Simkl API client ID
        access_token: Simkl API access token
        
    Returns:
        bool: True if successfully marked as watched, False otherwise
    """
    # First check internet connectivity
    if not is_internet_connected():
        logger.warning(f"Cannot mark movie ID {simkl_id} as watched: No internet connection")
        return False
    
    if not client_id or not access_token:
        logger.error("Missing Client ID or Access Token for mark_as_watched.")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    data = {
        'movies': [
            {
                'ids': {
                    'simkl': simkl_id
                },
                'status': 'completed'
            }
        ]
    }
    
    logger.info(f"Sending request to mark movie ID {simkl_id} as watched")
    
    try:
        response = requests.post(f'{SIMKL_API_BASE_URL}/sync/history', headers=headers, json=data)
        
        logger.info(f"Response status code: {response.status_code}")
        try:
            logger.debug(f"Response JSON: {response.json()}")
        except:
            logger.debug(f"Response text: {response.text}")
        
        if response.status_code == 201 or response.status_code == 200:
            logger.info(f"Successfully marked movie ID {simkl_id} as watched")
            return True
        else:
            logger.error(f"Failed to mark movie as watched. Status code: {response.status_code}")
            response.raise_for_status()
            return False
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error marking movie ID {simkl_id} as watched: {e}")
        logger.info(f"Movie ID {simkl_id} will be added to backlog for future syncing")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error marking Simkl ID {simkl_id} as watched: {e}")
    
    return False

def get_movie_details(simkl_id, client_id, access_token):
    """
    Get detailed movie information from Simkl including runtime, genres, and other metadata.
    
    Args:
        simkl_id: The Simkl ID of the movie
        client_id: Simkl API client ID
        access_token: Simkl API access token
        
    Returns:
        dict: Detailed movie information or None if not found
    """
    if not client_id or not access_token or not simkl_id:
        logger.error("Missing required parameters for get_movie_details")
        return None
        
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {'extended': 'full'}
    
    try:
        logger.info(f"Fetching detailed info for movie ID: {simkl_id}")
        response = requests.get(f'{SIMKL_API_BASE_URL}/movies/{simkl_id}', 
                               headers=headers, 
                               params=params)
        response.raise_for_status()
        movie_details = response.json()
        
        # Log some useful movie information
        if movie_details:
            title = movie_details.get('title', 'Unknown Title')
            year = movie_details.get('year', 'Unknown Year')
            runtime = movie_details.get('runtime', 0)
            genres = ', '.join(movie_details.get('genres', ['Unknown']))
            
            logger.info(f"Retrieved movie: '{title}' ({year}), Runtime: {runtime} min, Genres: {genres}")
            
            # Check if we have runtime information
            if runtime:
                logger.info(f"Found runtime: {runtime} minutes for '{title}'")
            else:
                logger.warning(f"No runtime information available for '{title}'")
                
        return movie_details
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting movie details for ID {simkl_id}: {e}")
        return None

def get_device_code(client_id):
    """Initiates the device authentication flow."""
    if not client_id:
        logger.error("Missing Client ID for get_device_code.")
        return None
    url = f"{SIMKL_API_BASE_URL}/oauth/pin?client_id={client_id}"
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if "user_code" in data and "verification_url" in data and "device_code" in data:
            return data
        else:
            logger.error(f"Unexpected response format from Simkl device code endpoint: {data}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting device code: {e}")
        if e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            try:
                logger.error(f"Response body: {e.response.json()}")
            except requests.exceptions.JSONDecodeError:
                logger.error(f"Response body: {e.response.text}")
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

    print(f"Polling Simkl for authorization using user code: {user_code}")
    print("Waiting for user authorization (this may take a minute)...")
    
    print("Please go to the Simkl site and enter the code shown above.")
    time.sleep(10)
    
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
                    logger.warning(f"Response data: {response_data}")
                time.sleep(interval)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error while polling: {str(e)}")
            time.sleep(2)

    print("\n✗ Authentication timed out")
    return None

def authenticate(client_id=None):
    """
    Handles the full device authentication flow.
    Requires a valid client ID to be provided.
    """
    if not client_id:
        logger.error("Client ID is required for authentication.")
        return None

    print("Requesting device code from Simkl...")
    device_info = get_device_code(client_id)
    if not device_info:
        print("Failed to get device code.")
        return None

    user_code = device_info.get('user_code')
    verification_url = device_info.get('verification_url')
    # Increase the minimum polling interval (minimum 5 seconds between requests)
    interval = max(device_info.get('interval', 5), 5)  
    
    # Significantly increase the expiration time to give users more time to authenticate
    # Use 1800 seconds (30 minutes) as the minimum timeout, or more if API provides it
    expires_in = max(device_info.get('expires_in', 900), 1800)
    
    logger.info(f"Using authentication timeout of {expires_in} seconds (30 minutes)")

    if not all([user_code, verification_url]):
        logger.error("Incomplete device information received.")
        return None

    print("\n" + "=" * 60)
    print(f"Please go to: {verification_url}")
    print(f"And enter the code: {user_code}")
    print(f"This code will be valid for {int(expires_in/60)} minutes")
    print("=" * 60 + "\n")

    access_token_info = poll_for_token(client_id, user_code, interval, expires_in)

    if access_token_info and 'access_token' in access_token_info:
        token = access_token_info['access_token']
        print("\n[NICE] Authentication complete! Access token received.")
        return token
    else:
        print("\n✗ Authentication process failed or timed out.")
        print("If you didn't have enough time to authenticate, try running the script again.")
        return None