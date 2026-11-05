import importlib
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
constants = importlib.import_module("simkl_mps.utils.constants")
PLAYING = constants.PLAYING
PAUSED = constants.PAUSED
STOPPED = constants.STOPPED


config_manager = importlib.import_module("simkl_mps.config_manager")
simkl_api_mod = importlib.import_module("simkl_mps.simkl_api")


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Use default settings in memory and block real network calls."""
    settings = dict(config_manager.DEFAULT_SETTINGS)
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(media_scrobbler_mod, "is_internet_connected", lambda: True)
    monkeypatch.setattr(media_scrobbler_mod, "scrobble",
                        lambda *a, **kw: {"ok": False, "status": None, "error": "network disabled in tests"})
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda *a, **kw: [])
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda *a, **kw: False)
    monkeypatch.setattr(simkl_api_mod, "get_user_settings", lambda *a, **kw: None)

    def _no_network(*args, **kwargs):
        raise AssertionError("Unexpected real HTTP request in test")

    for method in ("get", "post", "delete"):
        monkeypatch.setattr(simkl_api_mod.requests, method, _no_network)
    return settings


class MutableClock:
    def __init__(self, initial=1000.0):
        self.current = initial

    def time(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


@pytest.fixture
def clock_and_recorder(monkeypatch):
    clock = MutableClock(1000.0)
    calls = []

    def fake_scrobble(action, item, progress, client_id, access_token, min_progress=None):
        calls.append({
            "action": action,
            "item": item,
            "progress": progress,
            "client_id": client_id,
            "access_token": access_token,
            "min_progress": min_progress
        })
        return {"ok": True, "status": 200, "error": None}

    monkeypatch.setattr(media_scrobbler_mod.time, "time", clock.time)
    monkeypatch.setattr(media_scrobbler_mod, "scrobble", fake_scrobble)
    return clock, calls


def _make_scrobbler(tmp_path):
    scrobbler = media_scrobbler_mod.MediaScrobbler(
        app_data_dir=tmp_path,
        client_id="test_client_id",
        access_token="test_access_token",
        testing_mode=True
    )
    scrobbler.currently_tracking = "Test Movie"
    scrobbler.simkl_id = 123
    scrobbler.media_type = "movie"
    scrobbler.total_duration_seconds = 1000
    scrobbler.current_position_seconds = 100
    scrobbler.state = PLAYING
    return scrobbler


def test_build_scrobble_item_variants(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)

    # Movie
    scrobbler.media_type = "movie"
    scrobbler.simkl_id = 123
    assert scrobbler._build_scrobble_item() == {"movie": {"ids": {"simkl": 123}}}

    # Show with season and episode
    scrobbler.media_type = "show"
    scrobbler.season = 2
    scrobbler.episode = 5
    assert scrobbler._build_scrobble_item() == {
        "show": {"ids": {"simkl": 123}},
        "episode": {"season": 2, "number": 5}
    }

    # Show missing episode
    scrobbler.episode = None
    assert scrobbler._build_scrobble_item() is None

    # Anime with episode only
    scrobbler.media_type = "anime"
    scrobbler.season = None
    scrobbler.episode = 12
    assert scrobbler._build_scrobble_item() == {
        "anime": {"ids": {"simkl": 123}},
        "episode": {"number": 12}
    }

    # Anime with season and episode
    scrobbler.season = 1
    assert scrobbler._build_scrobble_item() == {
        "anime": {"ids": {"simkl": 123}},
        "episode": {"season": 1, "number": 12}
    }

    # Temporary ID
    scrobbler.simkl_id = "temp_ab12cd34"
    assert scrobbler._build_scrobble_item() is None

    # Missing ID
    scrobbler.simkl_id = None
    assert scrobbler._build_scrobble_item() is None


def test_sync_sends_start_once_then_nothing(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    scrobbler._sync_scrobble_state()
    assert len(calls) == 1
    assert calls[0]["action"] == "start"
    assert calls[0]["progress"] == 10.0

    clock.advance(10.0)
    scrobbler._sync_scrobble_state()
    # State has not changed, so no new scrobble call
    assert len(calls) == 1


def test_sync_sends_pause_on_state_change_and_start_on_resume(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    scrobbler._sync_scrobble_state()
    assert len(calls) == 1
    assert calls[-1]["action"] == "start"

    # Pause
    clock.advance(10.0)
    scrobbler.state = PAUSED
    scrobbler.current_position_seconds = 200
    scrobbler._sync_scrobble_state()
    assert len(calls) == 2
    assert calls[-1]["action"] == "pause"
    assert calls[-1]["progress"] == 20.0

    # Resume playing
    clock.advance(10.0)
    scrobbler.state = PLAYING
    scrobbler.current_position_seconds = 250
    scrobbler._sync_scrobble_state()
    assert len(calls) == 3
    assert calls[-1]["action"] == "start"
    assert calls[-1]["progress"] == 25.0


def test_sync_respects_min_interval(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    scrobbler._sync_scrobble_state()
    assert len(calls) == 1

    # State changes after only 1 second (below 2.5s interval)
    clock.advance(1.0)
    scrobbler.state = PAUSED
    scrobbler._sync_scrobble_state()
    assert len(calls) == 1  # Throttled!

    # Advance beyond 2.5s
    clock.advance(2.0)
    scrobbler._sync_scrobble_state()
    assert len(calls) == 2
    assert calls[-1]["action"] == "pause"


def test_sync_failure_is_retried_next_poll(tmp_path, monkeypatch):
    clock = MutableClock(1000.0)
    monkeypatch.setattr(media_scrobbler_mod.time, "time", clock.time)

    call_count = 0

    def failing_then_success_scrobble(action, item, progress, client_id, access_token, min_progress=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"ok": False, "status": 400, "error": "RATE_LIMIT"}
        return {"ok": True, "status": 200, "error": None}

    monkeypatch.setattr(media_scrobbler_mod, "scrobble", failing_then_success_scrobble)

    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._sync_scrobble_state()
    assert call_count == 1
    assert scrobbler._scrobble_reported_state is None

    # Failures back off for Simkl's 20s scrobble lock instead of retrying every poll
    clock.advance(10.0)
    scrobbler._sync_scrobble_state()
    assert call_count == 1

    clock.advance(11.0)
    scrobbler._sync_scrobble_state()
    assert call_count == 2
    assert scrobbler._scrobble_reported_state == "start"


def test_sync_skipped_when_setting_disabled(tmp_path, clock_and_recorder, monkeypatch):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda key, default=None: False if key == "enable_realtime_scrobble" else default)
    scrobbler._sync_scrobble_state()
    assert len(calls) == 0


def test_sync_skipped_for_unidentified_or_completed(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    # Missing simkl_id
    scrobbler.simkl_id = None
    scrobbler._sync_scrobble_state()
    assert len(calls) == 0

    # Temp ID
    scrobbler.simkl_id = "temp_12345"
    scrobbler._sync_scrobble_state()
    assert len(calls) == 0

    # Completed item
    scrobbler.simkl_id = 123
    scrobbler.completed = True
    scrobbler._sync_scrobble_state()
    assert len(calls) == 0


def test_detect_pause_uses_mpv_is_paused(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)

    class FakeMPVIntegration:
        def __init__(self, paused=True):
            self._paused = paused

        def is_paused(self):
            return self._paused

    fake_mpv = FakeMPVIntegration(paused=True)
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    # 1. MPV reports paused -> True even without "paused" in title
    assert scrobbler._detect_pause({"process_name": "mpv.exe", "title": "Inception.mkv - mpv"}) is True

    # 2. MPV reports playing -> False
    fake_mpv._paused = False
    assert scrobbler._detect_pause({"process_name": "mpv.exe", "title": "Inception.mkv - mpv"}) is False

    # 3. MPV returns None -> falls back to title check
    fake_mpv._paused = None
    assert scrobbler._detect_pause({"process_name": "mpv.exe", "title": "Inception.mkv [Paused] - mpv"}) is True
    assert scrobbler._detect_pause({"process_name": "mpv.exe", "title": "Inception.mkv - mpv"}) is False


def test_stop_below_threshold_reports_pause(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 45.0
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 450.0

    res = scrobbler.stop_tracking()
    assert res is not None
    assert len(calls) == 1
    assert calls[0]["action"] == "pause"
    assert calls[0]["progress"] == 45.0


def test_stop_custom_threshold_90_at_85_reports_pause(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 50.0
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 850.0

    res = scrobbler.stop_tracking()
    assert res is not None
    assert len(calls) == 1
    assert calls[0]["action"] == "pause"
    assert calls[0]["progress"] == 85.0


def test_stop_at_threshold_uses_history_not_pause(tmp_path, clock_and_recorder, monkeypatch):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 200.0
    scrobbler.completion_threshold = 65.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 650.0

    history_calls = []

    def fake_attempt():
        history_calls.append(True)
        scrobbler.completed = True
        return True

    monkeypatch.setattr(scrobbler, "_attempt_add_to_history", fake_attempt)

    res = scrobbler.stop_tracking()
    assert res is not None
    assert len(history_calls) == 1
    # No session was open, so nothing to close
    assert len(calls) == 0


def test_stop_below_min_progress_reports_nothing(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 50.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 19.0  # 1.9% < 2.0%

    scrobbler.stop_tracking()
    assert len(calls) == 0

    # Also low watch_time (< 30s)
    scrobbler2 = _make_scrobbler(tmp_path)
    scrobbler2.watch_time = 15.0
    scrobbler2.total_duration_seconds = 1000.0
    scrobbler2.current_position_seconds = 500.0  # 50%
    scrobbler2.stop_tracking()
    assert len(calls) == 0


def test_stop_completed_item_reports_nothing(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completed = True
    scrobbler.watch_time = 100.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 700.0

    scrobbler.stop_tracking()
    assert len(calls) == 0


def test_stop_with_stale_position_still_reports(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 60.0
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 350.0

    scrobbler.stop_tracking()
    assert len(calls) == 1
    assert calls[0]["action"] == "pause"
    assert calls[0]["progress"] == 35.0


def test_media_change_reports_old_item_then_resets(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 50.0
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 400.0

    scrobbler.stop_tracking()
    assert len(calls) == 1
    assert calls[0]["action"] == "pause"
    assert scrobbler._scrobble_reported_state is None

    # New item
    clock.advance(10.0)
    scrobbler.currently_tracking = "New Movie"
    scrobbler.simkl_id = 456
    scrobbler.media_type = "movie"
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 100.0
    scrobbler.state = PLAYING
    scrobbler._sync_scrobble_state()

    assert len(calls) == 2
    assert calls[1]["action"] == "start"
    assert calls[1]["item"] == {"movie": {"ids": {"simkl": 456}}}


def test_stop_network_error_does_not_raise(tmp_path, monkeypatch):
    def failing_scrobble(*args, **kwargs):
        import requests
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(media_scrobbler_mod, "scrobble", failing_scrobble)
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.watch_time = 50.0
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 450.0

    res = scrobbler.stop_tracking()
    assert res is not None
    assert res["state"] == STOPPED


def test_completion_deletes_matching_saved_playback(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "pause"
    scrobbler.watch_time = 200.0

    deleted_ids = []
    sessions = [{"id": 42, "movie": {"ids": {"simkl": 123}}}]

    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: False)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda pid, cid, tok: deleted_ids.append(pid) or True)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: {"status": "success"})

    scrobbler._attempt_add_to_history()

    assert scrobbler.completed is True
    assert deleted_ids == [42]


def test_completion_without_prior_pause_makes_no_calls(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "start"
    scrobbler._resume_sessions = None
    scrobbler.watch_time = 200.0

    deleted_ids = []
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda pid, cid, tok: deleted_ids.append(pid) or True)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: {"status": "success"})

    scrobbler._attempt_add_to_history()

    assert scrobbler.completed is True
    assert len(deleted_ids) == 0


def test_clear_saved_playback_swallows_errors(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "pause"

    def crashing_get(*args, **kwargs):
        import requests
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", crashing_get)
    # Should not raise exception
    scrobbler._clear_saved_playback()


def test_stop_short_watch_time_with_reported_start_reports_pause(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "start"
    scrobbler.watch_time = 15.0  # < 30s
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 185.0  # 18.5%

    res = scrobbler.stop_tracking()
    assert res is not None
    assert len(calls) == 1
    assert calls[0]["action"] == "pause"
    assert calls[0]["progress"] == 18.5


def test_stop_short_watch_time_below_min_progress_with_reported_start_reports_stop(tmp_path, clock_and_recorder):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "start"
    scrobbler.watch_time = 10.0  # < 30s
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 10.0  # 1.0% (< 2.0%)

    res = scrobbler.stop_tracking()
    assert res is not None
    assert len(calls) == 1
    assert calls[0]["action"] == "stop"
    assert calls[0]["progress"] == 1.0



# --- Regression: previews / seeks near the end must never mark watched on Simkl ---

def _short_watch_near_end(tmp_path, threshold=80.0, position=950.0):
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = threshold
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = position
    scrobbler.watch_time = 5.0  # far below the 180s minimum watch time
    scrobbler.state = PLAYING
    scrobbler._scrobble_reported_state = "start"
    return scrobbler


@pytest.mark.parametrize("threshold", [60.0, 80.0, 90.0, 95.0])
def test_stop_short_watch_near_end_never_sends_completing_stop(tmp_path, clock_and_recorder, monkeypatch, threshold):
    _, calls = clock_and_recorder
    history_calls = []
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"movies": 1}})
    scrobbler = _short_watch_near_end(tmp_path, threshold=threshold)

    scrobbler.stop_tracking()

    assert history_calls == []
    assert [c["action"] for c in calls] == ["pause"]
    assert calls[0]["progress"] == 95.0


def test_short_watch_near_end_media_switch_closes_session_with_pause(tmp_path, clock_and_recorder):
    """Switching items must close the open session with pause first, so the new start can't auto-finish it."""
    clock, calls = clock_and_recorder
    scrobbler = _short_watch_near_end(tmp_path)

    scrobbler.stop_tracking()
    clock.advance(25.0)
    scrobbler.currently_tracking = "Next Movie"
    scrobbler.simkl_id = 456
    scrobbler.media_type = "movie"
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 0.0
    scrobbler.state = PLAYING
    scrobbler._sync_scrobble_state()

    assert [c["action"] for c in calls] == ["pause", "start"]


