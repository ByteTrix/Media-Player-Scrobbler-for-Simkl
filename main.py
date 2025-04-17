# main.py

import time
import os
import sys
from dotenv import load_dotenv
# Update imports to use the new package structure
from simkl_movie_tracker.media_tracker import get_active_window_title, parse_movie_title
# Import specific functions needed, including the new authenticate
from simkl_movie_tracker.simkl_api import search_movie, mark_as_watched, authenticate

def load_configuration():
    """Loads configuration from .env file and validates required variables."""
    load_dotenv() # Load variables from .env file into environment
    client_id = os.getenv("SIMKL_CLIENT_ID")
    # client_secret = os.getenv("SIMKL_CLIENT_SECRET") # No longer needed for device flow
    access_token = os.getenv("SIMKL_ACCESS_TOKEN") # Check if already exists

    # Only client_id is essential to start the auth flow
    if not client_id:
        print("Error: SIMKL_CLIENT_ID not found in environment variables.")
        print("Please ensure you have a .env file with this value.")
        sys.exit(1) # Exit if essential config is missing

    # If no access token, try to authenticate using device flow
    if not access_token:
        print("Access token not found, attempting device authentication...")
        # Call the new authenticate function which only needs client_id
        access_token = authenticate(client_id)
        if access_token:
            print("Authentication successful. You should add the following line to your .env file to avoid authenticating next time:")
            print(f"SIMKL_ACCESS_TOKEN={access_token}")
            # Note: We are not automatically saving it back to .env here for simplicity/security.
        else:
            print("Authentication failed. Please check your client ID and ensure you complete the authorization step on Simkl.")
            sys.exit(1) # Exit if authentication fails

    # Return client_id and the obtained/loaded access_token
    return client_id, access_token

def main():
    print("Starting Simkl Media Tracker...")
    client_id, access_token = load_configuration()

    if not client_id or not access_token:
        print("Exiting due to configuration/authentication issues.")
        return # Exit if config loading/auth failed

    last_marked_title = None
    last_window_title = None

    while True:
        window_title = get_active_window_title()

        if window_title and window_title != last_window_title:
            print(f"Active window title changed: {window_title}")
            last_window_title = window_title
            movie_title = parse_movie_title(window_title)

            if movie_title:
                print(f"Parsed movie title: {movie_title}")

                if movie_title != last_marked_title:
                    # Pass credentials to API functions
                    movie = search_movie(movie_title, client_id, access_token)
                    if movie:
                        try:
                            if 'movie' in movie and 'ids' in movie['movie'] and 'simkl_id' in movie['movie']['ids']:
                                simkl_id = movie['movie']['ids']['simkl_id']
                                print(f"Found Simkl ID: {simkl_id} for '{movie_title}'")
                                # Pass credentials to API functions
                                if mark_as_watched(simkl_id, client_id, access_token):
                                    print(f"Successfully marked '{movie_title}' as watched on Simkl.")
                                    last_marked_title = movie_title
                                else:
                                    # Error message is now printed within mark_as_watched
                                    pass
                            else:
                                print(f"Could not extract Simkl ID for '{movie_title}' from API response structure.")
                        except KeyError as e:
                             print(f"Error accessing key in Simkl API response for '{movie_title}': {e}")
                        except Exception as e:
                             print(f"An unexpected error occurred while processing '{movie_title}': {e}")
                    # else: # Error message now printed within search_movie
                    #    pass
                # else: # Message for already marked is less important now
                #    pass
            # else: # Message for parse failure is less important now
            #    pass
        elif not window_title:
            if last_window_title is not None:
                 print("No active window detected.")
                 last_window_title = None

        time.sleep(30)

if __name__ == "__main__":
    main()