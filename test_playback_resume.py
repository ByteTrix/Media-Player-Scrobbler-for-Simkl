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


class FakeMPVIntegration:
    def __init__(self):
        self.seek_calls = []
        self.osd_calls = []

    def seek_absolute(self, seconds):
        self.seek_calls.append(seconds)
        return True

    def show_osd(self, text, duration_ms=3500):
        self.osd_calls.append((text, duration_ms))
        return True


def _make_scrobbler(tmp_path):
    scrobbler = media_scrobbler_mod.MediaScrobbler(
        app_data_dir=tmp_path,
        client_id="test_client_id",
        access_token="test_access_token",
        testing_mode=True
    )
    scrobbler.currently_tracking = "Test Media"
    scrobbler.simkl_id = 123
    scrobbler.media_type = "movie"
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 5.0
    scrobbler.state = PLAYING
    scrobbler.completion_threshold = 80.0
    return scrobbler


def test_format_timestamp():
    fmt = media_scrobbler_mod.MediaScrobbler._format_timestamp
    assert fmt(754.3) == "12:34"
    assert fmt(3725.0) == "1:02:05"
    assert fmt(45.0) == "0:45"
    assert fmt(0.0) == "0:00"


def test_find_matching_playback_movie_and_episode(tmp_path):
    scrobbler = _make_scrobbler(tmp_path)
    sessions = [
        {
            "id": 1,
            "progress": 42.0,
            "paused_at": "2026-10-01T10:00:00Z",
            "type": "movie",
            "movie": {"ids": {"simkl": 123}}
        },
        {
            "id": 2,
            "progress": 55.0,
            "paused_at": "2026-10-02T12:00:00Z",
            "type": "episode",
            "show": {"ids": {"simkl": 999}},
            "episode": {"season": 1, "number": 3}
        }
    ]

    # Movie match
    scrobbler.media_type = "movie"
    scrobbler.simkl_id = 123
    assert scrobbler._find_matching_playback(sessions)["id"] == 1

    # Episode match
    scrobbler.media_type = "show"
    scrobbler.simkl_id = 999
    scrobbler.season = 1
    scrobbler.episode = 3
    assert scrobbler._find_matching_playback(sessions)["id"] == 2

    # Episode mismatch
    scrobbler.episode = 4
    assert scrobbler._find_matching_playback(sessions) is None

    # Temp ID
    scrobbler.simkl_id = "temp_12345"
    assert scrobbler._find_matching_playback(sessions) is None


def test_resume_seeks_and_shows_osd(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    sessions = [{
        "id": 10,
        "progress": 45.0,
        "paused_at": "2026-10-03T10:00:00Z",
        "movie": {"ids": {"simkl": 123}}
    }]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=1000.0)

    assert fake_mpv.seek_calls == [450.0]
    assert len(fake_mpv.osd_calls) == 1
    assert fake_mpv.osd_calls[0][0] == "[Simkl] Resumed at 45% (7:30)"
    assert scrobbler.current_position_seconds == 450.0
    assert scrobbler._resume_done is True


def test_resume_waits_for_duration(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    called = []

    def fake_get_sessions(cid, tok, media_type=None):
        called.append(True)
        return [{"id": 1, "progress": 50.0, "movie": {"ids": {"simkl": 123}}}]

    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", fake_get_sessions)

    # 1. duration is None -> should NOT fetch, should NOT mark _resume_done
    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=None)
    assert len(called) == 0
    assert scrobbler._resume_done is False
    assert len(fake_mpv.seek_calls) == 0

    # 2. Next call with duration -> performs resume
    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=1000.0)
    assert len(called) == 1
    assert scrobbler._resume_done is True
    assert fake_mpv.seek_calls == [500.0]


