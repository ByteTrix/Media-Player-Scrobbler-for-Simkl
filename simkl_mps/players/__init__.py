"""
Media player integrations for Media Player Scrobbler for SIMKL.
"""

from .vlc import VLCIntegration
from .mpv import create_mpv_integration, MPVIntegration
from .mpc import MPCHCIntegration, MPCIntegration
from .potplayer import PotPlayerIntegration

__all__ = [
    'VLCIntegration',
    'create_mpv_integration', 
    'MPVIntegration',
    'MPCHCIntegration',
    'MPCIntegration',
    'PotPlayerIntegration'
]