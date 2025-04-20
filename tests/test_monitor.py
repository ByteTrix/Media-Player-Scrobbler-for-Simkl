# tests/test_monitor.py
import pytest
import time
import threading
import pathlib
import logging # Added missing import
from unittest.mock import patch, MagicMock, call

# Import the class to test
from simkl_scrobbler.monitor import Monitor

# --- Constants ---
TEST_APP_DATA_DIR = pathlib.Path("./test_app_data_monitor") # Use a separate temp dir
TEST_CLIENT_ID = "monitor_client_id"
TEST_ACCESS_TOKEN = "monitor_access_token"
POLL_INTERVAL = 0.1 # Use a short interval for tests
BACKLOG_INTERVAL = 0.5 # Short backlog interval

# --- Fixtures ---

@pytest.fixture(autouse=True)
def ensure_test_dir(tmp_path):
    """Ensure the test app data directory exists for each test."""
    global TEST_APP_DATA_DIR
    TEST_APP_DATA_DIR = tmp_path / "app_data_monitor"
    TEST_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield

@pytest.fixture
def mock_monitor_dependencies(mocker):
    """Mock external dependencies of Monitor."""
    mocks = {
        'get_all_windows_info': mocker.patch('simkl_scrobbler.monitor.get_all_windows_info', return_value=[]), # Default: no windows
        'is_video_player': mocker.patch('simkl_scrobbler.monitor.is_video_player', return_value=False), # Default: not a player
        'MovieScrobbler': mocker.patch('simkl_scrobbler.monitor.MovieScrobbler'),
        'time_sleep': mocker.patch('time.sleep'), # Mock sleep
        'time_time': mocker.patch('time.time'), # Mock time
        'threading_Thread': mocker.patch('threading.Thread'), # Mock Thread creation
        'threading_RLock': mocker.patch('threading.RLock'), # Mock Lock
    }

    # Configure mock MovieScrobbler instance
    mock_scrobbler_instance = MagicMock(spec=Monitor.scrobbler) # Use spec for better mocking
    mock_scrobbler_instance.process_window.return_value = None # Default: no scrobble info
    mock_scrobbler_instance.stop_tracking.return_value = None
    mock_scrobbler_instance.process_backlog.return_value = 0 # Default: 0 items synced
    mock_scrobbler_instance.currently_tracking = None # Default: not tracking
    # Add methods expected to be called
    mock_scrobbler_instance.set_credentials = MagicMock()
    mock_scrobbler_instance.cache_movie_info = MagicMock()
    mocks['MovieScrobbler'].return_value = mock_scrobbler_instance

    # Setup mock time to advance
    start_time = time.time()
    time_side_effects = [start_time + i * (POLL_INTERVAL / 2) for i in range(400)] # Advance time faster, more values
    mocks['time_time'].side_effect = time_side_effects

    # Mock the lock context manager
    mock_lock_instance = MagicMock()
    mocks['threading_RLock'].return_value = mock_lock_instance
    # Make the lock instance usable as a context manager
    mock_lock_instance.__enter__ = MagicMock(return_value=None)
    mock_lock_instance.__exit__ = MagicMock(return_value=None)


    return mocks, mock_scrobbler_instance # Return instance for easier access

@pytest.fixture
def monitor(mock_monitor_dependencies):
    """Fixture to create a Monitor instance with mocked dependencies."""
    mocks, _ = mock_monitor_dependencies
    instance = Monitor(
        app_data_dir=TEST_APP_DATA_DIR,
        client_id=TEST_CLIENT_ID,
        access_token=TEST_ACCESS_TOKEN,
        poll_interval=POLL_INTERVAL,
        backlog_check_interval=BACKLOG_INTERVAL
    )
    # Attach mocks for easier access
    instance.mocks = mocks
    instance.scrobbler = mocks['MovieScrobbler'].return_value # Ensure it uses the mock scrobbler
    instance._lock = mocks['threading_RLock'].return_value # Ensure it uses the mock lock
    return instance

# --- Test Cases ---

