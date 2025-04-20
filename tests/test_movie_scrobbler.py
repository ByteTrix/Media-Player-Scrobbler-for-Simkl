# tests/test_movie_scrobbler.py
import pytest
import time
import pathlib
import json # Added missing import
import logging # Added missing import
from unittest.mock import patch, MagicMock, call

# Import the class to test
from simkl_scrobbler.movie_scrobbler import MovieScrobbler
from simkl_scrobbler.utils.constants import PLAYING, PAUSED, STOPPED

# --- Constants ---
TEST_APP_DATA_DIR = pathlib.Path("./test_app_data") # Use a temporary dir for tests
TEST_CLIENT_ID = "test_client_id"
TEST_ACCESS_TOKEN = "test_access_token"
TEST_MOVIE_TITLE_RAW = "My Movie (2023) - Player"
TEST_MOVIE_TITLE_PARSED = "My Movie (2023)"
TEST_SIMKL_ID = 54321
TEST_MOVIE_NAME_SIMKL = "My Movie Official Name"
TEST_RUNTIME_MIN = 120
TEST_DURATION_SEC = TEST_RUNTIME_MIN * 60

# --- Fixtures ---

@pytest.fixture(autouse=True)
def ensure_test_dir(tmp_path):
    """Ensure the test app data directory exists for each test."""
    # Use pytest's tmp_path fixture for isolated test directories
    global TEST_APP_DATA_DIR
    TEST_APP_DATA_DIR = tmp_path / "app_data"
    TEST_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure playback log file exists for handler creation if needed early
    (TEST_APP_DATA_DIR / 'playback_log.jsonl').touch()
    yield
    # Cleanup happens automatically with tmp_path

@pytest.fixture
def mock_dependencies(mocker):
    """Mock external dependencies of MovieScrobbler."""
    mocks = {
        'is_video_player': mocker.patch('simkl_scrobbler.movie_scrobbler.is_video_player', return_value=True),
        'parse_movie_title': mocker.patch('simkl_scrobbler.movie_scrobbler.parse_movie_title', return_value=TEST_MOVIE_TITLE_PARSED),
        'get_player_position_duration': mocker.patch('simkl_scrobbler.movie_scrobbler.MovieScrobbler.get_player_position_duration', return_value=(None, None)), # Default: no position data
        # Mock the *imported* mark_as_watched in movie_scrobbler module
        'mark_as_watched': mocker.patch('simkl_scrobbler.movie_scrobbler.mark_as_watched', return_value=True),
        # Mock the *imported* is_internet_connected in movie_scrobbler module
        'is_internet_connected': mocker.patch('simkl_scrobbler.movie_scrobbler.is_internet_connected', return_value=True),
        'MediaCache': mocker.patch('simkl_scrobbler.movie_scrobbler.MediaCache'),
        'BacklogCleaner': mocker.patch('simkl_scrobbler.movie_scrobbler.BacklogCleaner'),
        'time_sleep': mocker.patch('time.sleep'), # Mock sleep to speed up tests
        'time_time': mocker.patch('time.time'), # Mock time for predictable timing
        'RotatingFileHandler': mocker.patch('logging.handlers.RotatingFileHandler') # Mock logger handler
    }
    # Configure mock instances for Cache and Backlog
    mocks['MediaCache'].return_value.get.return_value = {} # Default: cache miss
    mocks['MediaCache'].return_value.set.return_value = None
    mocks['BacklogCleaner'].return_value.add.return_value = None
    mocks['BacklogCleaner'].return_value.get_pending.return_value = []
    mocks['BacklogCleaner'].return_value.remove.return_value = None

    # Setup mock time to advance
    start_time = time.time() # Get real start time once
    # Use a list to manage side effects more predictably
    time_side_effects = [start_time + i * 0.1 for i in range(200)] # Pre-generate more time values
    mocks['time_time'].side_effect = time_side_effects

    return mocks

@pytest.fixture
def scrobbler(mock_dependencies):
    """Fixture to create a MovieScrobbler instance with mocked dependencies."""
    # Use the tmp_path provided by ensure_test_dir fixture implicitly
    instance = MovieScrobbler(
        app_data_dir=TEST_APP_DATA_DIR,
        client_id=TEST_CLIENT_ID,
        access_token=TEST_ACCESS_TOKEN
    )
    # Attach mocks for easier access in tests if needed
    instance.mocks = mock_dependencies
    # Ensure playback logger uses mocked handler and doesn't log to console during tests
    instance.playback_logger = MagicMock(spec=logging.Logger)
    instance.playback_logger.info = MagicMock()
    instance.playback_logger.warning = MagicMock()
    instance.playback_logger.error = MagicMock()
    return instance

