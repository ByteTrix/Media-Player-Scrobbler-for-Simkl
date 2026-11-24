import importlib
import pathlib
import sys
import types
import pytest
import requests

REPO_ROOT = pathlib.Path(__file__).resolve().parent
PACKAGE_ROOT = REPO_ROOT / "simkl_mps"

if "simkl_mps" not in sys.modules:
    package = types.ModuleType("simkl_mps")
    package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["simkl_mps"] = package

mpc_mod = importlib.import_module("simkl_mps.players.mpc")
mpcqt_mod = importlib.import_module("simkl_mps.players.mpcqt")
vlc_mod = importlib.import_module("simkl_mps.players.vlc")
potplayer_mod = importlib.import_module("simkl_mps.players.potplayer")
mpv_mod = importlib.import_module("simkl_mps.players.mpv")
mpv_wrappers_mod = importlib.import_module("simkl_mps.players.mpv_wrappers")
media_scrobbler_mod = importlib.import_module("simkl_mps.media_scrobbler")
config_manager = importlib.import_module("simkl_mps.config_manager")
simkl_api_mod = importlib.import_module("simkl_mps.simkl_api")
constants = importlib.import_module("simkl_mps.utils.constants")

PLAYING = constants.PLAYING
PAUSED = constants.PAUSED


class _FakeHTTPResponse:
    def __init__(self, status_code=200, text="", json_data=None, json_error=None):
        self.status_code = status_code
        self.content = text.encode("utf-8")
        self._json_data = json_data
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


class _MutableClock:
    def __init__(self, initial=1000.0):
        self.current = initial

    def time(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


@pytest.fixture
def isolated_scrobbler_env(monkeypatch):
    settings = dict(config_manager.DEFAULT_SETTINGS)
    monkeypatch.setattr(media_scrobbler_mod, "get_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(media_scrobbler_mod, "is_internet_connected", lambda: True)
    scrobble_calls = []

    def fake_scrobble(action, item, progress, client_id, access_token, min_progress=None):
        scrobble_calls.append({"action": action, "item": item, "progress": progress})
        return {"ok": True, "status": 200, "error": None}

    monkeypatch.setattr(media_scrobbler_mod, "scrobble", fake_scrobble)
    monkeypatch.setattr(media_scrobbler_mod, "get_playback_sessions", lambda *a, **kw: [])
    monkeypatch.setattr(media_scrobbler_mod, "delete_playback", lambda *a, **kw: False)
    monkeypatch.setattr(simkl_api_mod, "get_user_settings", lambda *a, **kw: None)
    return settings, scrobble_calls


def _make_scrobbler(tmp_path, clock):
    scrobbler = media_scrobbler_mod.MediaScrobbler(
        app_data_dir=tmp_path,
        client_id="test_client_id",
        access_token="test_access_token",
        testing_mode=True,
    )
    scrobbler.currently_tracking = "Inception"
    scrobbler.current_filepath = "/movies/Inception.mkv"
    scrobbler.simkl_id = 123
    scrobbler.media_type = "movie"
    scrobbler.total_duration_seconds = 1000.0
    scrobbler.current_position_seconds = 100.0
    scrobbler.watch_time = 0.0
    scrobbler.state = PLAYING
    scrobbler.last_update_time = clock.time()
    scrobbler._resume_done = True
    return scrobbler


# ---------------------------------------------------------------------------
# MPC-HC / MPC-BE tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state_val,expected",
    [
        ("2", False),   # Playing (State_Running)
        (" 2 ", False), # Playing with whitespace
        ("1", True),    # Paused (State_Paused)
        ("0", True),    # Stopped (State_Stopped)
        ("-1", True),   # Closed / no file
        ("", None),     # Empty state
        ("99", None),   # Unknown state
    ],
)
def test_mpc_is_paused_state_mapping(monkeypatch, state_val, expected):
    mpc = mpc_mod.MPCIntegration(base_url="http://localhost:13579")
    mpc.working_port = 13579
    html = f'<p id="file">movie.mkv</p><p id="state">{state_val}</p>'
    monkeypatch.setattr(mpc.session, "get", lambda url, timeout=0.5: _FakeHTTPResponse(200, text=html))
    assert mpc.is_paused() is expected


def test_mpc_is_paused_returns_none_when_state_variable_omitted(monkeypatch):
    mpc = mpc_mod.MPCIntegration(base_url="http://localhost:13579")
    mpc.working_port = 13579
    html = '<p id="file">movie.mkv</p><p id="position">12000</p>'
    monkeypatch.setattr(mpc.session, "get", lambda url, timeout=0.5: _FakeHTTPResponse(200, text=html))
    assert mpc.is_paused() is None


def test_mpc_is_paused_falls_back_across_ports_on_connection_error(monkeypatch):
    mpc = mpc_mod.MPCIntegration(base_url="http://localhost:13579")
    requested_urls = []

    def fake_get(url, timeout=0.5):
        requested_urls.append(url)
        if ":13580/" in url:
            return _FakeHTTPResponse(200, text='<p id="state">1</p>')
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(mpc.session, "get", fake_get)
    assert mpc.is_paused() is True
    assert mpc.working_port == 13580
    assert requested_urls == [
        "http://localhost:13579/variables.html",
        "http://localhost:13580/variables.html",
    ]


def test_mpc_is_paused_returns_none_when_all_ports_unreachable(monkeypatch):
    mpc = mpc_mod.MPCIntegration(base_url="http://localhost:13579")

    def fake_get(url, timeout=0.5):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(mpc.session, "get", fake_get)
    assert mpc.is_paused() is None


def test_mpc_is_paused_uses_custom_base_url_port(monkeypatch):
    mpc = mpc_mod.MPCHCIntegration(base_url="http://localhost:14567")
    requested_urls = []

    def fake_get(url, timeout=0.5):
        requested_urls.append(url)
        if ":14567/" in url:
            return _FakeHTTPResponse(200, text='<p id="state">2</p>')
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(mpc.session, "get", fake_get)
    assert mpc.is_paused() is False
    assert requested_urls == ["http://localhost:14567/variables.html"]


# ---------------------------------------------------------------------------
# MPC-QT tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state_val,expected",
    [
        ("2", False),
        ("1", True),
        ("0", True),
        ("-1", True),
        ("", None),
        ("unknown", None),
    ],
)
def test_mpcqt_is_paused_state_mapping(monkeypatch, state_val, expected):
    mpcqt = mpcqt_mod.MPCQTIntegration(base_url="http://localhost:13579")
    mpcqt.working_port = 13579
    html = f'<p id="file">movie.mkv</p><p id="state">{state_val}</p>'
    monkeypatch.setattr(mpcqt.session, "get", lambda url, timeout=0.5: _FakeHTTPResponse(200, text=html))
    assert mpcqt.is_paused() is expected


