"""
Media player integrations for Media Player Scrobbler for SIMKL.
"""

from simkl_mps.players.vlc import VLCIntegration
from simkl_mps.players.mpv import MPVIntegration
from simkl_mps.players.mpc import MPCHCIntegration, MPCIntegration
from simkl_mps.players.mpcqt import MPCQTIntegration
from simkl_mps.players.mpv_wrappers import MPVWrapperIntegration

__all__ = [
    'VLCIntegration',
    'MPVIntegration',
    'MPCHCIntegration',
    'MPCIntegration',
    'MPCQTIntegration',
    'MPVWrapperIntegration'
]