# --- Helper Function ---
def create_window_info(title=TEST_MOVIE_TITLE_RAW, process="vlc.exe"):
    return {'title': title, 'process_name': process}

# --- Test Cases ---

def test_scrobbler_init(scrobbler):
    """Test MovieScrobbler initialization."""
    assert scrobbler.app_data_dir == TEST_APP_DATA_DIR
    assert scrobbler.client_id == TEST_CLIENT_ID
    assert scrobbler.access_token == TEST_ACCESS_TOKEN
    assert scrobbler.currently_tracking is None
    assert scrobbler.state == STOPPED
    # Check if mocks were called during init
    scrobbler.mocks['MediaCache'].assert_called_once_with(app_data_dir=TEST_APP_DATA_DIR)
    scrobbler.mocks['BacklogCleaner'].assert_called_once_with(app_data_dir=TEST_APP_DATA_DIR, backlog_file="backlog.json", threshold_days=30)
    # Check logger handler setup attempt (mocked)
    # scrobbler.mocks['RotatingFileHandler'].assert_called_once() # This might be too strict

def test_process_window_starts_tracking(scrobbler, mock_dependencies):
    """Test processing a valid player window starts tracking."""
    window_info = create_window_info()
    # Reset time mock side effect for this test
    start_real_time = time.time()
    mock_dependencies['time_time'].side_effect = [start_real_time, start_real_time + 0.1, start_real_time + 0.2] # Provide enough values

    result = scrobbler.process_window(window_info)

    mock_dependencies['is_video_player'].assert_called_once_with(window_info)
    mock_dependencies['parse_movie_title'].assert_called_once_with(TEST_MOVIE_TITLE_RAW)
    assert scrobbler.currently_tracking == TEST_MOVIE_TITLE_PARSED
    assert scrobbler.state == PLAYING
    assert scrobbler.start_time == start_real_time # Check against mocked time
    assert scrobbler.last_update_time == scrobbler.start_time
    assert result == {"title": TEST_MOVIE_TITLE_PARSED, "simkl_id": None} # No ID known yet
    # Check if playback log was called for start/update
    assert scrobbler.playback_logger.info.call_count >= 1 # Should log start/progress


def test_process_window_stops_tracking_non_player(scrobbler, mock_dependencies):
    """Test processing a non-player window stops tracking."""
    # Start tracking first
    scrobbler.process_window(create_window_info())
    assert scrobbler.currently_tracking is not None
    scrobbler.playback_logger.reset_mock() # Reset logger mock after start

    # Now process a non-player window
    mock_dependencies['is_video_player'].return_value = False
    non_player_window = {'title': 'Browser', 'process_name': 'chrome.exe'}
    result = scrobbler.process_window(non_player_window)

    mock_dependencies['is_video_player'].assert_called_with(non_player_window)
    assert scrobbler.currently_tracking is None
    assert scrobbler.state == STOPPED
    assert result is None
    # Check stop tracking log event
    assert any("stop_tracking" in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)


def test_process_window_stops_tracking_unparsed_title(scrobbler, mock_dependencies):
    """Test processing a player window with unparsable title stops tracking."""
     # Start tracking first
    scrobbler.process_window(create_window_info())
    assert scrobbler.currently_tracking is not None
    scrobbler.playback_logger.reset_mock()

    # Now process a window where title parsing fails
    mock_dependencies['parse_movie_title'].return_value = None
    unparsed_window = create_window_info(title="Just Player Name")
    result = scrobbler.process_window(unparsed_window)

    mock_dependencies['parse_movie_title'].assert_called_with("Just Player Name")
    assert scrobbler.currently_tracking is None
    assert scrobbler.state == STOPPED
    assert result is None
    # Check stop tracking log event
    assert any("stop_tracking" in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)


def test_process_window_media_change(scrobbler, mock_dependencies):
    """Test switching to a different movie stops old tracking and starts new."""
    # Reset time mock
    start_real_time = time.time()
    mock_dependencies['time_time'].side_effect = [start_real_time, start_real_time + 0.1, start_real_time + 0.2, start_real_time + 0.3] # More time values

    # Start tracking movie 1
    mock_dependencies['parse_movie_title'].return_value = "Movie 1"
    scrobbler.process_window(create_window_info(title="Movie 1 - Player"))
    mock_dependencies['parse_movie_title'].assert_called_with("Movie 1 - Player")
    first_start_time = scrobbler.start_time
    assert scrobbler.currently_tracking == "Movie 1"
    scrobbler.playback_logger.reset_mock() # Reset logger mock

    # Process window for movie 2
    mock_dependencies['parse_movie_title'].return_value = "Movie 2 Title"
    scrobbler.process_window(create_window_info(title="Movie 2 Title - Player"))
    mock_dependencies['parse_movie_title'].assert_called_with("Movie 2 Title - Player")

    assert scrobbler.currently_tracking == "Movie 2 Title"
    assert scrobbler.start_time > first_start_time # New start time
    assert scrobbler.state == PLAYING
    # Check stop tracking log event for movie 1
    assert any("stop_tracking" in call_args[0][0] and '"movie_title_raw": "Movie 1"' in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)


