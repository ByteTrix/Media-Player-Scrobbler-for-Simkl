"""
Simkl Scrobbler - Automatically track and scrobble movies to Simkl
"""

__version__ = "1.0.0"
__author__ = "kavinthangavel"

from .main import SimklScrobbler, run_as_background_service, main
from .tray_app import run_tray_app
from .service_runner import run_service

__all__ = [
    'SimklScrobbler',
    'run_as_background_service',
    'main',
    'run_tray_app',
    'run_service'
]