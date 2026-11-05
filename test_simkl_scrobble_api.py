import importlib
import pathlib
import sys
import types
import requests

REPO_ROOT = pathlib.Path(__file__).resolve().parent
PACKAGE_ROOT = REPO_ROOT / "simkl_mps"

if "simkl_mps" not in sys.modules:
    package = types.ModuleType("simkl_mps")
    package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["simkl_mps"] = package

simkl_api = importlib.import_module("simkl_mps.simkl_api")


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def test_scrobble_lock_400_is_reported_as_throttling(monkeypatch, caplog):
    monkeypatch.setattr(simkl_api.requests, "post", lambda *a, **kw:
                        FakeResponse(400, {"error": "RATE_LIMIT"}, '{"error":"RATE_LIMIT"}'))
    res = simkl_api.scrobble("start", {"movie": {"ids": {"simkl": 123}}}, 10, "cid", "tok")
    assert res["ok"] is False
    assert res["status"] == 400
    assert "throttled (status 400" in caplog.text


def test_scrobble_posts_body_and_params(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, params=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse(200, {"action": "pause", "progress": 42.5})

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)

    item = {"movie": {"title": "Inception", "ids": {"simkl": 123}}}
    res = simkl_api.scrobble("pause", item, 42.5, "cid", "tok")

    assert res["ok"] is True
    assert res["status"] == 200
    assert captured["url"] == f"{simkl_api.SIMKL_API_BASE_URL}/scrobble/pause"
    assert captured["json"] == {
        "movie": {"title": "Inception", "ids": {"simkl": 123}},
        "progress": 42.5,
    }
    assert captured["params"]["client_id"] == "cid"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["headers"]["simkl-api-key"] == "cid"


def test_scrobble_409_on_stop_is_already_completed(monkeypatch):
    # Documented: stopping a session already completed within the last hour returns 409.
    def fake_post(*args, **kwargs):
        return FakeResponse(409, {"watched_at": "2026-11-04T10:00:00Z", "expires_at": "2026-11-04T11:00:00Z"})

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)
    res = simkl_api.scrobble("stop", {"movie": {}}, 95.0, "cid", "tok")
    assert res["ok"] is True
    assert res["status"] == 409
    assert res["already_completed"] is True


def test_scrobble_409_on_start_or_pause_is_failure(monkeypatch):
    monkeypatch.setattr(simkl_api.requests, "post", lambda *a, **kw: FakeResponse(409, {}, text="conflict"))
    for action in ("start", "pause"):
        res = simkl_api.scrobble(action, {"movie": {}}, 10.0, "cid", "tok")
        assert res["ok"] is False
        assert res["status"] == 409


def test_scrobble_429_lock_is_failure(monkeypatch):
    monkeypatch.setattr(simkl_api.requests, "post", lambda *a, **kw: FakeResponse(429, {}, text="locked"))
    res = simkl_api.scrobble("pause", {"movie": {}}, 40.0, "cid", "tok")
    assert res["ok"] is False
    assert res["status"] == 429


def test_scrobble_returns_server_action(monkeypatch):
    monkeypatch.setattr(simkl_api.requests, "post", lambda *a, **kw: FakeResponse(201, {"action": "pause", "progress": 85}))
    res = simkl_api.scrobble("stop", {"movie": {}}, 85.0, "cid", "tok", min_progress=90)
    assert res["ok"] is True
    assert res["server_action"] == "pause"
    assert res["already_completed"] is False


def test_scrobble_min_progress_sent_on_start_and_stop_only(monkeypatch):
    captured = []

    def fake_post(url, headers=None, json=None, params=None, timeout=None):
        captured.append((url.rsplit("/", 1)[-1], dict(params), dict(json)))
        return FakeResponse(201, {})

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)
    for action in ("start", "pause", "stop"):
        simkl_api.scrobble(action, {"movie": {"ids": {"simkl": 1}}}, 50.0, "cid", "tok", min_progress=92.7)

    by_action = {a: (params, body) for a, params, body in captured}
    assert by_action["start"][0]["min_progress"] == 92
    assert by_action["stop"][0]["min_progress"] == 92
    assert "min_progress" not in by_action["pause"][0]
    # Only valid in the URL, never in the body
    assert all("min_progress" not in body for _, _, body in captured)
    # Rewatch is never requested from the realtime scrobble path
    assert all("allow_rewatch" not in params for _, params, _ in captured)


def test_scrobble_without_min_progress_uses_server_default(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, params=None, timeout=None):
        captured["params"] = params
        return FakeResponse(201, {})

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)
    simkl_api.scrobble("stop", {"movie": {}}, 50.0, "cid", "tok")
    assert "min_progress" not in captured["params"]


def test_normalize_scrobble_min_progress():
    assert simkl_api.normalize_scrobble_min_progress(80) == 80
    assert simkl_api.normalize_scrobble_min_progress(90.9) == 90
    assert simkl_api.normalize_scrobble_min_progress(30) == 50
    assert simkl_api.normalize_scrobble_min_progress(150) == 100
    assert simkl_api.normalize_scrobble_min_progress(None) is None
    assert simkl_api.normalize_scrobble_min_progress(0) is None
    assert simkl_api.normalize_scrobble_min_progress("bad") is None


def test_scrobble_400_is_failure_without_raising(monkeypatch):
    def fake_post(*args, **kwargs):
        return FakeResponse(400, {"error": "RATE_LIMIT"})

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)
    res = simkl_api.scrobble("start", {"movie": {}}, 10.0, "cid", "tok")
    assert res["ok"] is False
    assert res["status"] == 400


def test_scrobble_network_error_returns_not_ok(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)
    res = simkl_api.scrobble("pause", {"movie": {}}, 50.0, "cid", "tok")
    assert res["ok"] is False
    assert res["status"] is None
    assert "network down" in str(res["error"])


def test_scrobble_rejects_unknown_action(monkeypatch):
    called = []

    def fake_post(*args, **kwargs):
        called.append(True)
        return FakeResponse(200)

    monkeypatch.setattr(simkl_api.requests, "post", fake_post)
    res = simkl_api.scrobble("seek", {"movie": {}}, 50.0, "cid", "tok")
    assert res["ok"] is False
    assert len(called) == 0


def test_get_playback_sessions_paths(monkeypatch):
    captured_urls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        captured_urls.append(url)
        if "episodes" in url:
            return FakeResponse(200, [{"id": 1, "type": "episode"}])
        elif url.endswith("/sync/playback"):
            return FakeResponse(200, [{"id": 2, "type": "movie"}])
        return FakeResponse(404, None)

    monkeypatch.setattr(simkl_api.requests, "get", fake_get)

    res_ep = simkl_api.get_playback_sessions("cid", "tok", media_type="episodes")
    assert res_ep == [{"id": 1, "type": "episode"}]
    assert captured_urls[-1] == f"{simkl_api.SIMKL_API_BASE_URL}/sync/playback/episodes"

    res_all = simkl_api.get_playback_sessions("cid", "tok")
    assert res_all == [{"id": 2, "type": "movie"}]
    assert captured_urls[-1] == f"{simkl_api.SIMKL_API_BASE_URL}/sync/playback"


def test_delete_playback_uses_delete_method(monkeypatch):
    captured = {}

    def fake_delete(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(200, {"result": "ok"})

    monkeypatch.setattr(simkl_api.requests, "delete", fake_delete)

    ok = simkl_api.delete_playback(12345, "cid", "tok")
    assert ok is True
    assert captured["url"] == f"{simkl_api.SIMKL_API_BASE_URL}/sync/playback/12345"
    assert captured["headers"]["Authorization"] == "Bearer tok"
