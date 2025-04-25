"""
Media player integrations for Media Player Scrobbler for SIMKL.
"""

from simkl_mps.players.vlc import VLCIntegration
from simkl_mps.players.mpv import create_mpv_integration, MPVIntegration
from simkl_mps.players.mpc import MPCHCIntegration, MPCIntegration
from simkl_mps.players.potplayer import PotPlayerIntegration
from simkl_mps.players.infuse import InfuseIntegration

__all__ = [
    'VLCIntegration',
    'create_mpv_integration', 
    'MPVIntegration',
    'MPCHCIntegration',
    'MPCIntegration',
    'PotPlayerIntegration',
    'InfuseIntegration'
]