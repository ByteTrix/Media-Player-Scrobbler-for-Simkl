# simkl_api.py

import requests
import time # Add time import for polling
# Remove direct import from config
# from config import SIMKL_CLIENT_ID, SIMKL_ACCESS_TOKEN

SIMKL_API_BASE_URL = 'https://api.simkl.com'

# Modify functions to accept client_id and access_token
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
    if not client_id or not access_token:
        print("Error: Missing Client ID or Access Token for search_movie.")
        return None
        
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {'q': title, 'extended': 'full'}
    
    try:
        print(f"Searching Simkl for movie: '{title}'")
        response = requests.get(f'{SIMKL_API_BASE_URL}/search/movie', headers=headers, params=params)
        
        # Print status code for debugging
        print(f"Simkl API search response status: {response.status_code}")
        
        # Handle non-200 responses
        if response.status_code != 200:
            print(f"Simkl API error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {error_data}")
            except:
                print(f"Error response text: {response.text}")
            return None
            
        # Parse the response
        results = response.json()
        
        # Debug: print number of results
        print(f"Found {len(results) if results else 0} results for '{title}'")
        
        if not results:
            # Try an alternative search endpoint if the first one returned no results
            return _fallback_search_movie(title, client_id, access_token)
            
        # Return the first result
        return results[0]
        
    except requests.exceptions.RequestException as e:
        print(f"Error searching Simkl for '{title}': {e}")
        return None
        
def _fallback_search_movie(title, client_id, access_token):
    """Fallback search method using the general search endpoint."""
    print(f"Trying fallback search for '{title}'")
    
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {'q': title, 'type': 'movie'}
    
    try:
        response = requests.get(f'{SIMKL_API_BASE_URL}/search/all', headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"Fallback search failed with status: {response.status_code}")
            return None
            
        results = response.json()
        print(f"Fallback search found {len(results) if results else 0} results")
        
        # Filter for movies only
        movie_results = [r for r in results if r.get('type') == 'movie']
        
        if movie_results:
            print(f"Found movie in fallback search: {movie_results[0].get('title', title)}")
            return movie_results[0]
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error in fallback search: {e}")
        return None

# Modify functions to accept client_id and access_token
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
    if not client_id or not access_token:
        print("Error: Missing Client ID or Access Token for mark_as_watched.")
        return False
    
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    # According to Simkl API, we need to send a specific format for adding to history
    data = {
        'movies': [
            {
                'ids': {
                    'simkl': simkl_id
                },
                'status': 'completed'  # Explicitly mark as completed
            }
        ]
    }
    
    print(f"Sending request to mark movie ID {simkl_id} as watched with data: {data}")
    
    try:
        # According to Simkl API, the endpoint for adding to history is /sync/history
        response = requests.post(f'{SIMKL_API_BASE_URL}/sync/history', headers=headers, json=data)
        
        # Print response details for debugging
        print(f"Response status code: {response.status_code}")
        try:
            print(f"Response JSON: {response.json()}")
        except:
            print(f"Response text: {response.text}")
        
        # Check for successful response
        if response.status_code == 201 or response.status_code == 200:
            print(f"Successfully marked movie ID {simkl_id} as watched")
            return True
        else:
            print(f"Failed to mark movie as watched. Status code: {response.status_code}")
            response.raise_for_status()
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error marking Simkl ID {simkl_id} as watched: {e}")
    
    return False

def get_movie_details(simkl_id, client_id, access_token):
    """Get detailed movie information from Simkl including runtime if available."""
    if not client_id or not access_token or not simkl_id:
        return None
        
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    try:
        response = requests.get(f'{SIMKL_API_BASE_URL}/movies/{simkl_id}', headers=headers)
        response.raise_for_status()
        movie_details = response.json()
        return movie_details
    except requests.exceptions.RequestException as e:
        print(f"Error getting movie details for ID {simkl_id}: {e}")
        return None

# --- Authentication Functions --- #

def get_device_code(client_id):
    """Initiates the device authentication flow."""
    if not client_id:
        print("Error: Missing Client ID for get_device_code.")
        return None
    url = f"{SIMKL_API_BASE_URL}/oauth/pin?client_id={client_id}"
    headers = {'Content-Type': 'application/json'}
    try:
        # Simkl device auth uses GET
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if "user_code" in data and "verification_url" in data and "device_code" in data:
            return data # Should contain user_code, verification_url, device_code, interval, expires_in
        else:
            print(f"Error: Unexpected response format from Simkl device code endpoint: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error getting device code: {e}")
        # Print response body if available for more details
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            try:
                print(f"Response body: {e.response.json()}")
            except requests.exceptions.JSONDecodeError:
                print(f"Response body: {e.response.text}")
    return None

