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


def test_seek_while_playing_makes_no_call_next_event_carries_progress(tmp_path, clock_and_recorder):
    """Simkl wants no scrobble call for seeks; the next real event reports the new position."""
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    scrobbler._sync_scrobble_state()
    assert len(calls) == 1
    assert calls[-1]["action"] == "start"
    assert calls[-1]["progress"] == 10.0

    # User seeks to 500s (50%): nothing is sent, even after the debounce interval
    clock.advance(30.0)
    scrobbler.current_position_seconds = 500
    scrobbler._notify_seek()
    scrobbler._sync_scrobble_state()
    assert len(calls) == 1

    # Next real event (pause) carries the new progress
    clock.advance(30.0)
    scrobbler.state = PAUSED
    scrobbler._sync_scrobble_state()
    assert len(calls) == 2
    assert calls[-1]["action"] == "pause"
    assert calls[-1]["progress"] == 50.0


def test_seek_while_paused_makes_no_call(tmp_path, clock_and_recorder):
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    scrobbler._sync_scrobble_state()
    clock.advance(3.0)
    scrobbler.state = PAUSED
    scrobbler._sync_scrobble_state()
    assert calls[-1]["action"] == "pause"
    assert calls[-1]["progress"] == 10.0

    # User seeks while paused to 750s (75%)
    clock.advance(30.0)
    scrobbler.current_position_seconds = 750
    scrobbler._notify_seek()
    scrobbler._sync_scrobble_state()
    assert len(calls) == 2

    # Resume carries the seek progress
    clock.advance(30.0)
    scrobbler.state = PLAYING
    scrobbler._sync_scrobble_state()
    assert len(calls) == 3
    assert calls[-1]["action"] == "start"
    assert calls[-1]["progress"] == 75.0


def test_stop_below_min_progress_clears_saved_playback(tmp_path, clock_and_recorder, monkeypatch):
    """Issue 2: Stopping near 0% (< MIN_RESUME_PROGRESS) must delete saved playback from Simkl."""
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "start"
    scrobbler.watch_time = 15.0
    scrobbler.completion_threshold = 80.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 5.0  # 0.5% (< 2.0%)

    deleted_ids = []
    fake_sessions = [{"id": 999, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: fake_sessions)
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda pid, cid, tok: deleted_ids.append(pid) or True)

    scrobbler.stop_tracking()

    assert len(calls) == 1
    assert calls[0]["action"] == "stop"
    assert calls[0]["progress"] == 0.5
    assert deleted_ids == [999]


def test_rewatch_deferred_if_watch_time_insufficient_in_update(tmp_path, monkeypatch):
    """Issue 3: Rewatch must not be added if accumulated watch time is below threshold."""
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0  # 95% (>= 90%)
    scrobbler.watch_time = 5.0  # Only watched for 5s (< 180s)

    history_calls = []
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: True)
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: True)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"status": "success"})

    # Emulate _check_completion_threshold
    scrobbler._check_completion_threshold(use_position=True)

    assert scrobbler.completed is False
    assert len(history_calls) == 0


def test_rewatch_deferred_if_watch_time_insufficient_on_stop(tmp_path, monkeypatch):
    """Issue 3: On player close/skip, rewatch is skipped if watch time is below threshold."""
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 960.0  # 96%
    scrobbler.watch_time = 8.0  # Only watched 8s (< 180s)

    history_calls = []
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: True)
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: True)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"status": "success"})

    scrobbler.stop_tracking()

    assert scrobbler.completed is False
    assert len(history_calls) == 0


def test_rewatch_succeeds_when_watch_time_sufficient(tmp_path, monkeypatch, isolated_settings):
    """Issue 3: When watch time meets the rewatch requirement, history sync succeeds."""
    isolated_settings["allow_rewatch"] = True
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0  # 95%
    scrobbler.watch_time = 200.0  # 200s >= 180s

    history_calls = []
    orig_get_setting = media_scrobbler_mod.get_setting
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda k, d=None: True if k == "allow_rewatch" else orig_get_setting(k, d))
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: True)
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: True)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"movies": 1}})

    scrobbler._check_completion_threshold(use_position=True)

    assert scrobbler.completed is True
    assert len(history_calls) == 1
    assert history_calls[0].get("allow_rewatch") is True


