"""
Media Player Scrobbler for SIMKL package.
"""

__version__ = "2.0.4"
__author__ = "kavinthangavel"

# Apply compatibility patches first, before any other imports
import simkl_mps.compatibility_patches
simkl_mps.compatibility_patches.apply_patches()

from simkl_mps.main import SimklScrobbler, run_as_background_service, main
from simkl_mps.tray_app import run_tray_app
__all__ = [
    'SimklScrobbler',
    'run_as_background_service',
    'main',
    'run_tray_app',
    # 'run_service' # Removed as it's not defined/imported here
]