def test_resume_skips_when_user_already_past_tolerance(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    sessions = [{"id": 1, "progress": 50.0, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    # Position 120s exceeds tolerance (default 30s)
    scrobbler._try_resume_playback("mpv.exe", position=120.0, duration=1000.0)
    assert len(fake_mpv.seek_calls) == 0
    assert scrobbler._resume_done is True


def test_resume_skips_when_close_to_target(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    sessions = [{"id": 1, "progress": 45.0, "movie": {"ids": {"simkl": 123}}}]  # target = 450
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    # Position 448s is within 5s of target 450s (even if tolerance is e.g. 500s)
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda k, d=None: 500 if k == "resume_start_tolerance_seconds" else d)
    scrobbler._try_resume_playback("mpv.exe", position=448.0, duration=1000.0)
    assert len(fake_mpv.seek_calls) == 0
    assert scrobbler._resume_done is True


def test_resume_skips_at_or_above_threshold(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    # Progress 85% is >= threshold 80%
    sessions = [{"id": 1, "progress": 85.0, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=1000.0)
    assert len(fake_mpv.seek_calls) == 0
    assert scrobbler._resume_done is True


def test_resume_skips_below_min_progress(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    # Progress 1.0% is below MIN_RESUME_PROGRESS (2.0%)
    sessions = [{"id": 1, "progress": 1.0, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    scrobbler._try_resume_playback("mpv.exe", position=0.0, duration=1000.0)
    assert len(fake_mpv.seek_calls) == 0
    assert scrobbler._resume_done is True


def test_resume_runs_once_per_item(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    get_calls = []

    def fake_get_sessions(cid, tok, media_type=None):
        get_calls.append(True)
        return [{"id": 1, "progress": 50.0, "movie": {"ids": {"simkl": 123}}}]

    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", fake_get_sessions)

    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=1000.0)
    assert len(get_calls) == 1
    assert len(fake_mpv.seek_calls) == 1

    # Second call
    scrobbler._try_resume_playback("mpv.exe", position=500.0, duration=1000.0)
    assert len(get_calls) == 1
    assert len(fake_mpv.seek_calls) == 1


def test_resume_disabled_setting(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    get_calls = []
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda *a, **kw: get_calls.append(True))
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda k, d=None: False if k == "enable_playback_resume" else d)

    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=1000.0)
    assert len(get_calls) == 0
    assert scrobbler._resume_done is True


def test_resume_api_failure_is_silent(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)
    fake_mpv = FakeMPVIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_mpv)

    # get_playback_sessions returns None on failure
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: None)

    scrobbler._try_resume_playback("mpv.exe", position=5.0, duration=1000.0)
    assert scrobbler._resume_done is True
    assert len(fake_mpv.seek_calls) == 0


def test_resume_skipped_for_integration_without_seek(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)

    class FakeVLCIntegration:
        pass  # No seek_absolute

    fake_vlc = FakeVLCIntegration()
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: fake_vlc)

    sessions = [{"id": 1, "progress": 50.0, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    scrobbler._try_resume_playback("vlc.exe", position=5.0, duration=1000.0)
    assert scrobbler._resume_done is True


def test_resume_works_with_potplayer(tmp_path, monkeypatch):
    scrobbler = _make_scrobbler(tmp_path)

    potplayer_mod = importlib.import_module("simkl_mps.players.potplayer")
    potplayer = potplayer_mod.PotPlayerIntegration()

    seek_targets = []
    monkeypatch.setattr(potplayer, "seek_absolute", lambda sec: seek_targets.append(sec) or True)
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: potplayer)

    sessions = [{"id": 1, "progress": 20.0, "movie": {"ids": {"simkl": 123}}}]
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda cid, tok, media_type=None: sessions)

    scrobbler._try_resume_playback("potplayer.exe", position=2.0, duration=1000.0)
    assert scrobbler._resume_done is True
    assert seek_targets == [200.0]
    assert scrobbler.current_position_seconds == 200.0


def test_potplayer_is_paused_and_seek_absolute(monkeypatch):
    potplayer_mod = importlib.import_module("simkl_mps.players.potplayer")
    potplayer = potplayer_mod.PotPlayerIntegration()

    sent_messages = []
    def fake_send(hwnd, msg, wparam, lparam):
        sent_messages.append((hwnd, msg, wparam, lparam))
        if wparam == potplayer_mod.PPM_GET_PLAYBACK_STATUS:
            return fake_send.play_status
        return 0

    fake_send.play_status = 2  # Running/Playing

    monkeypatch.setattr(potplayer_mod, "win32gui", types.SimpleNamespace(SendMessage=fake_send))
    monkeypatch.setattr(potplayer_mod, "win32con", types.SimpleNamespace(WM_USER=0x0400))
    monkeypatch.setattr(potplayer_mod, "find_potplayer_hwnd", lambda: 12345)
    potplayer.platform = "windows"

    # Status 2 = playing -> is_paused() should be False
    assert potplayer.is_paused() is False
    assert sent_messages[-1] == (12345, 0x0400, potplayer_mod.PPM_GET_PLAYBACK_STATUS, 0)
    assert potplayer_mod.PPM_GET_PLAYBACK_STATUS == 0x5006  # Must be 0x5006, not 0x5001 (which was POT_SET_VOLUME/mute)!

    # Status 1 = paused -> is_paused() should be True
    fake_send.play_status = 1
    assert potplayer.is_paused() is True

    # Status -1 = stopped -> is_paused() should be True
    fake_send.play_status = -1
    assert potplayer.is_paused() is True

    # seek_absolute should send PPM_SET_PLAYBACK_TIME_MS (0x5005) with ms
    ok = potplayer.seek_absolute(42.5)
    assert ok is True
    assert sent_messages[-1] == (12345, 0x0400, potplayer_mod.PPM_SET_PLAYBACK_TIME_MS, 42500)
