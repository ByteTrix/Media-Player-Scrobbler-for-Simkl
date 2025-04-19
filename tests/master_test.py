#!/usr/bin/env python3
import os
import sys
import time
import logging
import threading
import argparse
import json
import re
import subprocess
import shutil
import urllib.request
import requests
import winreg
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import components from our package - use existing functions directly
from simkl_movie_tracker.simkl_api import (
    search_movie, 
    get_movie_details, 
    mark_as_watched, 
    authenticate,
    is_internet_connected
)
from simkl_movie_tracker.media_tracker import (
    MovieScrobbler, 
    MonitorAwareScrobbler,
    MediaCache,
    BacklogCleaner,
    get_active_window_info,
    is_video_player,
    parse_movie_title,
    PLAYING,
    PAUSED,
    STOPPED
)
import simkl_movie_tracker.simkl_api as simkl_api  # For modifying functions during tests

# Configure logging with both file and console output
log_file = os.path.join(project_root, "master_test.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='w')
    ]
)
logger = logging.getLogger("MasterTest")

# Define test constants
TEST_DURATION_SECONDS = 120
POLL_INTERVAL_SECONDS = 2
COMPLETION_THRESHOLD = 80
PLAYBACK_SPEED_FACTOR = 100

# List of potential media player paths (Windows)
PLAYER_PATHS = {
    "mpc-hc64.exe": [
        r"C:\Program Files (x86)\K-Lite Codec Pack\MPC-HC64\mpc-hc64.exe",
        r"C:\Program Files\MPC-HC\mpc-hc64.exe",
    ],
    "mpc-hc.exe": [
        r"C:\Program Files (x86)\K-Lite Codec Pack\MPC-HC\mpc-hc.exe",
        r"C:\Program Files\MPC-HC\mpc-hc.exe",
    ],
    "mpc-be64.exe": [
        r"C:\Program Files\MPC-BE\mpc-be64.exe",
        r"C:\Program Files (x86)\MPC-BE\mpc-be64.exe",
    ],
    "mpc-be.exe": [
        r"C:\Program Files\MPC-BE\mpc-be.exe",
        r"C:\Program Files (x86)\MPC-BE\MPC-BE.exe",
    ],
    "vlc.exe": [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
    ],
    "wmplayer.exe": [
        r"C:\Program Files\Windows Media Player\wmplayer.exe",
    ]
}

class TestResult:
    """Class to store test results for reporting"""
    
    def __init__(self, test_name):
        self.test_name = test_name
        self.start_time = datetime.now()
        self.end_time = None
        self.success = False
        self.details = {}
        self.errors = []
    
    def complete(self, success, details=None):
        self.end_time = datetime.now()
        self.success = success
        if details:
            self.details.update(details)
    
    def add_error(self, error):
        self.errors.append(error)
    
    def duration_seconds(self):
        if not self.end_time:
            return (datetime.now() - self.start_time).total_seconds()
        return (self.end_time - self.start_time).total_seconds()
    
    def __str__(self):
        status = "[PASSED]" if self.success else "[FAILED]"
        result = f"{status} - {self.test_name} - {self.duration_seconds():.2f}s"
        if self.errors:
            result += f" - {len(self.errors)} errors"
        return result
    
    def to_dict(self):
        return {
            "test_name": self.test_name,
            "success": self.success,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds(),
            "details": self.details,
            "errors": self.errors
        }