def poll_for_token(client_id, user_code, interval, expires_in):
    """Polls Simkl to check if the user has authorized the device."""
    if not client_id or not user_code:
        print("Error: Missing arguments for poll_for_token.")
        return None

    # Construct URL using USER_CODE in the path
    url = f"{SIMKL_API_BASE_URL}/oauth/pin/{user_code}?client_id={client_id}"
    headers = {
        'Content-Type': 'application/json',
        'simkl-api-key': client_id
    }

    print(f"Polling Simkl for authorization using user code: {user_code}")
    print("Waiting for user authorization (this may take a minute)...")
    
    # Give the user some time to navigate to the site and enter the code before starting to poll
    print("Please go to the Simkl site and enter the code shown above.")
    time.sleep(10)  # Initial 10 second delay to allow user to open browser and navigate
    
    start_time = time.time()
    poll_count = 0
    
    while time.time() - start_time < expires_in:
        poll_count += 1
        try:
            response = requests.get(url, headers=headers)
            
            # Parse response if possible
            response_data = None
            try:
                response_data = response.json()
            except ValueError:
                print(f"Warning: Non-JSON response: {response.text}")
            
            # Check response status and content
            if response.status_code == 200:
                if not response_data:
                    print("Warning: Empty response with status 200")
                    time.sleep(interval)
                    continue
                    
                # Check for success
                if response_data.get('result') == 'OK' and 'access_token' in response_data:
                    print("✓ Authorization successful!")
                    return response_data
                elif response_data.get('result') == 'KO':
                    print("✗ Authorization denied by user")
                    return None
                else:
                    # Still waiting
                    if poll_count % 3 == 0:  # Show message every 3 polls to reduce spam
                        print(f"Still waiting for authorization... ({int(time.time() - start_time)}s elapsed)")
                    time.sleep(interval)
            
            elif response.status_code == 400:
                # Likely pending
                if poll_count % 10 == 0:  # Show dot every 10 polls to reduce spam
                    print(".", end="", flush=True)
                time.sleep(interval)
                
            elif response.status_code == 404:
                print("✗ Device code expired or not found")
                return None
                
            else:
                print(f"Unexpected status code: {response.status_code}")
                if response_data:
                    print(f"Response data: {response_data}")
                time.sleep(interval)
                
        except requests.exceptions.RequestException as e:
            print(f"Network error while polling: {str(e)}")
            # Brief pause before retrying after error
            time.sleep(2)

    print("\n✗ Authentication timed out")
    return None

def authenticate(client_id):
    """Handles the full device authentication flow."""
    if not client_id:
        print("Error: Client ID is required for authentication.")
        return None

    # 1. Get device code
    print("Requesting device code from Simkl...")
    device_info = get_device_code(client_id)
    if not device_info:
        print("Failed to get device code.")
        return None

    # Extract details safely
    user_code = device_info.get('user_code')
    verification_url = device_info.get('verification_url')
    # Use a longer interval for polling (10 seconds instead of default 5)
    interval = max(device_info.get('interval', 5), 10)  
    # Ensure a long timeout (at least 15 minutes)
    expires_in = max(device_info.get('expires_in', 900), 900)  

    if not all([user_code, verification_url]):
        print("Error: Incomplete device information received.")
        return None

    print("\n" + "=" * 60)
    print(f"Please go to: {verification_url}")
    print(f"And enter the code: {user_code}")
    print("=" * 60 + "\n")

    # 2. Poll for token
    access_token_info = poll_for_token(client_id, user_code, interval, expires_in)

    if access_token_info and 'access_token' in access_token_info:
        token = access_token_info['access_token']
        print("\n✓ Authentication complete! Access token received.")
        print(f"To skip authentication next time, add this to your .env file:")
        print(f"SIMKL_ACCESS_TOKEN={token}")
        return token
    else:
        print("\n✗ Authentication process failed or timed out.")
        print("If you didn't have enough time to authenticate, try running the script again.")
        return None