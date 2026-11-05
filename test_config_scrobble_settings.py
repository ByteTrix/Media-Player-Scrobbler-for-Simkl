import importlib
import pathlib
import sys
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parent
PACKAGE_ROOT = REPO_ROOT / "simkl_mps"

if "simkl_mps" not in sys.modules:
    package = types.ModuleType("simkl_mps")
    package.__path__ = [str(PACKAGE_ROOT)]
    sys.modules["simkl_mps"] = package

config_manager_module = importlib.import_module("simkl_mps.config_manager")


def test_scrobble_settings_defaults():
    defaults = config_manager_module.DEFAULT_SETTINGS
    assert defaults["enable_realtime_scrobble"] is True
    assert defaults["enable_playback_resume"] is True
    assert defaults["resume_start_tolerance_seconds"] == 30
    assert defaults["min_rewatch_watch_seconds"] == 180