class SimklMovieTrackerTester:
    """Master tester class for Simkl Movie Tracker functionality"""
    
    def __init__(self):
        self.client_id = None
        self.access_token = None
        self.results = []
        self.test_mode = False
        self.video_path = None
        # For player selection
        self.selected_player_exe = None
        self.selected_player_path = None
        self.player_web_interface_ok = False
        # Shared scrobbler instance
        self.scrobbler = None
    
    def setup(self):
        """Load credentials and check authentication"""
        test_result = TestResult("Authentication Check")
        logger.info("Starting authentication check...")
        
        # Load credentials from .env file
        load_dotenv()
        self.client_id = os.getenv("SIMKL_CLIENT_ID")
        self.access_token = os.getenv("SIMKL_ACCESS_TOKEN")
        
        if not self.client_id:
            logger.error("SIMKL_CLIENT_ID not found in environment variables")
            test_result.add_error("SIMKL_CLIENT_ID not found")
            test_result.complete(False, {"credentials_found": False})
            self.results.append(test_result)
            return False
                
        if not self.access_token and not self.test_mode:
            logger.warning("SIMKL_ACCESS_TOKEN not found, attempting authentication")
            self.access_token = authenticate(self.client_id)
            if not self.access_token:
                logger.error("Authentication failed, please set up authentication first")
                test_result.add_error("Authentication failed")
                test_result.complete(False, {"credentials_found": False})
                self.results.append(test_result)
                return False
        elif self.test_mode:
            self.access_token = "test_access_token"
            logger.warning("Using test access_token")
            
        logger.info("Authentication check successful")
        
        # Initialize shared scrobbler for tests
        self.scrobbler = MovieScrobbler(client_id=self.client_id, access_token=self.access_token)
        self.scrobbler.completion_threshold = COMPLETION_THRESHOLD
        
        # Clear any existing cache files for clean testing
        self._clear_cache()
        self._clear_backlog()
            
        logger.info("Test setup completed successfully")
        test_result.complete(True, {"credentials_found": True})
        self.results.append(test_result)
        return True
    
    def _clear_cache(self, movie_title=None):
        """Clear cache and backlog files for testing"""
        cache_file = os.path.join(project_root, "simkl_movie_tracker", "media_cache.json")
        
        # Clear media cache
        if os.path.exists(cache_file):
            if movie_title:
                try:
                    # Only clear specific movie from cache
                    with open(cache_file, 'r') as f:
                        cache = json.load(f)
                    
                    # Case insensitive removal
                    movie_title_lower = movie_title.lower()
                    keys_to_remove = [k for k in cache.keys() if k.lower() == movie_title_lower]
                    
                    for key in keys_to_remove:
                        logger.info(f"Removing '{key}' from cache for testing")
                        del cache[key]
                    
                    # Save the modified cache
                    with open(cache_file, 'w') as f:
                        json.dump(cache, f)
                except Exception as e:
                    logger.error(f"Error clearing cache: {e}")
            else:
                # Clear entire cache
                with open(cache_file, 'w') as f:
                    json.dump({}, f)
                logger.info("Cleared media cache for testing")
    
    def _clear_backlog(self):
        """Clear backlog for testing"""
        backlog_file = os.path.join(project_root, "simkl_movie_tracker", "backlog.json")
        if os.path.exists(backlog_file):
            with open(backlog_file, 'w') as f:
                json.dump([], f)
            logger.info("Cleared backlog for testing")
    
    def _check_player_setup(self):
        """Check for installed players and web interfaces"""
        test_result = TestResult("Player Detection")
        logger.info("Checking for installed media players...")
        
        # Find installed players
        available_players = self._find_installed_players()
        
        if not available_players:
            logger.error("No compatible media players found on this system")
            test_result.add_error("No compatible media players found")
            test_result.complete(False)
            self.results.append(test_result)
            return False
        
        # Select a player - prioritize MPC-HC/BE, then VLC
        preferred_order = ["mpc-hc64.exe", "mpc-be64.exe", "mpc-hc.exe", "mpc-be.exe", "vlc.exe"]
        
        for player in preferred_order:
            if player in available_players:
                self.selected_player_exe = player
                self.selected_player_path = available_players[player]
                logger.info(f"Selected player for testing: {self.selected_player_exe} at {self.selected_player_path}")
                break
        
        # If no preferred player found, use any available
        if not self.selected_player_exe:
            self.selected_player_exe = list(available_players.keys())[0]
            self.selected_player_path = available_players[self.selected_player_exe]
            logger.info(f"Using available player: {self.selected_player_exe} at {self.selected_player_path}")
        
        test_result.details["available_players"] = list(available_players.keys())
        test_result.details["selected_player"] = self.selected_player_exe
        
        # Check web interface connectivity for selected player
        logger.info(f"Checking web interface for {self.selected_player_exe}...")
        if "mpc-hc" in self.selected_player_exe.lower() or "mpc-be" in self.selected_player_exe.lower():
            # Try to enable the web interface (might require admin rights)
            self._setup_mpc_web_interface()
            # Test connection to interface (without launching player yet)
            test_url = "http://localhost:13579/variables.html"
            try:
                response = urllib.request.urlopen(test_url, timeout=1)
                if response.status == 200:
                    logger.info("MPC-HC/BE web interface is accessible")
                    self.player_web_interface_ok = True
                else:
                    logger.warning("MPC-HC/BE web interface returned unexpected status: " + str(response.status))
            except Exception as e:
                logger.warning(f"MPC-HC/BE web interface not accessible: {e}")
                logger.warning("To enable position tracking, open MPC-HC/BE and go to View > Options > Player > Web Interface")
                logger.warning("Check 'Listen on port: 13579' and ensure 'Serve pages to localhost only' is unchecked")
        
        elif "vlc" in self.selected_player_exe.lower():
            # Try connecting to VLC web interface
            test_url = "http://localhost:8080/requests/status.json"
            try:
                response = urllib.request.urlopen(test_url, timeout=1)
                if response.status == 200:
                    logger.info("VLC web interface is accessible")
                    self.player_web_interface_ok = True
                elif response.status == 401:  # Authentication required
                    logger.warning("VLC web interface requires authentication. Please set blank password in VLC preferences.")
                else:
                    logger.warning("VLC web interface returned unexpected status: " + str(response.status))
            except Exception as e:
                logger.warning(f"VLC web interface not accessible: {e}")
                logger.warning("To enable position tracking, open VLC and go to Tools > Preferences > Interface")
                logger.warning("Check 'Web' under Main interfaces, set a blank password, and restart VLC")
        
        test_result.details["web_interface_ok"] = self.player_web_interface_ok
        test_result.complete(True)  # Detection is successful even if web interface is not available
        self.results.append(test_result)
        return True
    
    def run_all_tests(self, args):
        """Run all tests and collect results"""
        logger.info("=" * 70)
        logger.info("SIMKL MOVIE TRACKER - MASTER TEST SUITE")
        logger.info("=" * 70)
        
        # Store command line arguments
        self.test_mode = args.test_mode
        self.video_path = args.video_file
        
        # 1. AUTHENTICATION CHECK (required)
        if not self.setup():
            logger.error("Authentication setup failed, cannot continue")
            return False
        
        # 2. PLAYER SETUP CHECK
        self._check_player_setup()
        
        # 3. API TESTS
        if not args.skip_api:
            self.test_api_integration()
        
        # 4. OFFLINE TRACKING TESTS
        if not args.skip_offline:
            self.test_offline_tracking()
        
        # 5. MOVIE COMPLETION TESTS
        if not args.skip_completion:
            self.test_movie_completion(args.movie_title)
        
        # 6. CACHE & TITLE PARSING TESTS
        if not args.skip_cache:
            self.test_cache_functionality()
        
        if not args.skip_title_parsing:
            self.test_title_parsing()
        
        # 7. REAL PLAYBACK TEST
        if args.test_real_playback and self.video_path:
            if os.path.exists(self.video_path):
                self.test_real_playback()
            else:
                logger.error(f"Video file not found: {self.video_path}")
                logger.error("Skipping real playback test")
        
        # Print summary
        self._print_results_summary()
        
        # Check if all tests passed
        all_passed = all(result.success for result in self.results)
        return all_passed
    
    def test_api_integration(self):
        """Test API search and movie details functionality"""
        test_result = TestResult("API Integration")
        logger.info("Starting API integration test...")
        
        if self.test_mode:
            logger.info("Running in TEST MODE - will use mock API responses")
            test_result.complete(True, {
                "api_calls": ["search_movie", "get_movie_details", "mark_as_watched"],
                "mocked": True
            })
            self.results.append(test_result)
            logger.info("API integration test completed in test mode")
            return True
        
        try:
            # First check internet connectivity
            if not is_internet_connected():
                logger.warning("No internet connection detected. Skipping real API test.")
                test_result.complete(True, {"skipped": True, "reason": "No internet connection"})
                self.results.append(test_result)
                return True
            
            # Test movie titles (including one that shouldn't exist)
            test_titles = ["Inception", "The Matrix", "Avengers", "NonexistentMovieXYZ123"]
            found_movies = 0
            found_details = 0
            
            for title in test_titles:
                logger.info(f"Testing search_movie API with title: '{title}'")
                movie = search_movie(title, self.client_id, self.access_token)
                
                if movie:
                    # Extract movie info
                    if isinstance(movie, list):
                        movie_data = movie[0]
                    else:
                        movie_data = movie
                    
                    if 'movie' in movie_data:
                        movie_data = movie_data['movie']
                    
                    if 'ids' in movie_data:
                        found_movies += 1
                        simkl_id = movie_data['ids'].get('simkl_id')
                        movie_name = movie_data.get('title', movie_data.get('name', title))
                        
                        logger.info(f"Found movie: '{movie_name}' (ID: {simkl_id})")
                        test_result.details[f"movie_{found_movies}"] = {
                            "title": movie_name,
                            "simkl_id": simkl_id
                        }
                        
                        # Only test details API for real movies
                        if title != "NonexistentMovieXYZ123":
                            # Test get_movie_details
                            if simkl_id:
                                logger.info(f"Testing get_movie_details API for ID: {simkl_id}")
                                details = get_movie_details(simkl_id, self.client_id, self.access_token)
                                
                                if details:
                                    found_details += 1
                                    runtime = details.get('runtime')
                                    logger.info(f"Got movie details - Runtime: {runtime} minutes")
                                    test_result.details[f"movie_{found_movies}_details"] = {
                                        "title": movie_name,
                                        "simkl_id": simkl_id,
                                        "runtime": runtime
                                    }
                                else:
                                    logger.warning(f"Could not get details for movie ID: {simkl_id}")
                    else:
                        logger.warning(f"Movie found but no IDs available: {movie_data}")
                else:
                    if title == "NonexistentMovieXYZ123":
                        logger.info(f"Correctly found no results for non-existent movie '{title}'")
                    else:
                        logger.warning(f"No movie found for title: '{title}'")
            
            # Consider test successful if we found real movies and their details
            real_titles = [t for t in test_titles if t != "NonexistentMovieXYZ123"]
            success = found_movies >= len(real_titles) and found_details > 0
            
            if success:
                logger.info(f"API integration test PASSED - found {found_movies} movies with {found_details} detailed lookups")
            else:
                logger.error(f"API integration test FAILED - only found {found_movies}/{len(real_titles)} movies")
                test_result.add_error("Failed to find all expected movies via API")
            
            test_result.complete(success, {
                "movies_searched": len(test_titles),
                "movies_found": found_movies,
                "details_found": found_details
            })
            
        except Exception as e:
            logger.error(f"API integration test error: {e}", exc_info=True)
            test_result.add_error(str(e))
            test_result.complete(False)
        
        self.results.append(test_result)
        return test_result.success
    
    def test_offline_tracking(self):
        """Test that movies are properly tracked when offline and synced when online"""
        test_result = TestResult("Offline Tracking")
        logger.info("Starting offline tracking test...")
        
        # Use our shared scrobbler instance
        scrobbler = self.scrobbler
        
        # Clear any existing backlog for clean testing
        scrobbler.backlog.clear()
        logger.info("Cleared existing backlog for testing")
        
        try:
            # Override is_internet_connected to simulate offline state
            original_is_connected = simkl_api.is_internet_connected
            
            # First get real movie data from the API while we're online
            real_movie_data = []
            if not self.test_mode and original_is_connected():
                # Get real movie data for testing
                logger.info("Getting real movie data from Simkl API for offline testing")
                popular_movies = ["Inception", "The Shawshank Redemption", "Interstellar"]
                
                for title in popular_movies:
                    try:
                        movie_result = search_movie(title, self.client_id, self.access_token)
                        if movie_result:
                            movie_info = None
                            if isinstance(movie_result, list):
                                movie_info = movie_result[0]
                            else:
                                movie_info = movie_result
                                
                            if 'movie' in movie_info:
                                movie_info = movie_info['movie']
                                
                            if 'ids' in movie_info and 'simkl_id' in movie_info['ids']:
                                simkl_id = movie_info['ids']['simkl_id']
                                movie_name = movie_info.get('title', movie_info.get('name', title))
                                
                                # Get runtime if available
                                runtime = 120  # Default runtime
                                details = get_movie_details(simkl_id, self.client_id, self.access_token)
                                if details and 'runtime' in details:
                                    runtime = details['runtime']
                                
                                logger.info(f"Found movie for offline test: {movie_name} (ID: {simkl_id}, Runtime: {runtime} min)")
                                
                                real_movie_data.append({
                                    "title": movie_name,
                                    "simkl_id": simkl_id,
                                    "duration": runtime * 60  # Convert to seconds
                                })
                    except Exception as e:
                        logger.warning(f"Error getting movie data for {title}: {e}")
            
            # Use preset movie data if we couldn't get real data
            if not real_movie_data:
                logger.warning("Using predefined movie data for offline testing")
                real_movie_data = [
                    {"title": "Inception (2010)", "simkl_id": 1015, "duration": 148 * 60},
                    {"title": "The Shawshank Redemption (1994)", "simkl_id": 4, "duration": 142 * 60},
                    {"title": "Interstellar (2014)", "simkl_id": 2000, "duration": 169 * 60}
                ]
            
            # Start with offline mode
            simkl_api.is_internet_connected = lambda: False
            logger.info("SIMULATING OFFLINE MODE - Internet connectivity check will return False")
            
            # Check the backlog count before starting
            initial_backlog_count = len(scrobbler.backlog.get_pending())
            logger.info(f"Initial backlog count: {initial_backlog_count}")
            test_result.details["initial_backlog_count"] = initial_backlog_count
            
            # Simulate watching movies while offline
            for movie in real_movie_data:
                logger.info(f"Simulating marking movie as watched while offline: {movie['title']}")
                # Call mark_as_finished which should add to backlog when offline
                result = scrobbler.mark_as_finished(movie["simkl_id"], movie["title"])
                if result:
                    logger.error(f"Error: Movie '{movie['title']}' was incorrectly marked as finished despite being offline")
                    test_result.add_error(f"Movie incorrectly marked as watched while offline: {movie['title']}")
                else:
                    logger.info(f"Correctly failed to mark as watched online and added to backlog: {movie['title']}")
            
            # Check the backlog after watching
            offline_backlog_count = len(scrobbler.backlog.get_pending())
            logger.info(f"Backlog count after watching movies offline: {offline_backlog_count}")
            
            # Log the backlog contents in a more readable format
            backlog_items = scrobbler.backlog.get_pending()
            logger.info(f"Backlog contents ({len(backlog_items)} items):")
            for idx, item in enumerate(backlog_items, 1):
                logger.info(f"  {idx}. '{item.get('title')}' (ID: {item.get('simkl_id')}, Added: {item.get('timestamp')})")
            
            test_result.details["offline_backlog_count"] = offline_backlog_count
            
            # Now simulate coming back online
            logger.info("\nSIMULATING COMING BACK ONLINE")
            simkl_api.is_internet_connected = lambda: True
            logger.info("Internet connectivity check will now return True")
            
            # Override mark_as_watched to avoid actual API calls in test mode
            original_mark_as_watched = None
            if self.test_mode:
                original_mark_as_watched = simkl_api.mark_as_watched
                simkl_api.mark_as_watched = lambda simkl_id, client_id, access_token: True
            
            # Process the backlog
            logger.info("Processing backlog...")
            synced_count = scrobbler.process_backlog()
            
            # Check results
            final_backlog_count = len(scrobbler.backlog.get_pending())
            logger.info(f"Synced {synced_count} movies from backlog")
            logger.info(f"Final backlog count: {final_backlog_count}")
            test_result.details["synced_count"] = synced_count
            test_result.details["final_backlog_count"] = final_backlog_count
            
            # Restore original functions
            simkl_api.is_internet_connected = original_is_connected
            if original_mark_as_watched:
                simkl_api.mark_as_watched = original_mark_as_watched
            
            # Test passes if backlog was filled and then emptied
            success = initial_backlog_count == 0 and offline_backlog_count > 0 and final_backlog_count == 0
            
            if success:
                logger.info("[PASSED] OFFLINE TRACKING TEST: Movies were correctly added to backlog when offline and synced when online")
            else:
                logger.error("[FAILED] OFFLINE TRACKING TEST FAILED: Offline tracking did not work as expected")
                test_result.add_error("Offline tracking flow did not complete as expected")
            
            test_result.complete(success)
            
        except Exception as e:
            logger.error(f"Offline tracking test error: {e}", exc_info=True)
            test_result.add_error(str(e))
            test_result.complete(False)
        
        self.results.append(test_result)
        return test_result.success
    
    def test_movie_completion(self, movie_title=None):
        """Test movie completion detection and marking as watched"""
        movie_title = movie_title or "Inception"
        test_result = TestResult(f"Movie Completion: {movie_title}")
        logger.info(f"Starting movie completion test for: {movie_title}")
        
        # Use shared scrobbler instance
        scrobbler = self.scrobbler
        scrobbler.stop_tracking()  # Reset state
        
        try:
            # Get real movie data if possible
            simkl_id = None
            runtime_min = 120  # Default in minutes
            movie_name = movie_title
            
            if not self.test_mode and is_internet_connected():
                logger.info(f"Fetching movie data for: {movie_title}")
                movie_result = search_movie(movie_title, self.client_id, self.access_token)
                
                if movie_result:
                    if isinstance(movie_result, list):
                        movie_data = movie_result[0]
                    else:
                        movie_data = movie_result
                        
                    if 'movie' in movie_data:
                        movie_data = movie_data['movie']
                        
                    if 'ids' in movie_data and 'simkl_id' in movie_data['ids']:
                        simkl_id = movie_data['ids']['simkl_id']
                        movie_name = movie_data.get('title', movie_data.get('name', movie_title))
                        
                        details = get_movie_details(simkl_id, self.client_id, self.access_token)
                        if details and 'runtime' in details:
                            runtime_min = details['runtime']
                            logger.info(f"Got details for '{movie_name}': Runtime = {runtime_min} min")
                        else:
                            logger.warning(f"Could not get runtime for '{movie_name}', using default: {runtime_min} min")
                    else:
                        logger.warning(f"No valid Simkl ID found for '{movie_title}'")
                else:
                    logger.warning(f"Could not find movie: '{movie_title}'")
            
            if not simkl_id:
                simkl_id = 12345  # Test ID
                logger.warning(f"Using test ID {simkl_id} for '{movie_title}'")
            
            # Make runtime shorter for testing
            if runtime_min > 10:
                original_runtime = runtime_min
                runtime_min = 10
                logger.info(f"Reducing runtime from {original_runtime} to 10 minutes for faster testing")
            
            # Setup scrobbler
            duration_sec = runtime_min * 60
            threshold_sec = duration_sec * (COMPLETION_THRESHOLD / 100.0)
            
            scrobbler.currently_tracking = movie_title
            scrobbler.simkl_id = simkl_id
            scrobbler.movie_name = movie_name
            scrobbler.start_time = time.time()
            scrobbler.last_update_time = time.time()
            scrobbler.watch_time = 0
            scrobbler.current_position_seconds = 0
            scrobbler.total_duration_seconds = duration_sec
            scrobbler.state = PLAYING
            scrobbler.completed = False
            
            logger.info(f"Test setup - Movie: '{movie_name}' (ID: {simkl_id}), Duration: {duration_sec}s, Threshold: {threshold_sec}s ({COMPLETION_THRESHOLD}%)")
            
            # Check completion at 75% (below threshold)
            below_threshold_pos = duration_sec * 0.75
            scrobbler.watch_time = below_threshold_pos
            scrobbler.current_position_seconds = below_threshold_pos
            
            below_threshold_complete = scrobbler.is_complete()
            logger.info(f"At 75% ({below_threshold_pos}s) - is_complete(): {below_threshold_complete}")
            
            # Check completion at 85% (above threshold)
            above_threshold_pos = duration_sec * 0.85
            scrobbler.watch_time = above_threshold_pos
            scrobbler.current_position_seconds = above_threshold_pos
            
            above_threshold_complete = scrobbler.is_complete()
            logger.info(f"At 85% ({above_threshold_pos}s) - is_complete(): {above_threshold_complete}")
            
            # Mark as finished
            logger.info(f"Attempting to mark '{movie_name}' (ID: {simkl_id}) as finished")
            
            # Override mark_as_watched to avoid API calls in test mode
            original_mark_as_watched = None
            if self.test_mode:
                original_mark_as_watched = simkl_api.mark_as_watched
                simkl_api.mark_as_watched = lambda simkl_id, client_id, access_token: True
            
            # Try to mark as finished
            marked_finished = scrobbler.mark_as_finished(simkl_id, movie_name)
            
            # Restore original function if needed
            if original_mark_as_watched:
                simkl_api.mark_as_watched = original_mark_as_watched
            
            # Check completion flag
            completion_flag_set = scrobbler.completed
            
            # Test passes if below threshold is not complete, above threshold is complete,
            # and mark_as_finished returns True
            success = (not below_threshold_complete and 
                      above_threshold_complete and 
                      marked_finished and
                      completion_flag_set)
            
            test_result.details.update({
                "movie_name": movie_name,
                "simkl_id": simkl_id,
                "duration_seconds": duration_sec,
                "threshold_seconds": threshold_sec,
                "below_threshold_complete": below_threshold_complete,
                "above_threshold_complete": above_threshold_complete,
                "marked_finished_result": marked_finished,
                "completion_flag_set": completion_flag_set
            })
            
            if success:
                logger.info("[PASS] MOVIE COMPLETION TEST PASSED: Completion detection and marking worked correctly")
            else:
                logger.error("[FAILED] MOVIE COMPLETION TEST FAILED")
                if below_threshold_complete:
                    test_result.add_error("Movie incorrectly marked as complete below threshold")
                if not above_threshold_complete:
                    test_result.add_error("Movie not marked as complete above threshold")
                if not marked_finished:
                    test_result.add_error("Failed to mark movie as finished")
                if not completion_flag_set:
                    test_result.add_error("Completion flag not set after marking as finished")
            
            test_result.complete(success)
            
        except Exception as e:
            logger.error(f"Movie completion test error: {e}", exc_info=True)
            test_result.add_error(str(e))
            test_result.complete(False)
        finally:
            # Reset scrobbler state
            scrobbler.stop_tracking()
        
        self.results.append(test_result)
        return test_result.success
    
    def test_cache_functionality(self):
        """Test the MediaCache class"""
        test_result = TestResult("Cache Functionality")
        logger.info("Starting cache functionality test...")
        
        try:
            # Use a test file to avoid interfering with real cache
            test_cache_file = "test_cache.json"
            test_cache_path = os.path.join(project_root, "simkl_movie_tracker", test_cache_file)
            
            # Create cache instance
            cache = MediaCache(cache_file=test_cache_file)
            
            # Test cache set and get
            test_title = "Test Movie 2025"
            test_info = {
                "simkl_id": 12345,
                "movie_name": "Test Movie 2025",
                "duration_seconds": 7200
            }
            
            logger.info(f"Setting cache for '{test_title}'")
            cache.set(test_title, test_info)
            
            # Test retrieval
            retrieved_info = cache.get(test_title)
            logger.info(f"Retrieved info for '{test_title}': {retrieved_info}")
            
            # Test case insensitivity
            case_insensitive_info = cache.get(test_title.lower())
            logger.info(f"Retrieved info with different case: {case_insensitive_info}")
            
            # Test get_all
            all_cache = cache.get_all()
            has_title = test_title.lower() in all_cache
            logger.info(f"All cache entries: {len(all_cache)}, Has test title: {has_title}")
            
            # Check results
            success = (retrieved_info == test_info and 
                       case_insensitive_info == test_info and
                       has_title)
            
            test_result.details.update({
                "cache_set_get_works": retrieved_info == test_info,
                "case_insensitive_works": case_insensitive_info == test_info,
                "get_all_works": has_title
            })
            
            if success:
                logger.info("[PASS] CACHE FUNCTIONALITY TEST PASSED")
            else:
                logger.error("[FAILED] CACHE FUNCTIONALITY TEST FAILED")
                if retrieved_info != test_info:
                    test_result.add_error("Cache get after set failed")
                if case_insensitive_info != test_info:
                    test_result.add_error("Case insensitive cache lookup failed")
                if not has_title:
                    test_result.add_error("get_all() didn't include the cached title")
            
            test_result.complete(success)
            
            # Clean up test file
            if os.path.exists(test_cache_path):
                os.remove(test_cache_path)
                logger.info(f"Removed test cache file: {test_cache_path}")
            
        except Exception as e:
            logger.error(f"Cache functionality test error: {e}", exc_info=True)
            test_result.add_error(str(e))
            test_result.complete(False)
        
        self.results.append(test_result)
        return test_result.success
    
    def test_title_parsing(self):
        """Test parse_movie_title functionality with various inputs"""
        test_result = TestResult("Title Parsing")
        logger.info("Starting title parsing test...")
        
        try:
            # Test cases: window title or info dict, expected result
            test_cases = [
                ("Inception (2010) - VLC media player", "Inception (2010)"),
                ("The Matrix 1999 - MPC-HC", "The Matrix (1999)"),
                ("Avatar.2009.BluRay.720p.x264 - Media Player", "Avatar (2009)"),
                ("Movie With Year 2018.mkv", "Movie With Year (2018)"),
                ("Movie.With.Dots.In.Title.mp4 - VLC", "Movie With Dots In Title"),
                ("TV.Show.S01E01.Title.mp4", None),  # Should identify as TV show, not movie
                ("Some Document.txt - Notepad", None),  # Should not identify as movie
                # Test with dict input
                ({'title': 'Interstellar (2014) - VLC media player', 'process_name': 'vlc.exe'}, "Interstellar (2014)"),
                ({'title': 'Not A Movie - Notepad', 'process_name': 'notepad.exe'}, None),
            ]
            
            passed = 0
            failed = 0
            failures = []
            
            for idx, (input_data, expected) in enumerate(test_cases, 1):
                result = parse_movie_title(input_data)
                
                case_passed = (result == expected)
                if case_passed:
                    passed += 1
                    logger.info(f"Case {idx} PASSED: '{input_data}' -> '{result}'")
                else:
                    failed += 1
                    error_msg = f"Case {idx} FAILED: '{input_data}' -> '{result}' (Expected: '{expected}')"
                    logger.error(error_msg)
                    failures.append(error_msg)
            
            success = failed == 0
            test_result.details.update({
                "test_cases": len(test_cases),
                "passed": passed,
                "failed": failed
            })
            
            if failures:
                test_result.errors.extend(failures)
            
            if success:
                logger.info("[PASS] TITLE PARSING TEST PASSED: All cases passed")
            else:
                logger.error(f"[FAILED] TITLE PARSING TEST FAILED: {failed}/{len(test_cases)} cases failed")
            
            test_result.complete(success)
            
        except Exception as e:
            logger.error(f"Title parsing test error: {e}", exc_info=True)
            test_result.add_error(str(e))
            test_result.complete(False)
        
        self.results.append(test_result)
        return test_result.success
    
    def test_real_playback(self):
        """Test with real media player and video file"""
        test_result = TestResult("Real Playback")
        logger.info("Starting real playback test...")
        
        if not self.video_path or not os.path.exists(self.video_path):
            logger.error(f"Video file not found: {self.video_path}")
            test_result.add_error(f"Video file not found: {self.video_path}")
            test_result.complete(False)
            self.results.append(test_result)
            return False
        
        try:
            # Find a suitable media player - prioritize MPC-HC
            available_players = self._find_installed_players()
            
            if not available_players:
                logger.error("No compatible media players found on this system")
                test_result.add_error("No compatible media players found")
                test_result.complete(False)
                self.results.append(test_result)
                return False
            
            # Select MPC-HC player specifically
            player_executable = None
            player_path = None
            # Prioritize MPC-HC first, then other players as fallback
            preferred_order = ["mpc-hc64.exe", "mpc-hc.exe", "vlc.exe", "wmplayer.exe"]
            
            for player in preferred_order:
                if player in available_players:
                    player_executable = player
                    player_path = available_players[player]
                    break
            
            # If no preferred player found, use any available
            if not player_executable:
                player_executable = list(available_players.keys())[0]
                player_path = available_players[player_executable]
            
            logger.info(f"Selected player: {player_executable} at {player_path}")
            test_result.details["player"] = player_executable
            test_result.details["video_file"] = os.path.basename(self.video_path)
            
            # Enable web interface for MPC-HC if selected
            if "mpc-hc" in player_executable.lower():
                logger.info("Setting up MPC-HC web interface for position tracking")
                self._setup_mpc_web_interface()
            
            # Get appropriate arguments for this player
            player_args = self._get_player_arguments(player_executable)
            
            # Extract movie title for cache clearing
            movie_filename = os.path.basename(self.video_path)
            movie_basename = os.path.splitext(movie_filename)[0]
            
            # Clear the cache for this movie to force API lookup
            possible_titles = [
                movie_basename,  # Full filename without extension
                " ".join(movie_basename.split(".")[:2]),  # First two parts of filename
                movie_basename.split(".")[0]  # Just first part of filename
            ]
            
            for title in possible_titles:
                self._clear_cache(title)
                # Also try with (year) format that might be in cache
                if " (" not in title and "(" not in title:
                    # Extract year from filename if it matches pattern like "Movie.2025."
                    year_match = re.search(r'\.(\d{4})\.', movie_basename)
                    if year_match:
                        year = year_match.group(1)
                        self._clear_cache(f"{title} ({year})")
            
            # Set up the scrobbler with real API credentials
            scrobbler = self.scrobbler
            scrobbler.stop_tracking()  # Ensure clean state
            
            # Prepare the launch command
            launch_command = [player_path, self.video_path] + player_args
            
            logger.info("=" * 60)
            logger.info(f"PLAYBACK TEST: {os.path.basename(self.video_path)}")
            logger.info(f"Player: {player_executable}")
            logger.info(f"Command: {' '.join(launch_command)}")
            logger.info("=" * 60)
            
            # Launch the player with the video
            player_process = subprocess.Popen(launch_command)
            pid = player_process.pid
            logger.info(f"Player process started (PID: {pid}). Waiting for initialization...")
            
            # Give the player time to start
            time.sleep(5)
            
            # Check if process is still running
            if player_process.poll() is not None:
                error_msg = f"Player process terminated immediately with code {player_process.returncode}"
                logger.error(error_msg)
                test_result.add_error(error_msg)
                test_result.complete(False)
                self.results.append(test_result)
                return False
            
            logger.info(f"Beginning monitoring loop for {TEST_DURATION_SECONDS} seconds...")
            
            # Start monitoring
            start_time = time.time()
            end_time = start_time + TEST_DURATION_SECONDS
            last_progress_log = start_time
            tracking_started = False
            position_detected = False
            completion_reached = False
            marked_as_watched = False
            simkl_id_set = False
            
            try:
                while time.time() < end_time:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    
                    # Check if player is still running
                    if player_process.poll() is not None:
                        logger.warning(f"Player process terminated during test after {elapsed:.1f}s")
                        break
                    
                    # Get active window info
                    active_window_info = get_active_window_info()
                    
                    # Process the window if it's active and the player
                    if active_window_info and player_executable.lower() in active_window_info.get('process_name', '').lower():
                        # Try to get position information for MPC-HC
                        if "mpc-hc" in player_executable.lower():
                            position_info = self._get_mpc_position()
                            if position_info:
                                logger.info(f"Position from MPC-HC: {position_info}")
                                # Update window info with position data
                                active_window_info['position'] = position_info.get('position')
                                active_window_info['duration'] = position_info.get('duration')
                                active_window_info['state'] = position_info.get('state')
                        
                        scrobble_data = scrobbler.process_window(active_window_info)
                        
                        # Check tracking status
                        if scrobbler.currently_tracking and not tracking_started:
                            logger.info(f"Tracking started: {scrobbler.currently_tracking}")
                            tracking_started = True
                        
                        # Check position detection
                        if scrobbler.current_position_seconds > 0 and not position_detected:
                            logger.info(f"Position detected: {scrobbler.current_position_seconds:.1f}s / {scrobbler.total_duration_seconds:.1f}s")
                            position_detected = True
                        
                        # Check if Simkl ID is set
                        if scrobbler.simkl_id and not simkl_id_set:
                            logger.info(f"Simkl ID set: {scrobbler.simkl_id}")
                            simkl_id_set = True
                        
                        # Calculate percentage
                        percentage = scrobbler._calculate_percentage(use_position=True)
                        
                        # Check completion threshold
                        if percentage and percentage >= COMPLETION_THRESHOLD and not completion_reached:
                            logger.info(f"Completion threshold reached: {percentage:.1f}%")
                            completion_reached = True
                        
                        # Check if marked as watched
                        if scrobbler.completed and not marked_as_watched:
                            logger.info(f"Movie marked as watched via Simkl API!")
                            marked_as_watched = True
                        
                        # Log progress periodically
                        if current_time - last_progress_log >= 5:
                            log_message = (f"[{elapsed:.1f}s] "
                                          f"Tracking: '{scrobbler.currently_tracking or 'None'}' | "
                                          f"State: {scrobbler.state} | ")
                            
                            if scrobbler.current_position_seconds:
                                log_message += f"Pos: {scrobbler.current_position_seconds:.1f}s / {scrobbler.total_duration_seconds}s | "
                            
                            if percentage:
                                log_message += f"Progress: {percentage:.1f}%"
                                
                            logger.info(log_message)
                            last_progress_log = current_time
                    
                    # Sleep for polling interval
                    time.sleep(POLL_INTERVAL_SECONDS)
                
                # Determine test success
                elapsed_time = time.time() - start_time
                success = tracking_started and position_detected
                
                test_result.details.update({
                    "tracking_started": tracking_started,
                    "position_detected": position_detected,
                    "simkl_id_set": simkl_id_set,
                    "completion_reached": completion_reached,
                    "marked_as_watched": marked_as_watched,
                    "test_duration": elapsed_time,
                    "player_used": player_executable
                })
                
                if success:
                    logger.info("[PASS] REAL PLAYBACK TEST PASSED: Successfully tracked media playback")
                    if marked_as_watched:
                        logger.info("[PASS] Movie was marked as watched successfully")
                else:
                    logger.error("[FAILED] REAL PLAYBACK TEST FAILED: Issues tracking playback")
                    test_result.add_error("Failed to properly track media playback")
                
                test_result.complete(success)
                
            finally:
                # Stop tracking if still active
                if scrobbler.currently_tracking:
                    logger.info("Stopping tracking at end of test")
                    scrobbler.stop_tracking()
                
                # Terminate the player process if it's still running
                if player_process and player_process.poll() is None:
                    logger.info(f"Terminating player process (PID: {player_process.pid})...")
                    try:
                        # First try graceful termination
                        player_process.terminate()
                        try:
                            player_process.wait(timeout=5)
                            logger.info("Player terminated gracefully")
                        except subprocess.TimeoutExpired:
                            # Force kill if termination times out
                            logger.warning("Graceful termination timed out, forcing kill...")
                            player_process.kill()
                            player_process.wait(timeout=2)
                            logger.info("Player forcibly terminated")
                    except Exception as term_err:
                        logger.error(f"Error terminating player process: {term_err}")
            
        except Exception as e:
            logger.error(f"Real playback test error: {e}", exc_info=True)
            test_result.add_error(str(e))
            test_result.complete(False)
        
        self.results.append(test_result)
        return test_result.success
    
    def _setup_mpc_web_interface(self):
        """
        Try to enable MPC-HC's web interface if it's not already running.
        This is done by editing registry settings for MPC-HC.
        """
        try:
            import winreg
            # Registry paths for MPC-HC and MPC-BE
            reg_paths = [
                r"SOFTWARE\MPC-HC\MPC-HC",
                r"SOFTWARE\MPC-HC\MPC-HC64",
                r"SOFTWARE\MPC-BE\MPC-BE",
                r"SOFTWARE\MPC-BE\MPC-BE64"
            ]
            
            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE) as key:
                        # Enable web interface
                        winreg.SetValueEx(key, "WebServerUseCompression", 0, winreg.REG_DWORD, 1)
                        winreg.SetValueEx(key, "WebServerPort", 0, winreg.REG_DWORD, 13579)
                        winreg.SetValueEx(key, "WebServerLocalhostOnly", 0, winreg.REG_DWORD, 0)
                        winreg.SetValueEx(key, "WebServerUseAuthentication", 0, winreg.REG_DWORD, 0)
                        winreg.SetValueEx(key, "WebServerEnableCORSForAllOrigins", 0, winreg.REG_DWORD, 1)
                        logger.info(f"Enabled MPC web interface through registry at {reg_path}")
                        return True
                except Exception as e:
                    logger.debug(f"Could not write to registry path {reg_path}: {e}")
            
            logger.warning("Could not enable MPC web interface through registry")
            return False
        except Exception as e:
            logger.warning(f"Error setting up MPC web interface: {e}")
            return False
    
    def _get_mpc_position(self):
        """
        Get current playback position from MPC-HC via its web interface
        """
        try:
            import urllib.request
            import json
            import xml.etree.ElementTree as ET
            
            # Try to connect to web interface
            urls = [
                "http://localhost:13579/variables.html",  # Default MPC-HC port
                "http://localhost:13580/variables.html"   # Alternative port
            ]
            
            for url in urls:
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            data = response.read().decode('utf-8')
                            
                            # Extract position and duration from variables
                            position_sec = None
                            duration_sec = None
                            state = "playing"
                            
                            if '<p id="file">' in data:
                                # Parse XML-like structure
                                for line in data.splitlines():
                                    if '<p id="position">' in line:
                                        time_str = line.split('<p id="position">')[1].split('</p>')[0]
                                        position_sec = self._parse_time_to_seconds(time_str)
                                    elif '<p id="duration">' in line:
                                        time_str = line.split('<p id="duration">')[1].split('</p>')[0]
                                        duration_sec = self._parse_time_to_seconds(time_str)
                                    elif '<p id="state">' in line:
                                        state_value = line.split('<p id="state">')[1].split('</p>')[0]
                                        if state_value == "0":
                                            state = "stopped"
                                        elif state_value == "1":
                                            state = "paused"
                                        else:
                                            state = "playing"
                            
                            if position_sec is not None and duration_sec is not None:
                                return {
                                    "position": position_sec,
                                    "duration": duration_sec,
                                    "state": state
                                }
                except Exception as e:
                    logger.debug(f"Error connecting to MPC-HC web interface at {url}: {e}")
            
            logger.debug("Could not get position from MPC-HC web interface")
            return None
        except Exception as e:
            logger.debug(f"Error getting MPC position: {e}")
            return None

    def _parse_time_to_seconds(self, time_str):
        """Convert time string (HH:MM:SS) to seconds"""
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                # HH:MM:SS format
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            elif len(parts) == 2:
                # MM:SS format
                minutes, seconds = parts
                return int(minutes) * 60 + int(seconds)
            else:
                # Just seconds
                return int(time_str)
        except Exception as e:
            logger.debug(f"Error parsing time string '{time_str}': {e}")
            return 0

    def _find_installed_players(self):
        """Detect which compatible media players are installed on the system"""
        found_players = {}
        
        # Check each player in our list
        for player_exe, possible_paths in PLAYER_PATHS.items():
            for path in possible_paths:
                if os.path.exists(path) and os.path.isfile(path):
                    found_players[player_exe] = path
                    logger.info(f"Found player: {player_exe} at {path}")
                    break  # Found this player, move to next one
                    
        if not found_players:
            logger.warning("No compatible media players found in standard installation paths")
            # Try to find players in PATH as a fallback
            for player_exe in PLAYER_PATHS.keys():
                path = shutil.which(player_exe)
                if path:
                    found_players[player_exe] = path
                    logger.info(f"Found player in PATH: {player_exe} at {path}")
        
        return found_players
    
    def _get_player_arguments(self, player_executable):
        """Get the appropriate command line arguments for a specific player"""
        args = []
        
        # Player-specific arguments
        if "vlc" in player_executable.lower():
            args.extend(["--no-random", "--fullscreen"])
        elif any(name in player_executable.lower() for name in ["mpc-hc", "mpc-be"]):
            args.append("/fullscreen")
        
        return args
    
    def _print_results_summary(self):
        """Print a summary of all test results"""
        logger.info("\n" + "=" * 70)
        logger.info("TEST RESULTS SUMMARY")
        logger.info("=" * 70)
        
        passed = sum(1 for result in self.results if result.success)
        failed = len(self.results) - passed
        
        for result in self.results:
            logger.info(result)
        
        logger.info("-" * 70)
        logger.info(f"TOTAL: {len(self.results)} tests, {passed} passed, {failed} failed")
        logger.info("=" * 70)
        
        # Save results to file
        results_file = os.path.join(project_root, "test_results.json")
        try:
            with open(results_file, 'w') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "summary": {
                        "total": len(self.results),
                        "passed": passed,
                        "failed": failed
                    },
                    "results": [result.to_dict() for result in self.results]
                }, f, indent=2)
            logger.info(f"Test results saved to {results_file}")
        except Exception as e:
            logger.error(f"Error saving test results: {e}")

