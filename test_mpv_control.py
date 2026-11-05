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

mpv_module = importlib.import_module("simkl_mps.players.mpv")
mpv_wrappers_module = importlib.import_module("simkl_mps.players.mpv_wrappers")


@pytest.fixture
def mpv_integration(monkeypatch):
    integration = mpv_module.MPVIntegration()
    # Stub internal IPC operations
    monkeypatch.setattr(integration, "_connect", lambda: None)
    monkeypatch.setattr(integration, "_disconnect", lambda: None)
    return integration


def test_seek_absolute_sends_expected_command(mpv_integration, monkeypatch):
    captured_commands = []

    def fake_send(command):
        captured_commands.append(command)
        return 1

    def fake_receive(timeout=None):
        return {"request_id": 1, "error": "success"}

    monkeypatch.setattr(mpv_integration, "_send_command", fake_send)
    monkeypatch.setattr(mpv_integration, "_receive_response", fake_receive)

    ok = mpv_integration.seek_absolute(754.333)
    assert ok is True
    assert captured_commands == [["seek", 754.33, "absolute"]]


def test_show_osd_sends_expected_command(mpv_integration, monkeypatch):
    captured_commands = []

    def fake_send(command):
        captured_commands.append(command)
        return 42

    def fake_receive(timeout=None):
        return {"request_id": 42, "error": "success"}

    monkeypatch.setattr(mpv_integration, "_send_command", fake_send)
    monkeypatch.setattr(mpv_integration, "_receive_response", fake_receive)

    ok = mpv_integration.show_osd("hello", 3500)
    assert ok is True
    assert captured_commands == [["show-text", "hello", 3500]]


def test_run_command_returns_false_on_error_response(mpv_integration, monkeypatch):
    def fake_send(command):
        return 1

    def fake_receive(timeout=None):
        return {"request_id": 1, "error": "property unavailable"}

    monkeypatch.setattr(mpv_integration, "_send_command", fake_send)
    monkeypatch.setattr(mpv_integration, "_receive_response", fake_receive)

    ok = mpv_integration._run_command(["test-command"])
    assert ok is False


def test_run_command_returns_false_when_not_connected(mpv_integration, monkeypatch):
    def fake_connect():
        raise mpv_module.MPVError("Cannot connect")

    monkeypatch.setattr(mpv_integration, "_connect", fake_connect)

    ok = mpv_integration._run_command(["test-command"])
    assert ok is False


def test_wrapper_delegates():
    wrapper = mpv_wrappers_module.MPVWrapperIntegration()
    
    class FakeMPV:
        def __init__(self):
            self.calls = []

        def seek_absolute(self, seconds):
            self.calls.append(("seek_absolute", seconds))
            return True

        def show_osd(self, text, duration_ms=3500):
            self.calls.append(("show_osd", text, duration_ms))
            return True

    fake_mpv = FakeMPV()
    wrapper.mpv_integration = fake_mpv

    assert wrapper.seek_absolute(123.45) is True
    assert fake_mpv.calls[0] == ("seek_absolute", 123.45)

    assert wrapper.show_osd("Test OSD", 2000) is True
    assert fake_mpv.calls[1] == ("show_osd", "Test OSD", 2000)