def test_mpcqt_is_paused_returns_none_when_missing_state_or_unreachable(monkeypatch):
    mpcqt = mpcqt_mod.MPCQTIntegration(base_url="http://localhost:13579")
    monkeypatch.setattr(
        mpcqt.session,
        "get",
        lambda url, timeout=0.5: _FakeHTTPResponse(200, text='<p id="file">movie.mkv</p>'),
    )
    assert mpcqt.is_paused() is None

    def fail_get(url, timeout=0.5):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(mpcqt.session, "get", fail_get)
    assert mpcqt.is_paused() is None


# ---------------------------------------------------------------------------
# VLC tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state_val,expected",
    [
        ("playing", False),
        ("Playing", False),
        ("paused", True),
        ("PAUSED", True),
        ("stopped", True),
        ("Stopped", True),
        ("", None),
        ("buffering", None),
        (None, None),
    ],
)
def test_vlc_is_paused_state_mapping(monkeypatch, state_val, expected):
    vlc = vlc_mod.VLCIntegration()
    vlc.last_successful_config = {"port": 8080, "password": "secret"}
    payload = {"time": 120, "length": 1000}
    if state_val is not None:
        payload["state"] = state_val

    monkeypatch.setattr(
        vlc.session,
        "get",
        lambda url, timeout=1.0: _FakeHTTPResponse(200, json_data=payload),
    )
    assert vlc.is_paused() is expected


def test_vlc_is_paused_falls_back_across_configs_and_caches_success(monkeypatch):
    vlc = vlc_mod.VLCIntegration()
    vlc.vlc_config = {"port": 8080, "password": "wrong"}
    vlc.last_successful_config = None
    attempts = []

    def fake_get(url, timeout=1.0):
        attempts.append((url, vlc.session.auth))
        if url == "http://localhost:8080/requests/status.json" and vlc.session.auth == ("", "simkl"):
            return _FakeHTTPResponse(200, json_data={"state": "paused", "time": 50, "length": 1000})
        return _FakeHTTPResponse(401)

    monkeypatch.setattr(vlc.session, "get", fake_get)
    assert vlc.is_paused() is True
    assert vlc.last_successful_config == {"port": 8080, "password": "simkl"}
    assert len(attempts) >= 2


