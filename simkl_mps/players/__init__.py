"""
Media player integrations for Media Player Scrobbler for SIMKL.
"""

from simkl_mps.players.vlc import VLCIntegration
from simkl_mps.players.mpv import MPVIntegration
from simkl_mps.players.mpc import MPCHCIntegration, MPCIntegration
from simkl_mps.players.infuse import InfuseIntegration

__all__ = [
    'VLCIntegration',
    'MPVIntegration',
    'MPCHCIntegration',
    'MPCIntegration',
    'InfuseIntegration'
]