def test_start_not_sent_past_threshold_until_completion_accepted(tmp_path, clock_and_recorder):
    """An open start session past min_progress could be auto-finished by Simkl; don't open one early."""
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 80.0
    scrobbler.current_position_seconds = 900.0
    scrobbler.watch_time = 5.0

    scrobbler._sync_scrobble_state()
    assert calls == []

    # Once local completion accepts the watch, Watching now may be shown
    scrobbler.completed = True
    scrobbler._scrobble_reported_state = "pause"
    clock.advance(30.0)
    scrobbler._sync_scrobble_state()
    assert [c["action"] for c in calls] == ["start"]


def test_seek_past_threshold_during_play_then_pause_reports_pause(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._sync_scrobble_state()
    assert calls[-1]["action"] == "start"

    clock.advance(30.0)
    scrobbler.current_position_seconds = 970.0
    scrobbler._notify_seek()
    scrobbler._sync_scrobble_state()
    assert len(calls) == 1  # no call on seek

    clock.advance(5.0)
    scrobbler.state = PAUSED
    scrobbler._sync_scrobble_state()
    assert calls[-1]["action"] == "pause"
    assert calls[-1]["progress"] == 97.0


def test_genuine_completion_flow_sends_start_then_stop(tmp_path, clock_and_recorder, monkeypatch):
    clock, calls = clock_and_recorder
    history_calls = []
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"movies": 1}})
    monkeypatch.setattr(media_scrobbler_mod.MediaScrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 90.0
    scrobbler.current_position_seconds = 0.0

    scrobbler._sync_scrobble_state()
    assert calls[-1]["action"] == "start"
    assert calls[-1]["min_progress"] == 90

    # Watched long enough to reach 95%
    clock.advance(900.0)
    scrobbler.watch_time = 900.0
    scrobbler.current_position_seconds = 950.0
    assert scrobbler._check_completion_threshold(use_position=True) is True
    assert scrobbler.completed is True
    assert history_calls[0].get("allow_rewatch") is False

    scrobbler.stop_tracking()
    assert [c["action"] for c in calls] == ["start", "stop"]
    assert calls[-1]["progress"] == 95.0
    assert calls[-1]["min_progress"] == 90


@pytest.mark.parametrize("threshold,expected", [(80.0, 80), (95.0, 95), (40.0, 50), (100.0, 100)])
def test_min_progress_follows_configured_threshold(tmp_path, clock_and_recorder, threshold, expected):
    _, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = threshold
    scrobbler.current_position_seconds = 10.0
    scrobbler._sync_scrobble_state()
    assert calls[-1]["min_progress"] == expected


def test_stop_failure_on_close_does_not_raise_or_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(media_scrobbler_mod, "scrobble",
                        lambda *a, **kw: {"ok": False, "status": 429, "error": "locked"})
    scrobbler = _short_watch_near_end(tmp_path)
    res = scrobbler.stop_tracking()
    assert res["state"] == STOPPED
    assert scrobbler.completed is False


def test_pause_resume_cycle_below_threshold(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._sync_scrobble_state()
    clock.advance(30.0)
    scrobbler.state = PAUSED
    scrobbler.current_position_seconds = 400.0
    scrobbler._sync_scrobble_state()
    clock.advance(30.0)
    scrobbler.state = PLAYING
    scrobbler._sync_scrobble_state()
    clock.advance(30.0)
    scrobbler.watch_time = 60.0
    scrobbler.current_position_seconds = 500.0
    scrobbler.stop_tracking()

    assert [(c["action"], c["progress"]) for c in calls] == [
        ("start", 10.0), ("pause", 40.0), ("start", 40.0), ("pause", 50.0)
    ]


def test_report_scrobble_failure_keeps_state_and_backs_off(tmp_path, monkeypatch):
    clock = MutableClock(1000.0)
    monkeypatch.setattr(media_scrobbler_mod.time, "time", clock.time)
    attempts = []
    monkeypatch.setattr(media_scrobbler_mod, "scrobble",
                        lambda *a, **kw: attempts.append(a[0]) or {"ok": False, "status": 401, "error": "unauthorized"})
    scrobbler = _make_scrobbler(tmp_path)

    for _ in range(5):
        scrobbler._sync_scrobble_state()
        clock.advance(3.0)

    assert attempts == ["start"]
    assert scrobbler._scrobble_reported_state is None