def test_vlc_is_paused_returns_none_on_invalid_json_or_unreachable(monkeypatch):
    vlc = vlc_mod.VLCIntegration()
    vlc.vlc_config = {"port": 8080, "password": ""}
    vlc.last_successful_config = {"port": 8080, "password": ""}

    monkeypatch.setattr(
        vlc.session,
        "get",
        lambda url, timeout=1.0: _FakeHTTPResponse(200, json_error=ValueError("bad json")),
    )
    assert vlc.is_paused() is None

    def fail_get(url, timeout=1.0):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(vlc.session, "get", fail_get)
    assert vlc.is_paused() is None


# ---------------------------------------------------------------------------
# PotPlayer & MPV / MPV wrappers tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,expected",
    [
        (2, False),   # Running / Playing
        (1, True),    # Paused
        (0, True),    # Stopped
        (-1, True),   # Stopped
        (99, None),   # Unknown
    ],
)
def test_potplayer_is_paused_state_mapping(monkeypatch, status, expected):
    potplayer = potplayer_mod.PotPlayerIntegration()
    potplayer.platform = "windows"
    monkeypatch.setattr(potplayer_mod, "win32gui", types.SimpleNamespace(SendMessage=lambda *a: status))
    monkeypatch.setattr(potplayer_mod, "win32con", types.SimpleNamespace(WM_USER=0x0400))
    monkeypatch.setattr(potplayer_mod, "find_potplayer_hwnd", lambda: 12345)
    assert potplayer.is_paused() is expected


def test_mpv_and_wrapper_is_paused(monkeypatch):
    mpv = mpv_mod.MPVIntegration()
    monkeypatch.setattr(mpv, "get_property", lambda prop: True)
    assert mpv.is_paused() is True

    monkeypatch.setattr(mpv, "get_property", lambda prop: False)
    assert mpv.is_paused() is False

    monkeypatch.setattr(mpv, "get_property", lambda prop: None)
    assert mpv.is_paused() is None

    wrapper = mpv_wrappers_mod.MPVWrapperIntegration()
    wrapper.mpv_integration = mpv
    monkeypatch.setattr(wrapper, "_get_custom_ipc_path", lambda proc: "/tmp/custom-mpv.sock")
    monkeypatch.setattr(mpv, "get_property", lambda prop: True)
    assert wrapper.is_paused("smplayer.exe") is True

    def raise_err(prop):
        raise mpv_mod.MPVError("boom")

    monkeypatch.setattr(mpv, "get_property", raise_err)
    assert wrapper.is_paused("smplayer.exe") is None


# ---------------------------------------------------------------------------
# MediaScrobbler integration: watch-time & unknown-state handling
# ---------------------------------------------------------------------------