def test_stop_completed_item_with_reported_scrobble_reports_stop_and_clears_playback(tmp_path, clock_and_recorder, monkeypatch):
    """
    When an item reached completion threshold during playback (completed=True)
    and had reported scrobble ('start' or 'pause'), closing the player (stop_tracking)
    MUST report scrobble 'stop' and clear any residual saved playback sessions.
    """
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler._scrobble_reported_state = "start"
    scrobbler.completed = True
    scrobbler.watch_time = 120.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0  # 95%

    deleted_ids = []
    fake_sessions = [{"id": 789, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: fake_sessions)
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda pid, cid, tok: deleted_ids.append(pid) or True)

    scrobbler.stop_tracking()

    assert len(calls) == 1
    assert calls[0]["action"] == "stop"
    assert calls[0]["progress"] == 95.0
    assert deleted_ids == [789]


def test_completed_item_seek_makes_no_call_until_next_event(tmp_path, clock_and_recorder):
    """After completion, seeks still send nothing; the next real event reports progress."""
    clock, calls = clock_and_recorder
    scrobbler = _make_scrobbler(tmp_path)

    scrobbler._sync_scrobble_state()
    assert len(calls) == 1
    assert calls[-1]["progress"] == 10.0

    scrobbler.completed = True
    clock.advance(30.0)
    scrobbler.current_position_seconds = 963.5
    scrobbler._notify_seek()
    scrobbler._sync_scrobble_state()
    assert len(calls) == 1

    clock.advance(30.0)
    scrobbler.state = PAUSED
    scrobbler._sync_scrobble_state()
    assert len(calls) == 2
    assert calls[-1]["action"] == "pause"
    assert calls[-1]["progress"] == 96.35


def test_add_to_history_passes_allow_rewatch_when_enabled_for_cloud_rewatch(tmp_path, monkeypatch, isolated_settings):
    """
    If an item is not in local watch history, but allow_rewatch is enabled and user is Pro/VIP,
    allow_rewatch=True must be passed to Simkl so cloud rewatches are properly recorded by Simkl.
    """
    isolated_settings["allow_rewatch"] = True
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.season = 2
    scrobbler.episode = 7
    scrobbler.media_type = "show"
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0  # 95%
    scrobbler.watch_time = 200.0

    history_calls = []
    orig_get_setting = media_scrobbler_mod.get_setting
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda k, d=None: True if k == "allow_rewatch" else orig_get_setting(k, d))
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: False)
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: True)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"episodes": 1}})

    scrobbler._check_completion_threshold(use_position=True)

    assert scrobbler.completed is True
    assert len(history_calls) == 1
    # allow_rewatch must be True so Simkl can record rewatch even if not previously in local history
    assert history_calls[0].get("allow_rewatch") is True


def test_add_to_history_does_not_pass_allow_rewatch_when_disabled_or_not_pro(tmp_path, monkeypatch):
    """
    When allow_rewatch is disabled in settings or user is not Pro/VIP, allow_rewatch=False must be passed.
    """
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.season = 2
    scrobbler.episode = 7
    scrobbler.media_type = "show"
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0
    scrobbler.watch_time = 200.0

    history_calls = []
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: False)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"episodes": 1}})

    scrobbler._check_completion_threshold(use_position=True)

    assert scrobbler.completed is True
    assert len(history_calls) == 1
    assert history_calls[0].get("allow_rewatch") is False


def test_first_watch_deferred_when_watch_time_below_min(tmp_path, monkeypatch):
    """
    First-time watches (not just rewatches) must defer history sync when watch_time < min_rewatch_watch_seconds (180s).
    """
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.season = 1
    scrobbler.episode = 1
    scrobbler.media_type = "show"
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0  # 95%
    scrobbler.watch_time = 45.0  # Only watched for 45s (e.g. skipped near end)

    history_calls = []
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: False)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw))

    res = scrobbler._check_completion_threshold(use_position=True)
    assert res is False
    assert scrobbler.completed is False
    assert len(history_calls) == 0


