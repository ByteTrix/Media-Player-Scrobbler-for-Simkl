"""Regression tests for MPV wrapper custom IPC path argument forwarding."""
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

mpv_wrappers_module = importlib.import_module("simkl_mps.players.mpv_wrappers")

DEFAULT_IPC = "default-ipc"
CUSTOM_IPC = "custom-ipc"
PROCESS = "smplayer.exe"


class FakeMPV:
    """Records each call together with the IPC path active at call time."""

    def __init__(self):
        self.ipc_path = DEFAULT_IPC
        self.calls = []
        self.raise_exc = None

    def _record(self, *call):
        self.calls.append(call + (self.ipc_path,))
        if self.raise_exc is not None:
            raise self.raise_exc

    def get_position_duration(self, process_name=None):
        self._record("get_position_duration", process_name)
        return 12.0, 3600.0

    def get_current_filepath(self):
        self._record("get_current_filepath")
        return "C:/movies/Movie (2020).mkv"

    def is_paused(self):
        self._record("is_paused")
        return True

    def seek_absolute(self, seconds):
        self._record("seek_absolute", seconds)
        return True

    def show_osd(self, text, duration_ms=3500):
        self._record("show_osd", text, duration_ms)
        return True


@pytest.fixture
def wrapper(monkeypatch):
    instance = mpv_wrappers_module.MPVWrapperIntegration()
    fake = FakeMPV()
    instance.mpv_integration = fake
    lookups = []

    def fake_custom_ipc(process_name):
        lookups.append(process_name)
        return CUSTOM_IPC if process_name == PROCESS else None

    # Never read real player configs during tests
    monkeypatch.setattr(instance, "_get_custom_ipc_path", fake_custom_ipc)
    monkeypatch.setattr(instance, "is_mpv_wrapper", lambda name: bool(name))
    monkeypatch.setattr(
        instance, "get_wrapper_info", lambda name: (name, "SMPlayer", None) if name else (None, None, None)
    )
    instance.lookups = lookups
    return instance


def test_get_position_duration_custom_ipc_positional(wrapper):
    assert wrapper.get_position_duration(PROCESS) == (12.0, 3600.0)
    assert wrapper.mpv_integration.calls == [("get_position_duration", PROCESS, CUSTOM_IPC)]
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC
    assert wrapper.lookups == [PROCESS]


def test_get_position_duration_custom_ipc_keyword(wrapper):
    assert wrapper.get_position_duration(process_name=PROCESS) == (12.0, 3600.0)
    assert wrapper.mpv_integration.calls == [("get_position_duration", PROCESS, CUSTOM_IPC)]
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


@pytest.mark.parametrize("call", [
    lambda w: w.get_current_filepath(PROCESS),
    lambda w: w.get_current_filepath(process_name=PROCESS),
])
def test_get_current_filepath_custom_ipc(wrapper, call):
    assert call(wrapper) == "C:/movies/Movie (2020).mkv"
    assert wrapper.mpv_integration.calls == [("get_current_filepath", CUSTOM_IPC)]
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


@pytest.mark.parametrize("call", [
    lambda w: w.is_paused(PROCESS),
    lambda w: w.is_paused(process_name=PROCESS),
])
def test_is_paused_custom_ipc(wrapper, call):
    assert call(wrapper) is True
    assert wrapper.mpv_integration.calls == [("is_paused", CUSTOM_IPC)]
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


@pytest.mark.parametrize("call", [
    lambda w: w.seek_absolute(120, PROCESS),
    lambda w: w.seek_absolute(120, process_name=PROCESS),
    lambda w: w.seek_absolute(seconds=120, process_name=PROCESS),
])
def test_seek_absolute_custom_ipc(wrapper, call):
    assert call(wrapper) is True
    assert wrapper.mpv_integration.calls == [("seek_absolute", 120, CUSTOM_IPC)]
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC
    assert wrapper.lookups == [PROCESS]


@pytest.mark.parametrize("call, expected_duration", [
    (lambda w: w.show_osd("Hello", 2000, PROCESS), 2000),
    (lambda w: w.show_osd("Hello", process_name=PROCESS), 3500),
    (lambda w: w.show_osd("Hello", duration_ms=2000, process_name=PROCESS), 2000),
    (lambda w: w.show_osd(text="Hello", process_name=PROCESS, duration_ms=2000), 2000),
])
def test_show_osd_custom_ipc(wrapper, call, expected_duration):
    assert call(wrapper) is True
    assert wrapper.mpv_integration.calls == [("show_osd", "Hello", expected_duration, CUSTOM_IPC)]
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


@pytest.mark.parametrize("call", [
    lambda w: w.get_position_duration("mpvnet.exe"),
    lambda w: w.seek_absolute(42),
    lambda w: w.seek_absolute(42, "mpvnet.exe"),
    lambda w: w.show_osd("Hi"),
    lambda w: w.get_current_filepath(),
    lambda w: w.is_paused(),
])
def test_no_custom_ipc_uses_default_path(wrapper, call):
    call(wrapper)
    assert len(wrapper.mpv_integration.calls) == 1
    assert wrapper.mpv_integration.calls[0][-1] == DEFAULT_IPC
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


@pytest.mark.parametrize("exc", [
    mpv_wrappers_module.MPVError("pipe gone"),
    RuntimeError("boom"),
])
@pytest.mark.parametrize("call, expected", [
    (lambda w: w.get_position_duration(PROCESS), (None, None)),
    (lambda w: w.get_current_filepath(PROCESS), None),
    (lambda w: w.is_paused(process_name=PROCESS), None),
    (lambda w: w.seek_absolute(120, PROCESS), False),
    (lambda w: w.show_osd("Hello", process_name=PROCESS), False),
])
def test_custom_ipc_errors_restore_path(wrapper, exc, call, expected):
    wrapper.mpv_integration.raise_exc = exc
    assert call(wrapper) == expected
    # Call ran on the custom path and the default was restored afterwards
    assert wrapper.mpv_integration.calls[0][-1] == CUSTOM_IPC
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


def test_no_custom_ipc_errors_propagate(wrapper):
    wrapper.mpv_integration.raise_exc = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        wrapper.seek_absolute(5)
    assert wrapper.mpv_integration.ipc_path == DEFAULT_IPC


def test_invalid_arguments_raise_type_error(wrapper):
    with pytest.raises(TypeError):
        wrapper.seek_absolute()
    with pytest.raises(TypeError):
        wrapper.seek_absolute(1, PROCESS, process_name=PROCESS)
    assert wrapper.mpv_integration.calls == []
