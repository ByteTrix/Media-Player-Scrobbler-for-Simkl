"""
Entry point for launching the correct tray application for the current platform.
"""
import sys
from simkl_mps.main import get_tray_app

if __name__ == "__main__":
    _, run_tray_app = get_tray_app()
    sys.exit(run_tray_app())
