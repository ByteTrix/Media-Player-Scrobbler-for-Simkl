"""
Regression tests for the PR #175 identification changes merged onto the #192 scrobble lifecycle:
filename parsing, /search/file variants, stale-cache validation, per-file search rate limit,
title-match safety, and tray "Retry Last Scrobble" re-identification.
All Simkl calls are faked; no network access.
"""
import importlib
import os
import pathlib
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent
PACKAGE_ROOT = REPO_ROOT / "simkl_mps"

if "simkl_mps" not in sys.modules:
    package = types.ModuleType("simkl_mps")
    package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["simkl_mps"] = package

media_scrobbler_mod = importlib.import_module("simkl_mps.media_scrobbler")
window_detection = importlib.import_module("simkl_mps.window_detection")
config_manager = importlib.import_module("simkl_mps.config_manager")
simkl_api_mod = importlib.import_module("simkl_mps.simkl_api")
constants = importlib.import_module("simkl_mps.utils.constants")
PLAYING = constants.PLAYING

MediaScrobbler = media_scrobbler_mod.MediaScrobbler


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Default settings in memory, no real network, no Simkl calls unless a test fakes them."""
    settings = dict(config_manager.DEFAULT_SETTINGS)
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(media_scrobbler_mod, "is_internet_connected", lambda: True)
    monkeypatch.setattr(simkl_api_mod, "is_internet_connected", lambda: True)
    monkeypatch.setattr(media_scrobbler_mod, "scrobble",
                        lambda *a, **kw: {"ok": False, "status": None, "error": "network disabled in tests"})
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda *a, **kw: [])
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda *a, **kw: False)
    monkeypatch.setattr(media_scrobbler_mod, "get_show_details", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "search_file",
                        lambda *a, **kw: pytest.fail("unexpected search_file call"))
    monkeypatch.setattr(media_scrobbler_mod, "search_movie",
                        lambda *a, **kw: pytest.fail("unexpected search_movie call"))
    monkeypatch.setattr(media_scrobbler_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(simkl_api_mod, "get_user_settings", lambda *a, **kw: None)

    def _no_network(*args, **kwargs):
        raise AssertionError("Unexpected real HTTP request in test")

    for method in ("get", "post", "delete"):
        monkeypatch.setattr(simkl_api_mod.requests, method, _no_network)
    return settings


def _make_scrobbler(tmp_path):
    return MediaScrobbler(
        app_data_dir=tmp_path,
        client_id="test_client_id",
        access_token="test_access_token",
        testing_mode=True,
    )


def test_failed_movie_search_waits_before_retry(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    now = [1000.0]
    calls = []
    monkeypatch.setattr(media_scrobbler_mod.time, "time", lambda: now[0])
    monkeypatch.setattr(media_scrobbler_mod, "search_movie", lambda *a, **kw: calls.append(a[0]) or None)
    scrobbler._identify_movie("Unmatched Movie")
    now[0] += 5
    scrobbler._identify_movie("Unmatched Movie")
    assert calls == ["Unmatched Movie"]
    now[0] += scrobbler.MOVIE_SEARCH_RETRY_INTERVAL
    scrobbler._identify_movie("Unmatched Movie")
    assert calls == ["Unmatched Movie", "Unmatched Movie"]


def test_retry_cannot_duplicate_synced_identity_but_can_correct_it(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.currently_tracking = "Test Movie"
    scrobbler.media_type = "movie"
    scrobbler.simkl_id = 123
    scrobbler.total_duration_seconds = 1000
    scrobbler.watch_time = 200
    calls = []
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: True)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(scrobbler, "_clear_saved_playback", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: calls.append(a[0]) or {"added": {"movies": 1}})
    assert scrobbler._attempt_add_to_history() is True
    scrobbler.completed = False  # Tray retry preserves the current viewing session
    assert scrobbler._attempt_add_to_history() is False
    assert scrobbler.completed is True
    assert len(calls) == 1
    scrobbler.completed = False
    scrobbler.simkl_id = 456  # Correcting a genuinely wrong identity is still allowed
    assert scrobbler._attempt_add_to_history() is True
    assert len(calls) == 2


def _episode_result(show_title="Show Name", show_id=555, season=1, episode=3, year=2010):
    return {
        "type": "episode",
        "episode": {"title": "Ep", "season": season, "episode": episode, "multipart": False, "ids": {"simkl": 999}},
        "show": {"title": show_title, "year": year, "ids": {"simkl": show_id}},
    }


@pytest.fixture
def posix_host(monkeypatch):
    """Make the path helpers behave as they would on Linux/macOS."""
    monkeypatch.setattr(window_detection.os, "sep", "/")


# --- filename parsing -------------------------------------------------------------------------

@pytest.mark.parametrize("filename, season, episode, episodes, display", [
    ("Show.Name.S01E01E02.1080p.WEB.mkv", 1, 1, [1, 2], "Show Name S01E01-E02"),
    ("Show.Name.S01E01-E03.mkv", 1, 1, [1, 2, 3], "Show Name S01E01-E03"),
])
def test_multi_episode_filenames_parse_instead_of_crashing(filename, season, episode, episodes, display):
    info = window_detection.parse_media_title(filename)
    assert info["type"] == "episode"
    assert info["title"] == "Show Name"
    assert (info["season"], info["episode"], info["episodes"]) == (season, episode, episodes)
    assert info["display_title"] == display


def test_multi_season_pack_keeps_first_season_as_int():
    info = window_detection.parse_media_title("Show.Name.S01-S02.Complete.mkv")
    assert info["title"] == "Show Name"
    assert info["season"] == 1


@pytest.mark.parametrize("filename, title, year", [
    ("Show.Name.E05.mkv", "Show Name", None),
    ("Attack on Titan - S04E28 [1080p].mkv", "Attack on Titan", None),
    ("[SubsPlease] Frieren - 12 (1080p) [ABCD1234].mkv", "Frieren", None),
    ("Doctor.Who.2005.S13E01.mkv", "Doctor Who", 2005),
    ("Shogun.2024.S01E01.mkv", "Shogun", 2024),
])
def test_episode_title_has_no_dangling_markers_or_show_year(filename, title, year):
    info = window_detection.parse_media_title(filename)
    assert info["title"] == title
    assert info.get("year") == year


@pytest.mark.parametrize("filename, title, year", [
    ("F1.The.Movie.2025.1080p.WEB.mkv", "F1 The Movie", 2025),
    ("Blade.Runner.2049.2017.1080p.mkv", "Blade Runner 2049", 2017),
    ("Spider-Man.No.Way.Home.2021.2160p.mkv", "Spider-Man No Way Home", 2021),
    ("www.Torrenting.com - Dune.Part.Two.2024.1080p.mkv", "Dune Part Two", 2024),
    ("1917.2019.1080p.mkv", "1917", 2019),
])
def test_movie_titles_keep_visible_title_text(filename, title, year):
    info = window_detection.parse_media_title(filename)
    assert info["type"] == "movie"
    assert (info["title"], info.get("year")) == (title, year)


@pytest.mark.parametrize("value, expected", [
    (3, 3), ([2, 3], 2), (["x", "4"], 4), ("07", 7), ("abc", None), ("", None),
    (None, None), (True, None), (-1, None), ([], None),
])
def test_coerce_media_number(value, expected):
    assert window_detection.coerce_media_number(value) == expected


# --- cross-platform path handling -------------------------------------------------------------

def test_windows_paths_split_on_posix_host(posix_host):
    path = r"C:\TV\Show Name (2019)\Season 01\Show.Name.S01E03.mkv"
    assert window_detection.media_path_basename(path) == "Show.Name.S01E03.mkv"
    assert window_detection.split_media_path(path)[1] == "TV"
    assert window_detection.media_path_basename(r"\\nas\media\Movie.2020.mkv") == "Movie.2020.mkv"
    assert window_detection.parse_filename_from_path(r"D:\Movies\Dune.2021.mkv") == "Dune (2021)"


def test_posix_filename_with_backslash_is_not_split_on_posix_host(posix_host):
    assert window_detection.media_path_basename("/home/u/odd\\name.mkv") == "odd\\name.mkv"
    assert window_detection.media_path_basename("/home/u/Show.S01E01.mkv") == "Show.S01E01.mkv"


def test_folder_year_from_remote_windows_path(posix_host):
    path = r"D:\Movies\Dune (2021)\Dune.mkv"
    assert MediaScrobbler._year_from_path_context(path) == 2021


def test_folder_year_is_used_for_movies_but_not_episodes(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    movie = scrobbler._expected_media_info_from_filepath(os.path.join("Movies", "Dune (2021)", "Dune.mkv"))
    assert movie["year"] == 2021

    # A season-folder year differs from the show year Simkl returns; it must not reject a match.
    episode_path = os.path.join("TV", "Doctor Who", "Season 13 (2021)", "Doctor.Who.S13E01.mkv")
    episode = scrobbler._expected_media_info_from_filepath(episode_path)
    assert episode.get("year") is None
    assert scrobbler._file_search_result_is_preferred(
        _episode_result("Doctor Who", season=13, episode=1, year=2005), episode_path)


# --- /search/file variant candidates ----------------------------------------------------------

def test_variant_candidates_survive_guessit_lists_and_junk_values(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    multi = scrobbler._file_search_variant_candidates(
        None, {"title": "Show", "type": "episode", "season": [1, 2], "episode": ["3", "x"]})
    assert "Show.S01E03.mkv" in multi

    junk = scrobbler._file_search_variant_candidates(
        None, {"title": "Show", "type": "episode", "season": "abc", "episode": "zz"})
    assert junk == ["Show.mkv"]


def test_variant_candidates_for_multi_episode_file_are_bounded(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    path = os.path.join("TV", "Show.Name.S01E01E02.mkv")
    candidates = scrobbler._file_search_variant_candidates(path, include_original=True)
    assert candidates[0] == path
    assert "Show.Name.S01E01E02.mkv" in candidates
    assert "Show Name.S01E01.mkv" in candidates
    assert len(candidates) <= MediaScrobbler.MAX_FILE_SEARCH_VARIANTS + 1
    assert len({c.lower() for c in candidates}) == len(candidates)


def test_absolute_numbered_episode_accepts_simkl_season_mapping(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    path = "One.Piece.1071.1080p.mkv"
    assert scrobbler._file_search_result_is_preferred(_episode_result("One Piece", season=21, episode=179), path)


def test_explicit_episode_mismatch_is_not_preferred(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    assert not scrobbler._file_search_result_is_preferred(_episode_result(episode=4), "Show.Name.S01E03.mkv")
    assert scrobbler._file_search_result_is_preferred(_episode_result(episode=3), "Show.Name.S01E03.mkv")


# --- title matching ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected, actual", [
    ("Dune Part Two (2024)", "Dune"),
    ("Avatar The Way of Water (2022)", "Avatar"),
    ("Spider Man", "Spider-Man 2"),
    ("Blade Runner 2049 (2017)", "Blade Runner"),
    ("Rocky II", "Rocky"),
])
def test_false_title_matches_are_rejected(expected, actual):
    assert not MediaScrobbler._titles_are_compatible(expected, actual)


@pytest.mark.parametrize("expected, actual", [
    ("The Matrix (1999)", "Matrix"),
    ("Blade Runner 2049 (2017)", "Blade Runner 2049"),
    ("Spider-Man No Way Home (2021)", "Spider-Man: No Way Home"),
    ("Aliens Directors Cut", "Aliens"),
    ("Harry Potter and the Sorcerers Stone", "Harry Potter and the Sorcerer's Stone"),
    ("1917 (2019)", "1917"),
])
def test_equivalent_titles_are_accepted(expected, actual):
    assert MediaScrobbler._titles_are_compatible(expected, actual)


def test_localized_movie_title_requires_matching_alias_not_just_year(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    via_alt = {"movie": {"title": "Der Pate", "year": 1972, "all_titles": ["The Godfather"], "ids": {"simkl": 1}}}
    assert scrobbler._simkl_movie_result_matches_title(via_alt, "The Godfather")

    via_year = {"movie": {"title": "Le Parrain", "year": 1972, "ids": {"simkl": 1}}}
    assert not scrobbler._simkl_movie_result_matches_title(via_year, "The Godfather (1972)")
    unrelated_same_year = {"movie": {"title": "Unrelated Movie", "year": 1972, "ids": {"simkl": 2}}}
    assert not scrobbler._simkl_movie_result_matches_title(unrelated_same_year, "The Godfather (1972)")

    wrong = {"movie": {"title": "Dune", "year": 2021, "ids": {"simkl": 2}}}
    assert not scrobbler._simkl_movie_result_matches_title(wrong, "Dune Part Two (2024)")


def test_rejected_movie_result_is_not_cached_or_tracked(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.currently_tracking = "Dune Part Two (2024)"
    scrobbler.media_type = "movie"
    monkeypatch.setattr(media_scrobbler_mod, "search_movie",
                        lambda *a, **kw: {"movie": {"title": "Dune", "year": 2021, "ids": {"simkl": 2}}})
    scrobbler._identify_movie("Dune Part Two (2024)")
    assert scrobbler.simkl_id is None
    assert scrobbler.media_cache.get("dune part two (2024)") is None


# --- stale cache validation -------------------------------------------------------------------

def test_validated_localized_cache_entry_is_kept(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.media_cache.set("the godfather", {
        "simkl_id": 1, "movie_name": "Der Pate", "type": "movie", "year": 1972,
        "source": MediaScrobbler.VALIDATED_MOVIE_SEARCH_SOURCE,
    })
    assert scrobbler._get_valid_cached_info("the godfather", raw_title="The Godfather")["simkl_id"] == 1


def test_conflicting_cache_entries_are_evicted(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.media_cache.set("dune part two (2024)", {
        "simkl_id": 2, "movie_name": "Dune", "type": "movie", "year": 2021, "source": "simkl_search_movie",
    })
    assert scrobbler._get_valid_cached_info("dune part two (2024)", raw_title="Dune Part Two (2024)") is None
    assert scrobbler.media_cache.get("dune part two (2024)") is None

    scrobbler.media_cache.set("show.name.s01e03.mkv", {
        "simkl_id": 555, "movie_name": "Show Name", "type": "show", "season": 1, "episode": 2,
        "source": "simkl_search_file_old",
    })
    assert scrobbler._get_valid_cached_info("show.name.s01e03.mkv", filepath="Show.Name.S01E03.mkv") is not None

    scrobbler.media_cache.set("show.name.s01e04.mkv", {
        "simkl_id": 555, "movie_name": "Show Name", "type": "show", "season": 1, "episode": 2,
        "source": "guessit_fallback",
    })
    assert scrobbler._get_valid_cached_info("show.name.s01e04.mkv", filepath="Show.Name.S01E04.mkv") is None


# --- per-file /search/file rate limit ---------------------------------------------------------

def test_file_search_rate_limit_blocks_after_limit_until_cleared(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    path = os.path.join("TV", "Show.Name.S01E03.mkv")
    queries = []

    def fake_search_file(file_path, client_id, part=None):
        queries.append(file_path)
        return []

    monkeypatch.setattr(media_scrobbler_mod, "search_file", fake_search_file)
    scrobbler.currently_tracking = "Show Name S01E03"
    scrobbler.current_filepath = path
    scrobbler.media_type = "episode"

    for _ in range(MediaScrobbler.MAX_FILE_SEARCH_ATTEMPTS_PER_FILE + 2):
        scrobbler._identify_media_from_filepath(path)

    assert queries.count(path) == MediaScrobbler.MAX_FILE_SEARCH_ATTEMPTS_PER_FILE
    per_cycle = len(queries) // MediaScrobbler.MAX_FILE_SEARCH_ATTEMPTS_PER_FILE
    assert per_cycle <= MediaScrobbler.MAX_FILE_SEARCH_VARIANTS + 1
    assert scrobbler._is_file_search_rate_limited(path.replace(os.sep, "/").upper())

    assert scrobbler.clear_file_search_rate_limit(path)
    scrobbler._identify_media_from_filepath(path)
    assert queries.count(path) == MediaScrobbler.MAX_FILE_SEARCH_ATTEMPTS_PER_FILE + 1


def test_rate_limit_key_is_not_resolved_against_cwd(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    assert scrobbler._file_search_rate_limit_key(r"C:\TV\Show.mkv") == "c:/tv/show.mkv"
    assert scrobbler._file_search_rate_limit_key("Show S01E01") == "show s01e01"


def test_successful_file_search_clears_counter_and_fills_identity(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    path = os.path.join("TV", "Show.Name.S01E01E02.mkv")
    monkeypatch.setattr(media_scrobbler_mod, "search_file",
                        lambda *a, **kw: _episode_result(season=1, episode=1))
    scrobbler.currently_tracking = "Show Name S01E01-E02"
    scrobbler.current_filepath = path
    scrobbler.media_type = "episode"

    scrobbler._identify_media_from_filepath(path)

    assert scrobbler.simkl_id == 555
    assert (scrobbler.season, scrobbler.episode) == (1, 1)
    assert not scrobbler._file_search_attempts


def test_non_preferred_result_goes_to_backlog_not_tracking(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    path = os.path.join("TV", "Show.Name.S01E03.mkv")
    monkeypatch.setattr(media_scrobbler_mod, "search_file",
                        lambda *a, **kw: _episode_result(episode=7))
    scrobbler.currently_tracking = "Show Name S01E03"
    scrobbler.current_filepath = path
    scrobbler.media_type = "episode"

    scrobbler._identify_media_from_filepath(path)

    assert scrobbler.simkl_id is None
    assert path in scrobbler.backlog_cleaner.get_pending()


def test_file_identified_mid_playback_past_threshold_does_not_start_or_mark_watched(tmp_path, monkeypatch):
    """#192 guard still holds when PR175 identification lands late (preview seek to 95%)."""
    scrobbler = _make_scrobbler(tmp_path)
    calls, history = [], []
    monkeypatch.setattr(media_scrobbler_mod, "scrobble",
                        lambda action, *a, **kw: calls.append(action) or {"ok": True, "status": 200})
    monkeypatch.setattr(scrobbler, "_attempt_add_to_history", lambda *a, **kw: history.append(1) or True)
    monkeypatch.setattr(media_scrobbler_mod, "search_file",
                        lambda *a, **kw: _episode_result(season=1, episode=3))
    path = os.path.join("TV", "Show.Name.S01E03.mkv")
    scrobbler.currently_tracking = "Show Name S01E03"
    scrobbler.current_filepath = path
    scrobbler.media_type = "episode"
    scrobbler.state = PLAYING
    scrobbler.total_duration_seconds = 1000
    scrobbler.current_position_seconds = 950
    scrobbler.watch_time = 5

    scrobbler._identify_media_from_filepath(path)
    scrobbler._check_completion_threshold(use_position=True)
    scrobbler._sync_scrobble_state()

    assert scrobbler.simkl_id == 555
    assert calls == []
    assert history == []


