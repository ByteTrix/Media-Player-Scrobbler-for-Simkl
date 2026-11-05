"""Safety checks for the PyInstaller spec and Windows build helper."""

import ast
import os
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / "simkl-mps.spec"


def _load_spec_function(name):
    tree = ast.parse(SPEC_FILE.read_text(encoding="utf-8"), str(SPEC_FILE))
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {"os": os, "time": types.SimpleNamespace(sleep=lambda _s: None)}
    module = ast.Module(body=[func], type_ignores=[])
    exec(compile(module, str(SPEC_FILE), "exec"), namespace)
    return namespace[name]


class _FakeProc:
    def __init__(self, pid, exe):
        self.pid = pid
        self.info = {"pid": pid, "exe": exe}
        self.terminated = False

    def terminate(self):
        self.terminated = True


def _fake_psutil(procs):
    fake = types.ModuleType("psutil")
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.process_iter = lambda attrs: list(procs)
    fake.wait_procs = lambda procs, timeout: (procs, [])
    return fake


def test_spec_does_not_kill_processes_by_image_name():
    source = SPEC_FILE.read_text(encoding="utf-8")
    assert "taskkill" not in source
    assert "/IM" not in source


def test_spec_only_stops_dist_processes_when_opted_in():
    tree = ast.parse(SPEC_FILE.read_text(encoding="utf-8"))
    cleanup = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cleanup_build_artifacts")
    calls = [n for n in ast.walk(cleanup) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "stop_dist_processes"]
    assert calls, "cleanup should delegate to stop_dist_processes"
    guarded = [n for n in ast.walk(cleanup) if isinstance(n, ast.If) and "MPSS_BUILD_STOP_DIST_PROCESSES" in ast.unparse(n.test)]
    assert guarded and any(call in ast.walk(guarded[0]) for call in calls)


def test_stop_dist_processes_ignores_installed_app(tmp_path, monkeypatch):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    installed_dir = tmp_path / "Program Files" / "MPS for Simkl"
    installed_dir.mkdir(parents=True)

    build_tray = _FakeProc(1, str(dist_dir / "MPS for Simkl.exe"))
    build_cli = _FakeProc(2, str(dist_dir / "MPSS.exe"))
    installed_tray = _FakeProc(3, str(installed_dir / "MPS for Simkl.exe"))
    installed_cli = _FakeProc(4, str(installed_dir / "MPSS.exe"))
    sibling_dist = _FakeProc(5, str(tmp_path / "dist_other" / "MPSS.exe"))
    unrelated_in_dist = _FakeProc(6, str(dist_dir / "python.exe"))
    no_exe = _FakeProc(7, None)
    procs = [build_tray, build_cli, installed_tray, installed_cli, sibling_dist, unrelated_in_dist, no_exe]

    fake = _fake_psutil(procs)
    monkeypatch.setitem(sys.modules, "psutil", fake)
    stop_dist_processes = _load_spec_function("stop_dist_processes")
    stop_dist_processes(str(dist_dir))

    assert build_tray.terminated and build_cli.terminated
    assert not installed_tray.terminated
    assert not installed_cli.terminated
    assert not sibling_dist.terminated
    assert not unrelated_in_dist.terminated


@pytest.mark.parametrize("pattern", [".env", "credentials.json", "token"])
def test_spec_does_not_bundle_secret_files(pattern):
    tree = ast.parse(SPEC_FILE.read_text(encoding="utf-8"))
    bundled = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(pattern)
    ]
    assert not bundled


def test_bundled_data_dirs_contain_no_env_files():
    for rel in ("simkl_mps/assets", "simkl_mps/watch-history-viewer"):
        names = [p.name.lower() for p in (PROJECT_ROOT / rel).rglob("*") if p.is_file()]
        assert not [n for n in names if n == ".env" or n.endswith(".env")], rel


def test_installer_helper_does_not_print_client_id():
    source = (PROJECT_ROOT / "build_windows_installer.py").read_text(encoding="utf-8")
    assert "client_id[:" not in source
    assert "client_secret[:" not in source
