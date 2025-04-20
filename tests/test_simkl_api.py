# tests/test_simkl_api.py
import pytest
import requests
import json # Added missing import
from unittest.mock import patch, MagicMock

# Import the functions to test
from simkl_scrobbler.simkl_api import (
    search_movie,
    mark_as_watched,
    fetch_movie_details,
    is_internet_connected,
    SIMKL_API_URL # Import base URL for clarity
)
import socket # Added missing import for socket patching

# --- Constants ---
TEST_CLIENT_ID = "test_client_id"
TEST_ACCESS_TOKEN = "test_access_token"
TEST_MOVIE_TITLE = "Inception"
TEST_SIMKL_ID = 12345

# --- Fixtures ---

@pytest.fixture
def mock_requests(mocker):
    """Fixture to mock requests.get and requests.post."""
    mock_get = mocker.patch('requests.get')
    mock_post = mocker.patch('requests.post')
    return mock_get, mock_post

# --- Tests for search_movie ---

def test_search_movie_success_found(mock_requests):
    """Test search_movie successfully finds a movie."""
    mock_get, _ = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Simulate Simkl API response structure for movie search
    mock_response.json.return_value = [{
        "title": "Inception",
        "year": 2010,
        "ids": {"simkl": TEST_SIMKL_ID, "imdb": "tt1375666"}
    }]
    mock_get.return_value = mock_response

    result = search_movie(TEST_MOVIE_TITLE, TEST_CLIENT_ID) # Access token not needed for search

    # Check if requests.get was called correctly
    expected_url = f"{SIMKL_API_URL}/search/movie"
    expected_params = {'q': TEST_MOVIE_TITLE, 'extended': 'full'}
    expected_headers = {'simkl-api-key': TEST_CLIENT_ID}
    mock_get.assert_called_once_with(expected_url, headers=expected_headers, params=expected_params, timeout=10)

    # Check the result
    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]['title'] == "Inception"
    assert result[0]['ids']['simkl'] == TEST_SIMKL_ID

def test_search_movie_success_not_found(mock_requests):
    """Test search_movie successfully finds no results."""
    mock_get, _ = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [] # Empty list for no results
    mock_get.return_value = mock_response

    result = search_movie("NonExistentMovieXYZ", TEST_CLIENT_ID)
    assert result == []

def test_search_movie_api_error(mock_requests):
    """Test search_movie handles API errors (e.g., 401)."""
    mock_get, _ = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.reason = "Unauthorized"
    mock_get.return_value = mock_response

    result = search_movie(TEST_MOVIE_TITLE, TEST_CLIENT_ID)
    assert result is None # Should return None on error

def test_search_movie_network_error(mock_requests):
    """Test search_movie handles network errors."""
    mock_get, _ = mock_requests
    mock_get.side_effect = requests.exceptions.RequestException("Network error")

    result = search_movie(TEST_MOVIE_TITLE, TEST_CLIENT_ID)
    assert result is None # Should return None on error

# --- Tests for mark_as_watched ---

def test_mark_as_watched_success(mock_requests):
    """Test mark_as_watched successfully marks a movie."""
    _, mock_post = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Simulate Simkl success response structure
    mock_response.json.return_value = {
        "added": {"movies": 1},
        "not_found": {"movies": []}
    }
    mock_post.return_value = mock_response

    result = mark_as_watched(TEST_SIMKL_ID, TEST_CLIENT_ID, TEST_ACCESS_TOKEN)

    # Check if requests.post was called correctly
    expected_url = f"{SIMKL_API_URL}/sync/history"
    expected_headers = {
        'Authorization': f'Bearer {TEST_ACCESS_TOKEN}',
        'simkl-api-key': TEST_CLIENT_ID,
        'Content-Type': 'application/json'
    }
    expected_data = json.dumps({"movies": [{"ids": {"simkl": TEST_SIMKL_ID}}]})
    mock_post.assert_called_once_with(expected_url, headers=expected_headers, data=expected_data, timeout=15)

    assert result is True

def test_mark_as_watched_failure_not_found(mock_requests):
    """Test mark_as_watched handles 'not found' response."""
    _, mock_post = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 200 # API might return 200 even if item not found
    mock_response.json.return_value = {
        "added": {"movies": 0},
        "not_found": {"movies": [{"ids": {"simkl": TEST_SIMKL_ID}}]}
    }
    mock_post.return_value = mock_response

    result = mark_as_watched(TEST_SIMKL_ID, TEST_CLIENT_ID, TEST_ACCESS_TOKEN)
    assert result is False # Should return False if not added

def test_mark_as_watched_api_error(mock_requests):
    """Test mark_as_watched handles API errors."""
    _, mock_post = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.reason = "Unauthorized"
    mock_post.return_value = mock_response

    result = mark_as_watched(TEST_SIMKL_ID, TEST_CLIENT_ID, TEST_ACCESS_TOKEN)
    assert result is False

def test_mark_as_watched_network_error(mock_requests):
    """Test mark_as_watched handles network errors."""
    _, mock_post = mock_requests
    mock_post.side_effect = requests.exceptions.RequestException("Network error")

    result = mark_as_watched(TEST_SIMKL_ID, TEST_CLIENT_ID, TEST_ACCESS_TOKEN)
    assert result is False

# --- Tests for fetch_movie_details ---

def test_fetch_movie_details_success(mock_requests):
    """Test fetch_movie_details successfully gets details."""
    mock_get, _ = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "title": "Inception",
        "year": 2010,
        "runtime": 148, # Runtime in minutes
        "ids": {"simkl": TEST_SIMKL_ID}
    }
    mock_get.return_value = mock_response

    result = fetch_movie_details(TEST_SIMKL_ID, TEST_CLIENT_ID)

    expected_url = f"{SIMKL_API_URL}/movies/{TEST_SIMKL_ID}"
    expected_params = {'extended': 'full'}
    expected_headers = {'simkl-api-key': TEST_CLIENT_ID}
    mock_get.assert_called_once_with(expected_url, headers=expected_headers, params=expected_params, timeout=10)

    assert result is not None
    assert result['title'] == "Inception"
    assert result['runtime'] == 148

def test_fetch_movie_details_not_found(mock_requests):
    """Test fetch_movie_details handles 404 Not Found."""
    mock_get, _ = mock_requests
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    result = fetch_movie_details(999999, TEST_CLIENT_ID)
    assert result is None

def test_fetch_movie_details_network_error(mock_requests):
    """Test fetch_movie_details handles network errors."""
    mock_get, _ = mock_requests
    mock_get.side_effect = requests.exceptions.RequestException("Network error")

    result = fetch_movie_details(TEST_SIMKL_ID, TEST_CLIENT_ID)
    assert result is None

# --- Tests for is_internet_connected ---

@patch('socket.create_connection')
def test_is_internet_connected_success(mock_socket):
    """Test is_internet_connected returns True when connection succeeds."""
    mock_socket.return_value = MagicMock() # Simulate successful connection
    assert is_internet_connected() is True
    # Check if socket.create_connection was called with expected args
    mock_socket.assert_called_once_with(("8.8.8.8", 53), timeout=3)

@patch('socket.create_connection')
def test_is_internet_connected_failure(mock_socket):
    """Test is_internet_connected returns False when connection fails."""
    mock_socket.side_effect = OSError("Connection failed") # Simulate failure
    assert is_internet_connected() is False