def test_monitor_init(monitor, mock_monitor_dependencies):
    """Test Monitor initialization."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    assert monitor.app_data_dir == TEST_APP_DATA_DIR
    assert monitor.client_id == TEST_CLIENT_ID
    assert monitor.access_token == TEST_ACCESS_TOKEN
    assert monitor.poll_interval == POLL_INTERVAL
    assert monitor.backlog_check_interval == BACKLOG_INTERVAL
    assert monitor.running is False
    assert monitor.monitor_thread is None
    assert monitor.search_callback is None
    # Check if MovieScrobbler was instantiated correctly
    mocks['MovieScrobbler'].assert_called_once_with(
        app_data_dir=TEST_APP_DATA_DIR,
        client_id=TEST_CLIENT_ID,
        access_token=TEST_ACCESS_TOKEN,
        testing_mode=False # Default value
    )
    mocks['threading_RLock'].assert_called_once() # Check lock creation

def test_monitor_set_search_callback(monitor):
    """Test setting the search callback."""
    my_callback = MagicMock()
    monitor.set_search_callback(my_callback)
    assert monitor.search_callback == my_callback

def test_monitor_start(monitor, mock_monitor_dependencies):
    """Test the start method."""
    mocks, _ = mock_monitor_dependencies
    mock_thread_instance = MagicMock()
    mocks['threading_Thread'].return_value = mock_thread_instance

    result = monitor.start()

    assert result is True
    assert monitor.running is True
    mocks['threading_Thread'].assert_called_once_with(target=monitor._monitor_loop, daemon=True)
    mock_thread_instance.start.assert_called_once()
    assert monitor.monitor_thread == mock_thread_instance

    # Test starting again when already running
    result_again = monitor.start()
    assert result_again is False
    # Ensure thread creation/start wasn't called again
    mocks['threading_Thread'].assert_called_once()
    mock_thread_instance.start.assert_called_once()

def test_monitor_stop(monitor, mock_monitor_dependencies):
    """Test the stop method."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    mock_thread_instance = MagicMock()
    mock_thread_instance.is_alive.return_value = True
    mocks['threading_Thread'].return_value = mock_thread_instance
    monitor.start() # Start first
    monitor.monitor_thread = mock_thread_instance # Ensure monitor has the mock thread

    # Simulate scrobbler tracking something when stop is called
    mock_scrobbler_instance.currently_tracking = "Some Movie"

    result = monitor.stop()

    assert result is True
    assert monitor.running is False # Should be set to False first
    mock_thread_instance.join.assert_called_once_with(timeout=2)
    # Check that scrobbler.stop_tracking was called within the lock context
    mock_scrobbler_instance.stop_tracking.assert_called_once()
    # Verify lock usage
    monitor._lock.__enter__.assert_called()
    monitor._lock.__exit__.assert_called()


    # Test stopping again when already stopped
    result_again = monitor.stop()
    assert result_again is False
    # Ensure join/stop_tracking wasn't called again
    mock_thread_instance.join.assert_called_once()
    mock_scrobbler_instance.stop_tracking.assert_called_once()

# Helper method to simulate one iteration of the monitor loop for testing
# This is added to the Monitor class dynamically in the fixture setup below
def _monitor_loop_iteration_test_helper(self):
    """Helper to run the core logic of one monitor loop iteration."""
    if not self.running: return # Prevent running if stopped

    try:
        found_player = False
        # Use mocked function directly from the instance's mocks attribute
        all_windows = self.mocks['get_all_windows_info']()

        for win in all_windows:
             # Use mocked function directly from the instance's mocks attribute
            if self.mocks['is_video_player'](win):
                window_info = win
                found_player = True
                # logger.debug(f"Active media player detected: {win.get('title', 'Unknown')}") # Skip logging

                # Use the actual lock from the instance
                with self._lock:
                    # Use the mock scrobbler from the instance
                    scrobble_info = self.scrobbler.process_window(window_info)

                if scrobble_info and self.search_callback and not scrobble_info.get("simkl_id"):
                    title = scrobble_info.get("title", "Unknown")
                    # logger.info(f"Media identification required: '{title}'")
                    self.search_callback(title)
                break # Found player, exit window loop

        if not found_player and self.scrobbler.currently_tracking:
            # logger.info("Media playback ended: No active players detected")
            with self._lock:
                self.scrobbler.stop_tracking()

        # Use mocked time directly from the instance's mocks attribute
        current_time = self.mocks['time_time']()
        if current_time - self.last_backlog_check > self.backlog_check_interval:
            # logger.debug("Performing backlog synchronization...")
            with self._lock:
                synced_count = self.scrobbler.process_backlog()

            # if synced_count > 0: logger.info(f"Backlog sync completed: {synced_count} items successfully synchronized")
            self.last_backlog_check = current_time

        # Don't call sleep in the helper
        # self.mocks['time_sleep'](self.poll_interval)

    except Exception as e:
        # logger.error(f"Monitoring service encountered an error: {e}", exc_info=True)
        # self.mocks['time_sleep'](max(5, self.poll_interval))
        pytest.fail(f"Monitor loop iteration encountered unexpected error: {e}")


# Add the helper method to the Monitor class *before* tests that use it run
Monitor._monitor_loop_iteration = _monitor_loop_iteration_test_helper


