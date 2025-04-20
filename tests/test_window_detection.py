# tests/test_window_detection.py
import pytest
import platform

# Import the functions to test
from simkl_scrobbler.window_detection import parse_movie_title, is_video_player, VIDEO_PLAYER_EXECUTABLES

# --- Tests for parse_movie_title ---

@pytest.mark.parametrize("window_title, expected_title", [
    # Basic movie titles
    ("The Matrix (1999) - VLC media player", "The Matrix (1999)"),
    ("Inception.mkv - mpv", "Inception"),
    ("My Movie Title - MPC-HC", "My Movie Title"),
    ("Dune Part Two [Playing] - PotPlayer", "Dune Part Two"), # Handle PotPlayer status
    ("Some.Movie.2023.1080p.BluRay.x264-GROUP.mkv", "Some Movie (2023)"), # Guessit parsing
    ("Movie Title", "Movie Title"), # Title without player info

    # Titles that should be rejected (return None)
    ("VLC media player", None), # Just the player
    ("mpv", None), # Just the player
    ("MyDocument.txt - Notepad", None), # Non-video file
    ("Website Title - Google Chrome", None), # Browser
    ("File Explorer", None), # OS window
    ("setup.py - VS Code", None), # Code editor
    ("Official download of VLC media player", None), # Web page title (should be rejected by is_movie check)
    ("mpv py", None), # From the bug report
    ("trakt-scrobbler: Scrobbler for trakt tv...", None), # From the bug report
])
def test_parse_movie_title_various(window_title, expected_title):
    """Test parse_movie_title with various inputs."""
    # Simulate window_info dict for context
    # We need a dummy process_name that is a known player for the function to proceed
    # Let's pick one common across platforms if possible, or use platform specific
    player_process = "vlc.exe" if platform.system() == "Windows" else "vlc"
    window_info = {'title': window_title, 'process_name': player_process}

    # Pass the dictionary to the function
    parsed = parse_movie_title(window_info)
    assert parsed == expected_title

def test_parse_movie_title_rejects_non_player_process():
    """Test that parse_movie_title returns None if process_name isn't a player."""
    window_info = {'title': "Some Movie (2024)", 'process_name': 'chrome.exe'}
    assert parse_movie_title(window_info) is None

# --- Tests for is_video_player ---

@pytest.mark.parametrize("process_name, title, expected_result", [
    # Known players (Windows example)
    pytest.param("vlc.exe", "Some Movie - VLC", True, marks=pytest.mark.skipif(platform.system() != "Windows", reason="Windows specific")),
    pytest.param("mpc-hc64.exe", "Another Movie", True, marks=pytest.mark.skipif(platform.system() != "Windows", reason="Windows specific")),
    pytest.param("mpv.exe", "Filename.mkv - mpv", True, marks=pytest.mark.skipif(platform.system() != "Windows", reason="Windows specific")),
    # Known players (Linux example)
    pytest.param("vlc", "Some Movie - VLC", True, marks=pytest.mark.skipif(platform.system() != "Linux", reason="Linux specific")),
    pytest.param("mpv", "Filename.mkv - mpv", True, marks=pytest.mark.skipif(platform.system() != "Linux", reason="Linux specific")),
    # Known players (macOS example)
    pytest.param("VLC", "Some Movie - VLC", True, marks=pytest.mark.skipif(platform.system() != "Darwin", reason="macOS specific")),
    pytest.param("mpv", "Filename.mkv - mpv", True, marks=pytest.mark.skipif(platform.system() != "Darwin", reason="macOS specific")),

    # Non-players
    ("chrome.exe", "Google Chrome", False),
    ("explorer.exe", "File Explorer", False),
    ("code.exe", "script.py - VS Code", False),
    ("browser.py", "My Browser Window", False),

    # Test case sensitivity (should be case-insensitive)
    pytest.param("VLC.EXE", "Some Movie - VLC", True, marks=pytest.mark.skipif(platform.system() != "Windows", reason="Windows specific")),

    # Test the removed title fallback (should now be False)
    ("chrome.exe", "Watching VLC tutorials - Chrome", False),
    ("firefox.exe", "Best mpv settings", False),
])
def test_is_video_player(process_name, title, expected_result):
    """Test is_video_player identification."""
    # Use app_name for macOS testing if needed
    app_name = process_name if platform.system() == "Darwin" else None
    window_info = {'process_name': process_name, 'title': title, 'app_name': app_name}
    assert is_video_player(window_info) == expected_result