def test_update_tracking_accumulates_time(scrobbler, mock_dependencies):
    """Test that watch time accumulates correctly when playing."""
    start_real_time = time.time()
    # Precise time mocking for accumulation check
    time_calls = [
        start_real_time,      # Call in process_window -> _start_new_movie
        start_real_time + 0.1,# Call in process_window -> _update_tracking (sets last_update_time)
        start_real_time + 10.1 # Call in _update_tracking (10s later)
    ]
    mock_dependencies['time_time'].side_effect = time_calls + [start_real_time + 10.2] # Add extra for safety

    # Start tracking
    scrobbler.process_window(create_window_info())
    initial_watch_time = scrobbler.watch_time
    assert initial_watch_time == 0
    first_update_time = scrobbler.last_update_time # Should be time_calls[1]

    # Update tracking after 10 seconds (relative to the first update time)
    scrobbler._update_tracking(create_window_info())

    # Check accumulated time (should be approx 10 seconds)
    # It's calculated based on the difference between the two _update_tracking calls
    expected_diff = time_calls[2] - first_update_time
    assert scrobbler.watch_time == pytest.approx(expected_diff)
    assert scrobbler.watch_time == pytest.approx(10.0) # Should be ~10s


def test_update_tracking_detects_pause(scrobbler, mock_dependencies):
    """Test pause detection based on window title."""
    # Start playing
    scrobbler.process_window(create_window_info())
    assert scrobbler.state == PLAYING
    scrobbler.playback_logger.reset_mock()

    # Update with a paused title
    paused_window = create_window_info(title="My Movie (2023) [Paused] - Player")
    scrobbler._update_tracking(paused_window)

    assert scrobbler.state == PAUSED
    # Check state change log
    assert any("state_change" in call_args[0][0] and '"state": "paused"' in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)


def test_update_tracking_uses_position_duration(scrobbler, mock_dependencies):
    """Test that position and duration from player are used."""
    mock_pos_dur = (300, TEST_DURATION_SEC) # 300s position, 120min duration
    mock_dependencies['get_player_position_duration'].return_value = mock_pos_dur

    # Start tracking
    scrobbler.process_window(create_window_info())
    # Update tracking to get position
    scrobbler._update_tracking(create_window_info())

    mock_dependencies['get_player_position_duration'].assert_called()
    assert scrobbler.current_position_seconds == mock_pos_dur[0]
    assert scrobbler.total_duration_seconds == mock_pos_dur[1]

def test_calculate_percentage_priority(scrobbler, mock_dependencies):
    """Test percentage calculation prioritizes position over accumulated time."""
    # Setup: Known duration, position, and some accumulated time
    scrobbler.total_duration_seconds = 600 # 10 min
    scrobbler.current_position_seconds = 300 # 5 min (position)
    scrobbler.watch_time = 120 # 2 min (accumulated)

    # Calculate preferring position
    percentage_pos = scrobbler._calculate_percentage(use_position=True)
    assert percentage_pos == pytest.approx(50.0) # 300 / 600

    # Calculate preferring accumulated (or as fallback)
    percentage_acc = scrobbler._calculate_percentage(use_accumulated=True)
    assert percentage_acc == pytest.approx(20.0) # 120 / 600

    # Calculate without preference (should default to accumulated if position not requested)
    percentage_default = scrobbler._calculate_percentage()
    assert percentage_default == pytest.approx(20.0) # Checks accumulated path

    # Explicitly test fallback when position is None but duration known
    scrobbler.current_position_seconds = None
    percentage_fallback_pos_req = scrobbler._calculate_percentage(use_position=True) # Tries pos, fails, falls back
    assert percentage_fallback_pos_req == pytest.approx(20.0)

    # Test when duration is unknown
    scrobbler.total_duration_seconds = None
    scrobbler.current_position_seconds = 300 # Position known but no duration
    assert scrobbler._calculate_percentage(use_position=True) is None
    assert scrobbler._calculate_percentage(use_accumulated=True) is None


