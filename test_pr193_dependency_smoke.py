"""Smoke tests for the dependency set locked by PR #193.

These check that the installed environment matches poetry.lock for the
packages the app and test suite rely on, and that the bumped libraries still
work the way simkl_mps and simkl-mps.spec use them.
"""

import importlib
import os
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent

# Runtime, Windows integration, and test/build packages whose installed version
# should match the lockfile. Lint-only tools are optional in local venvs.
LOCK_CHECKED_PACKAGES = [
    "guessit",
    "rebulk",
    "babelfish",
    "requests",
    "python-dotenv",
    "psutil",
    "pystray",
    "pillow",
    "plyer",
    "colorama",
    "winotify",
    "pygetwindow",
    "pywin32",
    "pytest",
    "pytest-mock",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "flake8",
    "pyflakes",
    "pycodestyle",
    "types-requests",
]


def _locked_versions():
    with open(PROJECT_ROOT / "poetry.lock", "rb") as f:
        lock = tomllib.load(f)
    return {pkg["name"].lower(): pkg["version"] for pkg in lock["package"]}


def test_lockfile_lists_checked_packages():
    locked = _locked_versions()
    missing = [name for name in LOCK_CHECKED_PACKAGES if name not in locked]
    assert not missing


@pytest.mark.parametrize("name", LOCK_CHECKED_PACKAGES)
def test_installed_version_matches_lock(name):
    locked = _locked_versions()[name]
    try:
        installed = metadata.version(name)
    except metadata.PackageNotFoundError:
        pytest.skip(f"{name} is not installed in this environment")
    assert installed == locked, f"{name}: installed {installed}, poetry.lock has {locked}"


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("The.Matrix.1999.1080p.BluRay.x264.mkv", {"type": "movie", "title": "The Matrix", "year": 1999}),
        ("Breaking.Bad.S02E05.720p.HDTV.x264.mkv", {"type": "episode", "title": "Breaking Bad", "season": 2, "episode": 5}),
    ],
)
def test_guessit_parses_media_filenames(filename, expected):
    from guessit import guessit

    result = guessit(filename)
    for key, value in expected.items():
        assert result.get(key) == value


def test_guessit_and_babelfish_data_dirs_exist_for_spec():
    # simkl-mps.spec bundles these directories and silently skips missing ones.
    import babelfish
    import guessit

    assert (Path(guessit.__file__).parent / "config").is_dir()
    assert (Path(babelfish.__file__).parent / "data").is_dir()


def test_dotenv_values_reads_file(tmp_path):
    from dotenv import dotenv_values

    env_file = tmp_path / ".env"
    env_file.write_text("SIMKL_CLIENT_ID=dummy-id\nSIMKL_CLIENT_SECRET='dummy secret'\n", encoding="utf-8")
    assert dotenv_values(env_file) == {"SIMKL_CLIENT_ID": "dummy-id", "SIMKL_CLIENT_SECRET": "dummy secret"}


@pytest.mark.parametrize(
    "module",
    [
        "simkl_mps.config_manager",
        "simkl_mps.simkl_api",
        "simkl_mps.media_scrobbler",
        "simkl_mps.window_detection",
        "simkl_mps.players",
        "simkl_mps.players.mpv",
        "simkl_mps.players.mpv_wrappers",
        "simkl_mps.players.vlc",
        "simkl_mps.players.mpc",
        "simkl_mps.players.mpcqt",
        "simkl_mps.players.potplayer",
    ],
)
def test_app_modules_import(module):
    importlib.import_module(module)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows integration modules")
@pytest.mark.parametrize("module", ["win32api", "win32con", "win32gui", "win32process", "pygetwindow", "winotify", "pystray"])
def test_windows_integration_modules_import(module):
    importlib.import_module(module)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific window detection")
def test_window_detection_lists_windows_without_error():
    from simkl_mps import window_detection

    windows = window_detection.get_all_windows_info()
    assert isinstance(windows, list)


def test_pyinstaller_hooks_importable():
    pytest.importorskip("PyInstaller")
    from PyInstaller.utils.hooks import collect_data_files

    assert collect_data_files("guessit")


def test_flake8_runs_with_locked_pyflakes():
    pytest.importorskip("flake8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "flake8", "--isolated", "--select=E9,F63,F7,F82", "simkl_mps"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