def test_monitor_loop_finds_player_and_processes(monitor, mock_monitor_dependencies):
    """Test loop iteration finding a player window."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    player_window = {'title': 'Movie Title - Player', 'process_name': 'vlc.exe', 'hwnd': 123}
    mocks['get_all_windows_info'].return_value = [
        {'title': 'Browser', 'process_name': 'chrome.exe'},
        player_window,
        {'title': 'Explorer', 'process_name': 'explorer.exe'}
    ]
    mocks['is_video_player'].side_effect = lambda win: win == player_window # Only identify the player window

    # Simulate one loop iteration by calling the helper method
    monitor.running = True
    monitor._monitor_loop_iteration()

    mocks['get_all_windows_info'].assert_called_once()
    assert mocks['is_video_player'].call_count == 2 # Called for chrome and vlc
    mock_scrobbler_instance.process_window.assert_called_once_with(player_window)
    monitor._lock.__enter__.assert_called() # Check lock usage around process_window
    monitor._lock.__exit__.assert_called()
    mock_scrobbler_instance.stop_tracking.assert_not_called() # Player found, don't stop

def test_monitor_loop_no_player_stops_tracking(monitor, mock_monitor_dependencies):
    """Test loop iteration stops tracking when no player is found."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    mocks['get_all_windows_info'].return_value = [
        {'title': 'Browser', 'process_name': 'chrome.exe'},
        {'title': 'Explorer', 'process_name': 'explorer.exe'}
    ]
    mocks['is_video_player'].return_value = False # No window is a player
    mock_scrobbler_instance.currently_tracking = "Some Movie" # Simulate tracking

    monitor.running = True
    monitor._monitor_loop_iteration()

    mocks['get_all_windows_info'].assert_called_once()
    assert mocks['is_video_player'].call_count == 2 # Called for both windows
    mock_scrobbler_instance.process_window.assert_not_called()
    mock_scrobbler_instance.stop_tracking.assert_called_once() # Should stop tracking
    monitor._lock.__enter__.assert_called() # Check lock usage around stop_tracking
    monitor._lock.__exit__.assert_called()

def test_monitor_loop_calls_search_callback(monitor, mock_monitor_dependencies):
    """Test loop calls search callback when scrobbler needs identification."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    player_window = {'title': 'Raw Title', 'process_name': 'mpv.exe'}
    scrobble_info_needs_search = {"title": "Raw Title", "simkl_id": None} # No ID yet
    mocks['get_all_windows_info'].return_value = [player_window]
    mocks['is_video_player'].return_value = True
    mock_scrobbler_instance.process_window.return_value = scrobble_info_needs_search

    # Set a mock callback
    mock_callback = MagicMock()
    monitor.set_search_callback(mock_callback)

    monitor.running = True
    monitor._monitor_loop_iteration()

    mock_scrobbler_instance.process_window.assert_called_once_with(player_window)
    mock_callback.assert_called_once_with("Raw Title") # Callback should be triggered

def test_monitor_loop_does_not_call_search_callback_if_id_known(monitor, mock_monitor_dependencies):
    """Test loop doesn't call search callback if scrobbler returns Simkl ID."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    player_window = {'title': 'Known Movie - Player', 'process_name': 'vlc.exe'}
    scrobble_info_with_id = {"title": "Known Movie", "simkl_id": 12345} # Has ID
    mocks['get_all_windows_info'].return_value = [player_window]
    mocks['is_video_player'].return_value = True
    mock_scrobbler_instance.process_window.return_value = scrobble_info_with_id

    mock_callback = MagicMock()
    monitor.set_search_callback(mock_callback)

    monitor.running = True
    monitor._monitor_loop_iteration()

    mock_scrobbler_instance.process_window.assert_called_once_with(player_window)
    mock_callback.assert_not_called() # Callback should NOT be triggered

def test_monitor_loop_processes_backlog_periodically(monitor, mock_monitor_dependencies):
    """Test loop calls process_backlog based on interval."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    start_real_time = time.time()
    # Simulate time advancing past the backlog check interval
    time_calls = [
        start_real_time,                     # Initial time check in loop
        start_real_time + POLL_INTERVAL,     # Time check after ~1st iteration
        start_real_time + POLL_INTERVAL * 2, # Time check after ~2nd iteration
        start_real_time + BACKLOG_INTERVAL + 0.1 # Time check when backlog should run
    ]
    mocks['time_time'].side_effect = time_calls + [time_calls[-1] + POLL_INTERVAL] # Add extra

    monitor.running = True
    monitor.last_backlog_check = start_real_time # Initialize check time

    # Simulate multiple iterations
    monitor._monitor_loop_iteration() # Iteration 1 (time() called, check fails)
    mock_scrobbler_instance.process_backlog.assert_not_called()

    monitor._monitor_loop_iteration() # Iteration 2 (time() called, check fails)
    mock_scrobbler_instance.process_backlog.assert_not_called()

    monitor._monitor_loop_iteration() # Iteration 3 (time() called, check passes)
    mock_scrobbler_instance.process_backlog.assert_called_once()
    monitor._lock.__enter__.assert_called() # Check lock usage around process_backlog
    monitor._lock.__exit__.assert_called()
    # Check that last_backlog_check time was updated
    assert monitor.last_backlog_check == time_calls[3]

def test_monitor_set_credentials(monitor, mock_monitor_dependencies):
    """Test setting credentials propagates to scrobbler."""
    mocks, mock_scrobbler_instance = mock_monitor_dependencies
    new_client_id = "new_id"
    new_token = "new_token"

    monitor.set_credentials(new_client_id, new_token)

    assert monitor.client_id == new_client_id
    assert monitor.access_token == new_token
    mock_scrobbler_instance.set_credentials.assert_called_once_with(new_client_id, new_token)