def test_update_tracking_mpc_playing_paused_stopped_and_unknown(tmp_path, monkeypatch, isolated_scrobbler_env):
    _, scrobble_calls = isolated_scrobbler_env
    clock = _MutableClock(1000.0)
    monkeypatch.setattr(media_scrobbler_mod.time, "time", clock.time)

    scrobbler = _make_scrobbler(tmp_path, clock)
    mpc = mpc_mod.MPCIntegration(base_url="http://localhost:13579")
    mpc.working_port = 13579
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: mpc)
    monkeypatch.setattr(scrobbler, "get_current_filepath", lambda proc: "/movies/Inception.mkv")

    current_html = {'body': '<p id="state">2</p><p id="position">105000</p><p id="duration">1000000</p>'}
    monkeypatch.setattr(mpc.session, "get", lambda url, timeout=0.5: _FakeHTTPResponse(200, text=current_html['body']))

    win = {"process_name": "mpc-hc64.exe", "title": "Inception.mkv - Media Player Classic Home Cinema"}

    # 1. Playing (state=2): accumulates 5s
    clock.advance(5.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PLAYING
    assert scrobbler.watch_time == pytest.approx(5.0)
    assert scrobble_calls[-1]["action"] == "start"

    # 2. Paused (state=1): suspends accumulation immediately and transitions to PAUSED
    current_html['body'] = '<p id="state">1</p><p id="position">105000</p><p id="duration">1000000</p>'
    clock.advance(10.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PAUSED
    assert scrobbler.watch_time == pytest.approx(5.0)
    assert scrobble_calls[-1]["action"] == "pause"

    # 3. Still paused for several polling intervals: watch_time must not grow
    clock.advance(20.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PAUSED
    assert scrobbler.watch_time == pytest.approx(5.0)

    # 4. Missing state variable while paused: unknown state skips interval and stays PAUSED
    current_html['body'] = '<p id="position">105000</p><p id="duration">1000000</p>'
    clock.advance(20.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PAUSED
    assert scrobbler.watch_time == pytest.approx(5.0)

    # 5. Stopped (state=0) while file remains tracked: remains PAUSED, no accumulation
    current_html['body'] = '<p id="state">0</p><p id="position">0</p><p id="duration">1000000</p>'
    clock.advance(20.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PAUSED
    assert scrobbler.watch_time == pytest.approx(5.0)

    # 6. Resumed playing (state=2): transitions back to PLAYING without adding paused interval
    current_html['body'] = '<p id="state">2</p><p id="position">110000</p><p id="duration">1000000</p>'
    clock.advance(10.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PLAYING
    assert scrobbler.watch_time == pytest.approx(5.0)

    # 7. Confirmed playing interval: accumulates 8s
    current_html['body'] = '<p id="state">2</p><p id="position">118000</p><p id="duration">1000000</p>'
    clock.advance(8.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PLAYING
    assert scrobbler.watch_time == pytest.approx(13.0)


def test_update_tracking_unknown_state_while_playing_skips_interval_and_recovery_interval(
    tmp_path, monkeypatch, isolated_scrobbler_env
):
    clock = _MutableClock(2000.0)
    monkeypatch.setattr(media_scrobbler_mod.time, "time", clock.time)

    scrobbler = _make_scrobbler(tmp_path, clock)
    vlc = vlc_mod.VLCIntegration()
    vlc.last_successful_config = {"port": 8080, "password": ""}
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: vlc)
    monkeypatch.setattr(scrobbler, "get_current_filepath", lambda proc: "/movies/Inception.mkv")
    monkeypatch.setattr(scrobbler, "get_player_position_duration", lambda proc: (100.0, 1000.0))

    win = {"process_name": "vlc.exe", "title": "Inception.mkv - VLC media player"}

    # Missing state in status.json -> unknown -> skips accumulation
    monkeypatch.setattr(
        vlc.session,
        "get",
        lambda url, timeout=1.0: _FakeHTTPResponse(200, json_data={"time": 100, "length": 1000}),
    )
    clock.advance(15.0)
    scrobbler._update_tracking(win)
    assert scrobbler.watch_time == pytest.approx(0.0)

    # Connection error while reading state -> unknown -> skips accumulation
    def fail_get(url, timeout=1.0):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(vlc.session, "get", fail_get)
    clock.advance(15.0)
    scrobbler._update_tracking(win)
    assert scrobbler.watch_time == pytest.approx(0.0)

    # First confirmed playing poll after unknown intervals does not retroactively add unknown time
    monkeypatch.setattr(
        vlc.session,
        "get",
        lambda url, timeout=1.0: _FakeHTTPResponse(200, json_data={"state": "playing", "time": 105, "length": 1000}),
    )
    clock.advance(10.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PLAYING
    assert scrobbler.watch_time == pytest.approx(0.0)

    # Subsequent confirmed playing poll accumulates normally
    clock.advance(6.0)
    scrobbler._update_tracking(win)
    assert scrobbler.watch_time == pytest.approx(6.0)


def test_update_tracking_vlc_pausing_suspends_accumulation(tmp_path, monkeypatch, isolated_scrobbler_env):
    _, scrobble_calls = isolated_scrobbler_env
    clock = _MutableClock(3000.0)
    monkeypatch.setattr(media_scrobbler_mod.time, "time", clock.time)

    scrobbler = _make_scrobbler(tmp_path, clock)
    vlc = vlc_mod.VLCIntegration()
    vlc.last_successful_config = {"port": 8080, "password": ""}
    monkeypatch.setattr(scrobbler, "_get_player_integration", lambda name: vlc)
    monkeypatch.setattr(scrobbler, "get_current_filepath", lambda proc: "/movies/Inception.mkv")
    monkeypatch.setattr(scrobbler, "get_player_position_duration", lambda proc: (200.0, 1000.0))

    win = {"process_name": "vlc.exe", "title": "Inception.mkv - VLC media player"}

    monkeypatch.setattr(
        vlc.session,
        "get",
        lambda url, timeout=1.0: _FakeHTTPResponse(200, json_data={"state": "paused", "time": 200, "length": 1000}),
    )
    clock.advance(10.0)
    scrobbler._update_tracking(win)
    assert scrobbler.state == PAUSED
    assert scrobbler.watch_time == pytest.approx(0.0)
    assert scrobble_calls[-1]["action"] == "pause"

    # Title keyword still detects pause even if integration returns None
    monkeypatch.setattr(vlc, "is_paused", lambda: None)
    assert scrobbler._detect_playback_state({"process_name": "vlc.exe", "title": "Inception.mkv [Paused]"}) == PAUSED
    assert scrobbler._detect_playback_state(win) is None