def test_first_watch_succeeds_when_watch_time_reaches_min(tmp_path, monkeypatch):
    """
    First-time watch completes successfully once watch_time reaches min_rewatch_watch_seconds.
    """
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.season = 1
    scrobbler.episode = 1
    scrobbler.media_type = "show"
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0  # 95%
    scrobbler.watch_time = 185.0  # Watched for >= 180s

    history_calls = []
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: False)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"episodes": 1}})

    res = scrobbler._check_completion_threshold(use_position=True)
    assert res is True
    assert scrobbler.completed is True
    assert len(history_calls) == 1


def test_short_media_duration_caps_min_watch_time(tmp_path, monkeypatch):
    """
    For short videos (e.g. 60s clips), required min watch time is capped at duration * threshold%
    (e.g. 60 * 0.9 = 54s) so short videos are not blocked by 180s.
    """
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 60.0
    scrobbler.current_position_seconds = 58.0  # > 90%
    scrobbler.watch_time = 55.0  # 55s >= 54s (capped min_watch_time)

    history_calls = []
    monkeypatch.setattr(scrobbler, "_is_local_rewatch", lambda *a: False)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"movies": 1}})

    res = scrobbler._check_completion_threshold(use_position=True)
    assert res is True
    assert scrobbler.completed is True
    assert len(history_calls) == 1


def test_tray_min_watch_time_setting(monkeypatch):
    """
    Test setting minimum watch time via preset and custom values in TrayAppBase.
    """
    from simkl_mps.tray_base import TrayAppBase
    from simkl_mps.config_manager import get_setting, set_setting

    class DummyTrayApp(TrayAppBase):
        def __init__(self):
            super().__init__()
            self.dialog_return_val = None

        def run(self):
            pass

        def _ask_custom_threshold_dialog(self, current_threshold: int):
            return None

        def _ask_custom_min_watch_time_dialog(self, current_seconds: int):
            return self.dialog_return_val

        def _ask_directory_filter_dialog(self, title, current_value, help_text):
            return None

        def update_icon(self):
            pass

        def show_notification(self, title, message):
            pass

        def show_about(self, _=None):
            pass

        def show_help(self, _=None):
            pass

        def exit_app(self, _=None):
            pass

    tray = DummyTrayApp()

    # Preset 300s
    tray._set_preset_min_watch_time(300)
    assert get_setting("min_rewatch_watch_seconds") == 300

    # Preset 0s (None)
    tray._set_preset_min_watch_time(0)
    assert get_setting("min_rewatch_watch_seconds") == 0

    # Custom 120s
    tray._apply_min_watch_time_change(120)
    assert get_setting("min_rewatch_watch_seconds") == 120

    # Reset back to default 180s
    tray._set_preset_min_watch_time(180)
    assert get_setting("min_rewatch_watch_seconds") == 180



def test_add_to_history_does_not_pass_allow_rewatch_for_pro_when_setting_default_off(tmp_path, monkeypatch):
    """Rewatch tracking is opt-in: Pro/VIP with the default setting must not send allow_rewatch."""
    scrobbler = _make_scrobbler(tmp_path)
    scrobbler.completion_threshold = 90.0
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 950.0
    scrobbler.watch_time = 200.0

    history_calls = []
    monkeypatch.setattr(scrobbler, "is_pro_or_vip", lambda: True)
    monkeypatch.setattr(scrobbler, "_store_in_watch_history", lambda *a, **kw: None)
    monkeypatch.setattr(media_scrobbler_mod, "add_to_history", lambda *a, **kw: history_calls.append(kw) or {"added": {"movies": 1}})

    scrobbler._check_completion_threshold(use_position=True)

    assert scrobbler.completed is True
    assert history_calls[0].get("allow_rewatch") is False