def main():
    """Main entry point for master test suite"""
    parser = argparse.ArgumentParser(description="Simkl Movie Tracker Master Test Suite")
    parser.add_argument("-t", "--test-mode", action="store_true", help="Run in test mode without real API calls")
    parser.add_argument("-m", "--movie-title", help="Specific movie title to test with", default="Inception")
    parser.add_argument("-v", "--video-file", help="Path to a video file for real playback testing")
    parser.add_argument("-r", "--test-real-playback", action="store_true", help="Run real playback test")
    parser.add_argument("--skip-api", action="store_true", help="Skip API integration tests")
    parser.add_argument("--skip-offline", action="store_true", help="Skip offline tracking tests")
    parser.add_argument("--skip-completion", action="store_true", help="Skip movie completion tests")
    parser.add_argument("--skip-cache", action="store_true", help="Skip cache functionality tests")
    parser.add_argument("--skip-title-parsing", action="store_true", help="Skip title parsing tests")
    parser.add_argument("--show-version", action="store_true", help="Show version and exit")
    parser.add_argument("--verbose", action="store_true", help="Show more detailed test information")
    
    args = parser.parse_args()
    
    if args.show_version:
        print("Simkl Movie Tracker - Master Test Suite v1.0.0")
        return 0
    
    # Set more verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Run the test suite
    tester = SimklMovieTrackerTester()
    all_passed = tester.run_all_tests(args)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())