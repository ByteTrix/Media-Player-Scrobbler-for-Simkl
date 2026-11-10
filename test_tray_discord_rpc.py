import pytest
from unittest.mock import MagicMock, patch
from simkl_mps.config_manager import get_setting, set_setting
from simkl_mps.tray_base import TrayAppBase

class FakeTrayApp(TrayAppBase):
    def __init__(self):
        self.status = "stopped"
        self._auth_in_progress = False
        self._media_scrobbler = MagicMock()
        self.notifications_shown = []

    def _get_media_scrobbler(self):
        return self._media_scrobbler

    def update_icon(self):
        pass

    def show_notification(self, title, message):
        self.notifications_shown.append((title, message))

    def _ask_custom_threshold_dialog(self, current_threshold): pass
    def _ask_custom_min_watch_time_dialog(self, current_seconds): pass
    def _ask_directory_filter_dialog(self, title, current_dirs): pass
    def exit_app(self, _=None): pass
    def run(self): pass
    def show_about(self, _=None): pass
    def show_help(self, _=None): pass


def test_toggle_discord_rpc_menu_action(tmp_path):
    app = FakeTrayApp()
    
    # Ensure starting state is True
    set_setting("enable_discord_rpc", True)
    assert get_setting("enable_discord_rpc", True) is True

    # Call toggle_discord_rpc -> toggles to False
    app.toggle_discord_rpc()
    assert get_setting("enable_discord_rpc", True) is False
    assert app._media_scrobbler.discord_rpc.clear_presence.called

    # Call toggle_discord_rpc again -> toggles back to True
    app.toggle_discord_rpc()
    assert get_setting("enable_discord_rpc", True) is True
    assert app._media_scrobbler._sync_discord_presence.called