# --- tray retry -------------------------------------------------------------------------------

def _make_tray(scrobbler):
    from simkl_mps.tray_base import TrayAppBase

    class DummyTrayApp(TrayAppBase):
        def run(self): pass
        def _ask_custom_threshold_dialog(self, current_threshold): return None
        def _ask_custom_min_watch_time_dialog(self, current_seconds): return None
        def _ask_directory_filter_dialog(self, title, current_value, help_text): return None
        def update_icon(self): pass
        def show_notification(self, title, message): pass
        def show_about(self, _=None): pass
        def show_help(self, _=None): pass
        def exit_app(self, _=None): pass

    tray = DummyTrayApp()
    tray.scrobbler = types.SimpleNamespace(monitor=types.SimpleNamespace(scrobbler=scrobbler))
    return tray


def test_tray_retry_closes_old_session_clears_limit_and_starts_new_identity(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    calls = []

    def fake_scrobble(action, item, progress, client_id, access_token, min_progress=None):
        calls.append((action, item, progress))
        return {"ok": True, "status": 200, "error": None}

    clock = [1000.0]
    monkeypatch.setattr(media_scrobbler_mod.time, "time", lambda: clock[0])
    monkeypatch.setattr(media_scrobbler_mod, "scrobble", fake_scrobble)

    path = os.path.join("TV", "Show.Name.S01E03.mkv")
    scrobbler.currently_tracking = "Show Name S01E03"
    scrobbler.current_filepath = path
    scrobbler.simkl_id = 111  # wrong show identified earlier
    scrobbler.media_type = "show"
    scrobbler.season, scrobbler.episode = 1, 3
    scrobbler.state = PLAYING
    scrobbler.total_duration_seconds = 1000
    scrobbler.current_position_seconds = 300
    scrobbler.watch_time = 300
    scrobbler._sync_scrobble_state()
    assert calls[-1][0] == "start" and calls[-1][1]["show"]["ids"]["simkl"] == 111

    for _ in range(MediaScrobbler.MAX_FILE_SEARCH_ATTEMPTS_PER_FILE):
        scrobbler._record_file_search_attempt(path)
    assert scrobbler._is_file_search_rate_limited(path)

    monkeypatch.setattr(media_scrobbler_mod, "search_file", lambda *a, **kw: _episode_result(season=1, episode=3))
    clock[0] += 30
    _make_tray(scrobbler).try_scrobble_again()

    # Old session closed below min_progress (never marks the wrong item watched).
    assert calls[1][0] == "stop" and calls[1][2] == 0.0
    assert calls[1][1]["show"]["ids"]["simkl"] == 111
    assert scrobbler.simkl_id == 555
    assert not scrobbler._is_file_search_rate_limited(path)
    assert scrobbler._scrobble_reported_state is None

    clock[0] += 30
    scrobbler._sync_scrobble_state()
    assert calls[-1][0] == "start"
    assert calls[-1][1]["show"]["ids"]["simkl"] == 555
    assert calls[-1][2] == 30.0