def test_completion_threshold_reached_marks_finished(scrobbler, mock_dependencies):
    """Test that reaching the completion threshold triggers mark_as_finished."""
    # Setup: Known ID and duration, position close to end
    scrobbler.simkl_id = TEST_SIMKL_ID
    scrobbler.movie_name = TEST_MOVIE_NAME_SIMKL
    scrobbler.total_duration_seconds = TEST_DURATION_SEC # 120 min
    scrobbler.completion_threshold = 80 # 80%

    # Mock position to be 85% complete
    pos_85_percent = TEST_DURATION_SEC * 0.85
    mock_dependencies['get_player_position_duration'].return_value = (pos_85_percent, TEST_DURATION_SEC)

    # Mock time to advance past the check interval
    start_real_time = time.time()
    time_calls = [
        start_real_time,      # Start tracking
        start_real_time + 0.1,# First update (gets position)
        start_real_time + 6.0 # Second update (after 5s check interval)
    ]
    mock_dependencies['time_time'].side_effect = time_calls + [start_real_time + 6.1] # Add extra

    # Start tracking
    scrobbler.process_window(create_window_info())
    scrobbler.playback_logger.reset_mock() # Reset logger

    # First update (gets position)
    scrobbler._update_tracking(create_window_info())
    assert not scrobbler.completed
    mock_dependencies['mark_as_watched'].assert_not_called()

    # Second update (should trigger check and mark as finished)
    scrobbler._update_tracking(create_window_info())

    assert scrobbler.completed # Should be marked complete now
    # Check the *mocked* mark_as_watched was called
    mock_dependencies['mark_as_watched'].assert_called_once_with(TEST_SIMKL_ID, TEST_CLIENT_ID, TEST_ACCESS_TOKEN)
    # Check log event
    assert any("completion_threshold_reached" in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)
    assert any("marked_as_finished_api_success" in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)


def test_mark_as_finished_offline_adds_to_backlog(scrobbler, mock_dependencies):
    """Test mark_as_finished adds to backlog when offline."""
    mock_dependencies['is_internet_connected'].return_value = False
    # Need to access the *mock instance* of BacklogCleaner
    mock_backlog_instance = scrobbler.mocks['BacklogCleaner'].return_value
    mock_backlog_add = mock_backlog_instance.add
    scrobbler.backlog_cleaner = mock_backlog_instance # Ensure scrobbler uses the mock instance

    # Manually call mark_as_finished (simulating threshold reached offline)
    # Need to ensure the scrobbler has the ID/title set
    scrobbler.simkl_id = TEST_SIMKL_ID
    scrobbler.movie_name = TEST_MOVIE_NAME_SIMKL
    result = scrobbler.mark_as_finished(TEST_SIMKL_ID, TEST_MOVIE_NAME_SIMKL)

    assert result is False
    assert scrobbler.completed is False # Not marked complete if offline
    mock_dependencies['mark_as_watched'].assert_not_called() # API call shouldn't happen
    mock_backlog_add.assert_called_once_with(TEST_SIMKL_ID, TEST_MOVIE_NAME_SIMKL)
    # Check log event
    assert any("marked_as_finished_offline" in call_args[0][0] for call_args in scrobbler.playback_logger.info.call_args_list)


def test_cache_movie_info_updates_state(scrobbler, mock_dependencies):
    """Test caching movie info updates the scrobbler's state if tracking."""
    # Start tracking (simkl_id and movie_name are None initially)
    scrobbler.process_window(create_window_info())
    assert scrobbler.currently_tracking == TEST_MOVIE_TITLE_PARSED # Ensure tracking started
    assert scrobbler.simkl_id is None
    assert scrobbler.movie_name is None
    assert scrobbler.total_duration_seconds is None

    # Need to access the *mock instance* of MediaCache
    mock_cache_instance = scrobbler.mocks['MediaCache'].return_value
    scrobbler.media_cache = mock_cache_instance # Ensure scrobbler uses the mock instance

    # Cache info (e.g., from search callback)
    scrobbler.cache_movie_info(
        title=TEST_MOVIE_TITLE_PARSED, # Title being tracked
        simkl_id=TEST_SIMKL_ID,
        movie_name=TEST_MOVIE_NAME_SIMKL,
        runtime=TEST_RUNTIME_MIN
    )

    # Check if scrobbler state was updated
    assert scrobbler.simkl_id == TEST_SIMKL_ID
    assert scrobbler.movie_name == TEST_MOVIE_NAME_SIMKL
    assert scrobbler.total_duration_seconds == TEST_DURATION_SEC

    # Check if cache was called
    expected_cache_data = {
        "simkl_id": TEST_SIMKL_ID,
        "movie_name": TEST_MOVIE_NAME_SIMKL,
        "duration_seconds": TEST_DURATION_SEC
    }
    mock_cache_instance.set.assert_called_once_with(TEST_MOVIE_TITLE_PARSED, expected_cache_data)

# TODO: Add tests for backlog processing (process_backlog)
# TODO: Add tests for player-specific integrations if they exist and have logic
# TODO: Add tests for playback logging (_log_playback_event) - maybe check file content?