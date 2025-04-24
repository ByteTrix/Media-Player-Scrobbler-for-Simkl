"""
Media Player Scrobbler for SIMKL package.
"""

__version__ = "2.0.0"
__author__ = "kavinthangavel"

from simkl_mps.compatibility_patches import apply_patches
apply_patches()

from simkl_mps.main import SimklScrobbler, run_as_background_service, main
from simkl_mps.tray_app import run_tray_app
__all__ = [
    'SimklScrobbler',
    'run_as_background_service',
    'main',
    'run_tray_app',
    'run_service'
]