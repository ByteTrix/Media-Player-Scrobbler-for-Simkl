"""
Base tray implementation for Media Player Scrobbler for SIMKL.
Provides common functionality for all platform-specific tray implementations.
"""

import os
import sys
import time
import threading
import queue # Added for thread-safe communication for custom threshold dialog
import logging
import webbrowser
import subprocess
import re
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from PIL import Image, ImageDraw, ImageFont
import abc
import pystray
import tkinter as tk
from tkinter import messagebox

if TYPE_CHECKING:
    from simkl_mps.main import SimklScrobbler
    from simkl_mps.media_scrobbler import MediaScrobbler
    from simkl_mps.watch_history_manager import WatchHistoryManager

# Import API and credential functions
from simkl_mps.simkl_api import get_user_settings, pin_auth_flow
from simkl_mps.credentials import get_credentials
# Import constants only, not the whole module
from simkl_mps.main import APP_DATA_DIR, APP_NAME
# Import settings functions
from simkl_mps.config_manager import get_setting, set_setting, DEFAULT_THRESHOLD

logger = logging.getLogger(__name__)

DEFAULT_DONATION_URL = "https://github.com/sponsors/itskavin"
# Hardcoded application version (used by About dialog).
APP_HARDCODED_VERSION = "2.4.0"

def get_simkl_scrobbler():
    """Lazy import for SimklScrobbler to avoid circular imports"""
    from simkl_mps.main import SimklScrobbler
    return SimklScrobbler

class TrayAppBase(abc.ABC): # Inherit from ABC for abstract methods
    """Base system tray application for simkl-mps"""
    
    @abc.abstractmethod
    def update_icon(self):
        """Update the tray icon - must be implemented by platform-specific classes"""
        pass
        
    @abc.abstractmethod
    def show_notification(self, title, message):
        """Show a desktop notification - must be implemented by platform-specific classes"""
        pass
        
    @abc.abstractmethod
    def show_about(self, _=None):
        """Show about dialog - must be implemented by platform-specific classes"""
        pass
        
    @abc.abstractmethod
    def show_help(self, _=None):
        """Show help - must be implemented by platform-specific classes"""
        pass
        
    @abc.abstractmethod
    def exit_app(self, _=None):
        """Exit the application - must be implemented by platform-specific classes"""
        pass
        
    @abc.abstractmethod
    def run(self):
        """Run the tray application - must be implemented by platform-specific classes"""
        pass
        
    @abc.abstractmethod
    def _ask_custom_threshold_dialog(self, current_threshold: int) -> int | None:
        """
        Platform-specific method to display a dialog asking the user for a custom threshold.
        
        Args:
            current_threshold: The currently configured threshold value.
            
        Returns:
            The new threshold value (int) entered by the user, or None if cancelled.
         """       
        pass

    @abc.abstractmethod
    def _ask_directory_filter_dialog(self, title: str, current_value: str, help_text: str) -> str | None:
        """
        Platform-specific dialog for editing directory filters.

        Returns:
            Updated string (comma/newline separated) or None if cancelled.
        """
        pass
            
    def _show_confirmation_dialog(self, title, message):
        """
        Show a simple Yes/No confirmation dialog using tkinter messagebox.
        Returns True if user clicks Yes, False if user clicks No or closes dialog.
        """
        try:
            import tkinter as tk
            from tkinter import messagebox
            import threading
            
            result = [False]  # Use list to allow modification in thread
            
            def show_dialog():
                try:
                    # Create a temporary root window
                    root = tk.Tk()
                    root.withdraw()  # Hide the root window
                    root.attributes('-topmost', True)
                    root.lift()
                    root.focus_force()
                    
                    # Show the Yes/No dialog
                    answer = messagebox.askyesno(title, message, parent=root)
                    result[0] = answer
                    
                    # Clean up
                    root.destroy()
                except Exception as e:
                    logger.error(f"Error in dialog thread: {e}")
                    result[0] = False
            
            # Run dialog in main thread
            thread = threading.Thread(target=show_dialog)
            thread.start()
            thread.join()  # Wait for completion
            
            return result[0]
        except Exception as e:
            logger.error(f"Error showing confirmation dialog: {e}")
            return False
            

    def _show_info_dialog(self, title, message):
        """Display an informational dialog and wait for the user to dismiss it."""
        try:

            def show_dialog():
                try:
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes('-topmost', True)
                    root.lift()
                    root.focus_force()
                    messagebox.showinfo(title, message, parent=root)
                    root.destroy()
                except Exception as dialog_err:
                    logger.error(f"Error showing info dialog: {dialog_err}")

            thread = threading.Thread(target=show_dialog)
            thread.start()
            thread.join()
        except Exception as e:
            logger.error(f"Error launching info dialog: {e}")


    def __init__(self):
        self.scrobbler: Optional["SimklScrobbler"] = None
        self.monitoring_active = False
        self.status = "stopped"
        self.status_details = ""
        self.last_scrobbled = None
        self.config_path = APP_DATA_DIR / ".simkl_mps.env"
        self.log_path = APP_DATA_DIR / "simkl_mps.log"
        
        # Track whether this is a first run (for notifications)
        self.is_first_run = False
        self.check_first_run()

        # Track authentication state for menu labeling and actions
        self._auth_in_progress = False
        self.is_authenticated = False
        self._last_known_access_token = None
        self._last_known_client_id = None
        self._refresh_auth_state(initial=True)

        # Improved asset path resolution for frozen applications
        if getattr(sys, 'frozen', False):
            # When frozen, look for assets in multiple locations
            meipass_dir = getattr(sys, "_MEIPASS", None)
            base_dir = Path(meipass_dir) if meipass_dir else Path(sys.executable).parent
            possible_asset_paths = [
                base_dir / "simkl_mps" / "assets",  # Standard location in the frozen app
                base_dir / "assets",                # Alternative location
                Path(sys.executable).parent / "simkl_mps" / "assets",  # Beside the executable
                Path(sys.executable).parent / "assets"   # Beside the executable (alternative)
            ]
            
            # Find the first valid assets directory
            for path in possible_asset_paths:
                if path.exists() and path.is_dir():
                    self.assets_dir = path
                    logger.info(f"Using assets directory from frozen app: {self.assets_dir}")
                    break
            else:
                # If no directory was found, use a fallback
                self.assets_dir = base_dir
                logger.warning(f"No assets directory found in frozen app. Using fallback: {self.assets_dir}")
        else:
            # When running normally, assets are relative to this script's dir
            module_dir = Path(__file__).parent
            self.assets_dir = module_dir / "assets"
            logger.info(f"Using assets directory from source: {self.assets_dir}")

    def _check_auth_state(self):
        """Return the current authentication state and cached credentials."""
        try:
            creds = get_credentials()
            token = creds.get("access_token")
            client_id = creds.get("client_id")
            return bool(token), token, client_id
        except Exception as e:
            logger.error(f"Failed to read authentication state: {e}", exc_info=True)
            return False, None, None

    def _refresh_auth_state(self, initial: bool = False):
        """Refresh cached authentication state; return True if anything changed."""
        authenticated, token, client_id = self._check_auth_state()
        changed = (
            authenticated != self.is_authenticated or
            token != self._last_known_access_token or
            client_id != self._last_known_client_id
        )
        self.is_authenticated = authenticated
        self._last_known_access_token = token
        self._last_known_client_id = client_id
        if changed and not initial:
            logger.info("Authentication state changed: %s", "authenticated" if authenticated else "not authenticated")
            # Refresh the tray menu/icon when auth state changes
            try:
                self.update_icon()
            except Exception:
                logger.debug("Failed to update icon after auth state change", exc_info=True)
        return changed

    def _get_media_scrobbler(self) -> Any:
        """Return the active MediaScrobbler instance if available."""
        scrobbler_instance = self.scrobbler
        if not scrobbler_instance:
            return None
        monitor = getattr(scrobbler_instance, "monitor", None)
        return getattr(monitor, "scrobbler", None)

    def _get_watch_history_manager(self) -> Any:
        """Return the active WatchHistoryManager instance if available."""
        scrobbler_instance = self.scrobbler
        if scrobbler_instance and hasattr(scrobbler_instance, "watch_history_manager"):
            return scrobbler_instance.watch_history_manager
        return None

    def _ensure_threshold_value(self, value: Any) -> int:
        """Convert stored threshold value to an int with a safe fallback."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULT_THRESHOLD

    def _format_dir_list_for_dialog(self, values: Any) -> str:
        """Format directory lists for dialog input."""
        if not values:
            return ""
        if isinstance(values, str):
            return values
        try:
            return "\n".join([str(value) for value in values if value])
        except Exception:
            return ""

    def _parse_dir_list_input(self, input_text: str | None) -> list[str]:
        """Parse dialog input into a normalized list of paths or patterns."""
        if not input_text:
            return []
        parts: list[str] = []
        for line in input_text.splitlines():
            for token in re.split(r"[;,]", line):
                cleaned = token.strip()
                if cleaned:
                    parts.append(cleaned)
        return parts

    def _apply_dir_filter_change(self, key: str, entries: list[str]) -> None:
        """
        Persist filter settings and signal the running scrobbler to refresh its configuration.
        
        This respects encapsulation by using the scrobbler's public signal_dir_filters_update()
        method rather than directly modifying its private attributes.
        """
        try:
            set_setting(key, entries)
            media_scrobbler = self._get_media_scrobbler()
            if media_scrobbler is not None:
                # Signal the scrobbler to refresh configuration via public method
                if hasattr(media_scrobbler, "signal_dir_filters_update"):
                    media_scrobbler.signal_dir_filters_update()
            label = "Allow" if key == "allow_dirs" else "Deny"
            self.show_notification("Settings Updated", f"{label} directories updated.")
        except Exception as exc:
            logger.error(f"Failed to update {key}: {exc}", exc_info=True)
            self.show_notification("Error", f"Failed to update directory filters: {exc}")

    def set_allow_dirs(self, _=None):
        current_value = self._format_dir_list_for_dialog(get_setting("allow_dirs", []))
        help_text = "Enter paths or glob patterns, separated by commas or semicolons."
        updated_text = self._ask_directory_filter_dialog("Set Allow Directories", current_value, help_text)
        if updated_text is not None:
            entries = self._parse_dir_list_input(updated_text)
            self._apply_dir_filter_change("allow_dirs", entries)
        self.update_icon()
        return 0

    def set_deny_dirs(self, _=None):
        current_value = self._format_dir_list_for_dialog(get_setting("deny_dirs", []))
        help_text = "Enter paths or glob patterns, separated by commas or semicolons."
        updated_text = self._ask_directory_filter_dialog("Set Deny Directories", current_value, help_text)
        if updated_text is not None:
            entries = self._parse_dir_list_input(updated_text)
            self._apply_dir_filter_change("deny_dirs", entries)
        self.update_icon()
        return 0

    def clear_allow_dirs(self, _=None):
        self._apply_dir_filter_change("allow_dirs", [])
        self.update_icon()
        return 0

    def clear_deny_dirs(self, _=None):
        self._apply_dir_filter_change("deny_dirs", [])
        self.update_icon()
        return 0

    def _get_app_version(self) -> str:
        """Return the hardcoded application version.

        This deliberately returns a fixed string to avoid runtime lookups.
        Keep `APP_HARDCODED_VERSION` in this file in sync with the project's
        versioning (the `version_manager.py` script now updates this constant).
        """
        return APP_HARDCODED_VERSION

    def _build_about_text(self) -> str:
        """Build standard About dialog text."""
        return (
            "Media Player Scrobbler for SIMKL\n"
            f"Version: {self._get_app_version()}\n"
            "Author: kavin\n"
            "License: GNU GPL v3\n\n"
            "Automatically track and scrobble your media to SIMKL."
        )

    def check_updates_thread(self, _=None):
        """Optional hook for subclasses that implement update checks."""
        logger.debug("Update check not implemented for this platform.")

    def _get_auth_menu_label(self):
        if self._auth_in_progress:
            return "Authenticating..."
        return "Authenticate" if not self.is_authenticated else "Re-authenticate"

    def trigger_auth_flow(self, _=None):
        """Start the Simkl authentication flow from the tray menu."""
        if self._auth_in_progress:
            self.show_notification("SIMKL Authentication", "Authentication is already in progress.")
            return 0

        authenticated, _, client_id = self._check_auth_state()
        if not client_id or "PLACEHOLDER" in str(client_id):
            logger.error("Client ID missing; cannot start authentication flow.")
            self.show_notification("Authentication Error", "Client ID is not configured. Reinstall or check your build configuration.")
            return 0

        self._auth_in_progress = True
        if not authenticated:
            logger.info("Starting initial authentication flow from tray.")
        else:
            logger.info("Starting re-authentication flow from tray.")

        # Refresh menu immediately to show in-progress state
        try:
            self.update_icon()
        except Exception:
            logger.debug("Unable to refresh icon before authentication starts", exc_info=True)

        threading.Thread(target=self._run_auth_flow, args=(client_id,), daemon=True).start()
        return 0

    def _run_auth_flow(self, client_id: str):
        """Execute the Simkl PIN authentication flow in a background thread."""
        try:
            self._show_info_dialog(
                "Simkl Authentication",
                "A browser window will open so you can authorize Media Player Scrobbler for SIMKL."
                " Sign in to Simkl and approve the request, then return here once it is complete."
            )
            self.show_notification(
                "Simkl Authentication",
                "Opening your browser for Simkl authorization. Complete the steps and return to the tray."
            )

            new_token = pin_auth_flow(client_id)

            if new_token:
                logger.info("Authentication flow completed successfully from tray.")
                self.show_notification("Simkl Authentication", "Authentication completed successfully.")

                try:
                    # Ensure the latest credentials are cached
                    self._refresh_auth_state()
                    refreshed_creds = get_credentials()
                    if self.scrobbler:
                        self.scrobbler.access_token = new_token
                        self.scrobbler.client_id = client_id
                        if hasattr(self.scrobbler, 'monitor') and self.scrobbler.monitor:
                            self.scrobbler.monitor.set_credentials(
                                client_id,
                                new_token,
                                account_type=refreshed_creds.get("account_type"),
                                settings_all=refreshed_creds.get("settings_all")
                            )
                except Exception as update_err:
                    logger.error(f"Failed to propagate new credentials to running components: {update_err}", exc_info=True)
            else:
                logger.warning("Authentication flow did not return a token (cancelled or timed out).")
                self.show_notification("Simkl Authentication", "Authentication was not completed. You can try again anytime.")

        except Exception as e:
            logger.error(f"Authentication flow failed: {e}", exc_info=True)
            self.show_notification("Authentication Error", f"Authentication failed: {e}")
        finally:
            self._refresh_auth_state()
            self._auth_in_progress = False
            try:
                self.update_icon()
            except Exception:
                logger.debug("Unable to refresh icon after authentication", exc_info=True)
        
    def get_status_text(self):
        """Generate status text for the menu item"""
        status_map = {
            "running": "Running",
            "paused": "Paused",
            "stopped": "Stopped",
            "error": "Error"
        }
        status_text = status_map.get(self.status, "Unknown")
        if self.status_details:
            status_text += f" - {self.status_details}"
        if self.last_scrobbled:
            status_text += f"\nLast: {self.last_scrobbled}"
        return status_text

    def update_status(self, new_status, details="", last_scrobbled=None):
        """Update the status and refresh the icon"""
        if new_status != self.status or details != self.status_details or last_scrobbled != self.last_scrobbled:
            self.status = new_status
            self.status_details = details
            if last_scrobbled:
                self.last_scrobbled = last_scrobbled
            self.update_icon()
            logger.debug(f"Status updated to {new_status} - {details}")
    
    def _create_fallback_image(self, size=128):
        """Create a fallback image when the icon files can't be loaded"""
        width = size
        height = size
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        
        dc = ImageDraw.Draw(image)
        
        if self.status == "running":
            color = (34, 177, 76)  # Green
            ring_color = (22, 117, 50)
        elif self.status == "paused":
            color = (255, 127, 39)  # Orange
            ring_color = (204, 102, 31)
        elif self.status == "error":
            color = (237, 28, 36)  # Red
            ring_color = (189, 22, 29)
        else:  
            color = (112, 146, 190)  # Blue
            ring_color = (71, 93, 121)
            
        ring_thickness = max(1, size // 20)
        padding = ring_thickness * 2
        dc.ellipse([(padding, padding), (width - padding, height - padding)],
                   outline=ring_color, width=ring_thickness)
        
        try:
            font_size = int(height * 0.6)
            font = ImageFont.truetype("arialbd.ttf", font_size)
            bbox = dc.textbbox((0, 0), "S", font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = (width - text_width) / 2 - bbox[0]
            text_y = (height - text_height) / 2 - bbox[1]
            dc.text((text_x, text_y), "S", font=font, fill=color)
        except (OSError, IOError):
            logger.warning("Arial Bold font not found. Falling back to drawing a circle.")
            inner_padding = size // 4
            dc.ellipse([(inner_padding, inner_padding),
                        (width - inner_padding, height - inner_padding)], fill=color)
            
        return image

    def _get_icon_path(self, status: str):
        """Get the path to an icon file based on status, prioritizing status-specific icons."""
        try:
            # Platform-specific considerations
            if sys.platform == "win32":
                preferred_formats = ["ico", "png"]
                # Order for search preference if multiple sized files exist.
                preferred_sizes = [256, 128, 64, 48, 32, 24, 16]
            elif sys.platform == "darwin":
                preferred_formats = ["png", "ico"] # macOS prefers png
                preferred_sizes = [512, 256, 128, 64, 32] # macOS can handle large icons
            else: # Linux
                preferred_formats = ["png", "ico"]
                preferred_sizes = [256, 128, 64, 48, 32, 24, 16]

            # 1. Try status-specific sized icons (e.g., simkl-mps-running-32.png)
            for size in preferred_sizes:
                for fmt in preferred_formats:
                    path = self.assets_dir / f"simkl-mps-{status}-{size}.{fmt}"
                    if path.exists():
                        logger.debug(f"Using status-specific sized icon: {path}")
                        return str(path)

            # 2. Try status-specific non-sized icons (e.g., simkl-mps-running.png)
            for fmt in preferred_formats:
                path = self.assets_dir / f"simkl-mps-{status}.{fmt}"
                if path.exists():
                    logger.debug(f"Using status-specific non-sized icon: {path}")
                    return str(path)

            # 3. Try generic sized icons (e.g., simkl-mps-32.png) - as fallback
            for size in preferred_sizes:
                for fmt in preferred_formats:
                    path = self.assets_dir / f"simkl-mps-{size}.{fmt}"
                    if path.exists():
                        logger.debug(f"Using generic sized icon (fallback for status '{status}'): {path}")
                        return str(path)
            
            # 4. Try generic non-sized icon (e.g., simkl-mps.png) - as final fallback
            for fmt in preferred_formats:
                path = self.assets_dir / f"simkl-mps.{fmt}"
                if path.exists():
                    logger.debug(f"Using generic non-sized icon (fallback for status '{status}'): {path}")
                    return str(path)
            
            # The self.assets_dir initialization (lines 93-118) is comprehensive.
            # The original code had a section for sys.executable.parent, which is covered if
            # self.assets_dir resolution points there or includes it in its search.

            logger.warning(f"No suitable icon found for status '{status}' in: {self.assets_dir}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding icon path for status '{status}': {e}")
            return None

    def open_config_dir(self, _=None):
        """Open the configuration directory"""
        try:
            if APP_DATA_DIR.exists():
                if sys.platform == 'win32':
                    os.startfile(APP_DATA_DIR)
                elif sys.platform == 'darwin':
                    os.system(f'open "{APP_DATA_DIR}"')
                else:
                    os.system(f'xdg-open "{APP_DATA_DIR}"')
            else:
                logger.warning(f"Config directory not found at {APP_DATA_DIR}")
        except Exception as e:
            logger.error(f"Error opening config directory: {e}")
        return 0

    def open_simkl(self, _=None):
        """Open the SIMKL website"""
        webbrowser.open("https://simkl.com")
        return 0

    def open_donation_page(self, _=None):
        """Open the donation/support page."""
        donation_url = DEFAULT_DONATION_URL
        webbrowser.open(donation_url)
        return 0

    def open_simkl_history(self, _=None):
        """Open the SIMKL history page"""
        logger.info("Attempting to open SIMKL history page...")
        try:
            creds = get_credentials()
            client_id = creds.get("client_id")
            access_token = creds.get("access_token")
            
            # First, check if we have the user ID stored in credentials
            user_id = creds.get("user_id")
            
            if user_id:
                logger.info(f"Using stored user ID from credentials: {user_id}")
                history_url = f"https://simkl.com/{user_id}/stats/seen/"
                logger.info(f"Opening SIMKL history URL: {history_url}")
                webbrowser.open(history_url)
                return
                
            # If no stored user ID, we need to fetch it from the API
            if not client_id or not access_token:
                logger.error("Cannot open history: Missing credentials.")
                self.show_notification("Error", "Missing credentials to fetch user history.")
                return

            logger.info("No stored user ID found, attempting to retrieve from Simkl API...")
            
            # Use the cached /users/settings lookup to recover the authenticated Simkl user ID
            settings = get_user_settings(client_id, access_token)
            
            if settings:
                # Our improved function now consistently puts user ID in settings['user_id']
                user_id = settings.get('user_id')
                
                if user_id:
                    history_url = f"https://simkl.com/{user_id}/stats/seen/"
                    logger.info(f"Successfully retrieved user ID: {user_id}")
                    logger.info(f"Opening SIMKL history URL: {history_url}")
                    webbrowser.open(history_url)
                    
                    # Save user ID to env file for future use
                    from simkl_mps.credentials import get_env_file_path
                    from simkl_mps.simkl_api import _save_access_token
                    env_path = get_env_file_path()
                    _save_access_token(env_path, access_token, user_id)
                    logger.info(f"Saved user ID {user_id} to credentials file for future use")
                    return
            
            logger.error("Could not retrieve user ID from Simkl settings.")
            self.show_notification("Error", "Could not retrieve user ID to open history.")
        except Exception as e:
            logger.error(f"Error opening SIMKL history: {e}", exc_info=True)
            self.show_notification("Error", f"Failed to open SIMKL history: {e}")

    def open_watch_history(self, _=None):
        """Open the local watch history page in the browser"""
        logger.info("Attempting to open local watch history page...")
        try:
            # Check if the scrobbler and its history manager are initialized
            if self.scrobbler and hasattr(self.scrobbler, 'watch_history_manager') and self.scrobbler.watch_history_manager:
                watch_history = self.scrobbler.watch_history_manager
                
                # Open the history page in browser using the existing instance
                if watch_history.open_history():
                    self.show_notification(
                        "simkl-mps",
                        "Watch history page opened in your browser"
                    )
                    logger.info("Successfully opened watch history page")
                else:
                    # This specific error case might indicate a problem within open_history() itself
                    logger.error("watch_history.open_history() returned False.")
                    self.show_notification(
                        "simkl-mps Error",
                        "Failed to open watch history page (internal error)."
                    )
                    return 1 # Indicate failure
            else:
                # This case means the manager wasn't ready
                logger.error("Cannot open watch history: Scrobbler or WatchHistoryManager not initialized.")
                self.show_notification(
                    "simkl-mps Error",
                    "Watch History Manager is not ready. Please ensure monitoring is started."
                )
                return 1 # Indicate failure

        except Exception as e:
            # Catch any other unexpected errors
            logger.error(f"Error opening watch history: {e}", exc_info=True)
            self.show_notification(
                "simkl-mps Error",
                f"Could not open watch history: {e}"
            )
            return 1 # Indicate failure
            
        return 0 # Indicate success

    def _get_updater_path(self, filename):
        """Get the path to the updater script (ps1 or sh)"""
        import sys
        from pathlib import Path
        
        # Check if we're running from an executable or source
        if getattr(sys, 'frozen', False):
            # Running from executable
            app_path = Path(sys.executable).parent
            return app_path / filename
        else:
            # Running from source
            import simkl_mps
            module_path = Path(simkl_mps.__file__).parent
            return module_path / "utils" / filename

    def open_logs(self, _=None):
        """Open the log file"""
        log_path = APP_DATA_DIR/"simkl_mps.log"
        try:
            if sys.platform == "win32":
                os.startfile(str(log_path))
            elif sys.platform == "darwin":
                os.system(f"open '{str(log_path)}'")
            else:
                os.system(f"xdg-open '{str(log_path)}'")
            self.show_notification(
                "simkl-mps",
                "Log folder opened."
            )
        except Exception as e:
            logger.error(f"Error opening log file: {e}")
            self.show_notification(
                "simkl-mps Error",
                f"Could not open log file: {e}"
            )

    def start_monitoring(self, _=None):
        """Start the scrobbler monitoring"""
        # Check if this is a manual start (from the menu) vs. autostart
        is_manual_start = _ is not None
        
        if self.scrobbler and hasattr(self.scrobbler, 'monitor'):
            if not getattr(self.scrobbler.monitor, 'running', False):
                self.monitoring_active = False
                
        if not self.monitoring_active:
            if not self.scrobbler:
                self.scrobbler = get_simkl_scrobbler()()
                if not self.scrobbler.initialize():
                    self.update_status("error", "Failed to initialize")
                    self.show_notification(
                        "simkl-mps Error",
                        "Failed to initialize. Check your credentials."
                    )
                    logger.error("Failed to initialize scrobbler from tray app")
                    self.monitoring_active = False
                    return False
                    
            if hasattr(self.scrobbler, 'monitor') and hasattr(self.scrobbler.monitor, 'scrobbler'):
                self.scrobbler.monitor.scrobbler.set_notification_callback(self.show_notification)
                # Register menu refresh callback so UI updates when account type changes
                if hasattr(self.scrobbler.monitor.scrobbler, 'set_menu_refresh_callback'):
                    try:
                        self.scrobbler.monitor.scrobbler.set_menu_refresh_callback(self.update_icon)
                    except Exception as e:
                        logger.debug(f"Failed to set menu refresh callback: {e}")
                
            try:
                started = self.scrobbler.start()
                if started:
                    self.monitoring_active = True
                    self.update_status("running")
                    
                    # Only show notification if:
                    # 1. This is the first run of the app after installation
                    # 2. User manually started the app from the menu
                    # 3. Notifications are not disabled
                    if (self.is_first_run or is_manual_start) and not get_setting('disable_notifications', False):
                        self.show_notification(
                            "simkl-mps",
                            "Media monitoring started"
                        )
                    
                    logger.info("Monitoring started from tray")
                    return True
                else:
                    self.monitoring_active = False
                    self.update_status("error", "Failed to start")
                    self.show_notification(
                        "simkl-mps Error",
                        "Failed to start monitoring"
                    )
                    logger.error("Failed to start monitoring from tray app")
                    return False
            except Exception as e:
                self.monitoring_active = False
                self.update_status("error", str(e))
                logger.exception("Exception during start_monitoring in tray app")
                self.show_notification(
                    "simkl-mps Error",
                    f"Error starting monitoring: {e}"
                )
                return False
        return True

    def stop_monitoring(self, _=None):
        """Stop the scrobbler monitoring"""
        if self.monitoring_active:
            logger.info("Stop monitoring requested from tray.")
            # Ensure scrobbler exists before trying to stop
            if self.scrobbler:
                self.scrobbler.stop()
            else:
                logger.warning("Stop monitoring called, but scrobbler instance is None.")
            self.monitoring_active = False
            self.update_status("stopped")
            self.show_notification(
                "simkl-mps",
                "Media monitoring stopped"
            )
            logger.info("Monitoring stopped from tray")
            return True
        return False

    def process_backlog(self, _=None):
        """Process the backlog from the tray menu"""
        media_scrobbler = self._get_media_scrobbler()
        if not media_scrobbler or not hasattr(media_scrobbler, "process_backlog"):
            logger.warning("Cannot process backlog: media scrobbler is unavailable.")
            self.show_notification(
                "simkl-mps Error",
                "Backlog processing is unavailable because monitoring is not running."
            )
            return 0

        def _process():
            try:
                result = media_scrobbler.process_backlog()
                
                # Handle both the old integer return type and new dictionary return type
                if isinstance(result, dict):
                    count_value = result.get('processed', 0)
                    attempted = result.get('attempted', 0)
                    failures = result.get('failed', False)
                    
                    if count_value > 0:
                        self.show_notification(
                            "simkl-mps",
                            f"Processed {count_value} of {attempted} backlog items"
                        )
                    elif attempted > 0 and failures:
                        self.show_notification(
                            "simkl-mps",
                            f"No backlog items processed successfully. {attempted} items will be retried later."
                        )
                    else:
                        self.show_notification(
                            "simkl-mps",
                            "No backlog items to process"
                        )
                else:
                    # Legacy integer return type
                    count = result
                    if count > 0:
                        self.show_notification(
                            "simkl-mps",
                            f"Processed {count} backlog items"
                        )
                    else:
                        self.show_notification(
                            "simkl-mps",
                            "No backlog items to process"
                        )
            except Exception as e:
                logger.error(f"Error processing backlog: {e}")
                self.update_status("error")
                self.show_notification(
                    "simkl-mps Error",
                    "Failed to process backlog"
                )
            return 0
        threading.Thread(target=_process, daemon=True).start()
        return 0

    def clear_logs(self, _=None):
        """Clear application and playback log files."""
        logger.info("Clear logs requested from tray menu...")

        if not self._show_confirmation_dialog(
            "Clear Logs",
            "This will erase the application log and playback logs.\n\n"
            "Use this when you need a clean slate before reproducing an issue.\n\n"
            "Continue?"
        ):
            logger.info("Clear logs cancelled by user")
            return 0

        log_targets: list[tuple[str, Path, str]] = [
            ("application log", self.log_path, "truncate"),
            ("app data playback log", APP_DATA_DIR / "playback_log.jsonl", "truncate"),
            ("workspace playback log", Path("playback_log.jsonl"), "delete"),
        ]

        cleared: list[str] = []
        failures: list[str] = []

        for label, target_path, mode in log_targets:
            try:
                if not target_path.exists():
                    logger.debug(f"Log target '{label}' not found at {target_path}. Skipping.")
                    continue

                if mode == "truncate":
                    with open(target_path, "w", encoding="utf-8"):
                        pass
                else:
                    target_path.unlink()

                cleared.append(label)
                logger.info(f"Cleared {label} at {target_path}")
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"Failed to clear {label} at {target_path}: {exc}", exc_info=True)
                failures.append(label)

        if cleared and not failures:
            self.show_notification("simkl-mps", f"Cleared logs: {', '.join(cleared)}")
        elif cleared:
            self.show_notification(
                "simkl-mps",
                f"Cleared logs: {', '.join(cleared)}. Failed: {', '.join(failures)}"
            )
        else:
            self.show_notification("simkl-mps Error", "No log files could be cleared.")

        return 0

    def clear_watch_history(self, _=None):
        """Clear the local watch history cache and viewer data."""
        logger.info("Clear watch history requested from tray menu...")

        if not self._show_confirmation_dialog(
            "Clear Watch History",
            "This removes the locally stored watch_history.json and viewer data.\n\n"
            "Simkl's online history is unaffected.\n\n"
            "Continue?"
        ):
            logger.info("Clear watch history cancelled by user")
            return 0

        try:
            history_manager = None
            if self.scrobbler and getattr(self.scrobbler, 'watch_history_manager', None):
                history_manager = self.scrobbler.watch_history_manager

            if history_manager is None:
                from simkl_mps.watch_history_manager import WatchHistoryManager
                history_manager = WatchHistoryManager(APP_DATA_DIR)
                if self.scrobbler and hasattr(self.scrobbler, 'watch_history_manager'):
                    self.scrobbler.watch_history_manager = history_manager

            if history_manager is None:
                raise RuntimeError("Watch history manager unavailable")

            history_manager.clear()
            if hasattr(history_manager, "history"):
                history_manager.history = []

            history_file = APP_DATA_DIR / "watch_history.json"
            if history_file.exists():
                history_file.unlink()

            viewer_dir = APP_DATA_DIR / "watch-history-viewer"
            data_js = viewer_dir / "data.js"
            if data_js.exists():
                data_js.unlink()

            self.show_notification("simkl-mps", "Local watch history cleared.")
            logger.info("Local watch history cleared via tray menu")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to clear watch history: {exc}", exc_info=True)
            self.show_notification("simkl-mps Error", f"Failed to clear watch history: {exc}")

        return 0

    def clear_backlog(self, _=None):
        """Clear the backlog and restart application state to prevent repeated sync notifications"""
        logger.info("Clear backlog requested from tray menu...")
        
        # Show confirmation dialog
        if not self._show_confirmation_dialog(
            "Clear Backlog",
            "Are you sure you want to clear the backlog?\n\n"
            "This will:\n"
            "• Clear all pending backlog items\n"
            "• Reset tracking state\n"
            "• Stop repeated sync notifications\n\n"
            "This action cannot be undone."
        ):
            logger.info("Clear backlog cancelled by user")
            return 0
        
        logger.info("Clearing backlog from tray menu...")
        try:
            # Clear the backlog
            from simkl_mps.backlog_cleaner import BacklogCleaner
            backlog_cleaner = BacklogCleaner(APP_DATA_DIR)
            backlog_cleaner.clear()
            
            # Reset scrobbler state if running
            if self.scrobbler:
                if hasattr(self.scrobbler, 'monitor') and hasattr(self.scrobbler.monitor, 'scrobbler'):
                    scrobbler: Any = self.scrobbler.monitor.scrobbler
                    
                    # Use the new reset method for comprehensive state clearing
                    if hasattr(scrobbler, 'reset_tracking_state'):
                        scrobbler.reset_tracking_state()
                        logger.info("Used comprehensive tracking state reset")
                    else:
                        # Fallback to manual reset if method not available
                        if hasattr(scrobbler, 'clear_backlog_processing_state'):
                            scrobbler.clear_backlog_processing_state()
                        
                        # Reset tracking state to prevent stuck notifications
                        for attr in ('currently_tracking', 'movie_name', 'show_name', 'media_title', 
                                   'media_type', 'season', 'episode', 'simkl_id', 'completed',
                                   'current_filepath', 'state'):
                            if hasattr(scrobbler, attr):
                                setattr(scrobbler, attr, None)
                        
                        # Reset timing and progress tracking
                        scrobbler.start_time = None
                        scrobbler.watch_time = 0
                        scrobbler.current_position_seconds = 0
                        scrobbler.total_duration_seconds = 0
                        scrobbler.last_update_time = None
                        
                        # Clear any offline sync thread notification throttles
                        if hasattr(scrobbler, '_last_offline_sync_notification'):
                            scrobbler._last_offline_sync_notification = 0
                        
                        logger.info("Used manual tracking state reset")
            
            self.show_notification("simkl-mps", "Backlog cleared and tracking state reset.")
            self.update_icon()
            logger.info("Backlog cleared successfully")
            
        except Exception as e:
            logger.error(f"Error clearing backlog: {e}")
            self.show_notification("simkl-mps Error", f"Failed to clear backlog: {e}")
        return 0

    # --- Watch Threshold Logic ---

    def _apply_threshold_change(self, new_threshold: int | None):
        """Applies the threshold change: saves, updates scrobbler, notifies, updates UI."""
        logger.debug(f"TrayBase: _apply_threshold_change called with new_threshold='{new_threshold}' (type: {type(new_threshold)})")
        current_threshold = self._ensure_threshold_value(
            get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        )
        logger.debug(f"TrayBase: Current threshold from settings: {current_threshold}")

        if new_threshold is not None and new_threshold != current_threshold:
            logger.info(f"TrayBase: Applying new threshold: {new_threshold}%")
            try:
                set_setting('watch_completion_threshold', new_threshold)
                logger.info(f"Watch completion threshold set to {new_threshold}%")
                self.show_notification("Settings Updated", f"Watch threshold set to {new_threshold}%")

                # Attempt to update the running scrobbler instance
                media_scrobbler = self._get_media_scrobbler()
                if media_scrobbler and hasattr(media_scrobbler, 'completion_threshold'):
                    media_scrobbler.completion_threshold = new_threshold # Store as percentage
                    logger.debug(f"Updated running scrobbler instance threshold to {new_threshold}%")
                else:
                    logger.warning("Could not update running scrobbler instance threshold (not found or not running).")

                self.update_icon() # Refresh menu to show new checkmark/state

            except Exception as e:
                logger.error(f"Error applying watch threshold change: {e}", exc_info=True)
                self.show_notification("Error", f"Failed to set watch threshold: {e}")
                self.update_icon() # Still update icon on error
        elif new_threshold is None:
             logger.warning("TrayBase: _apply_threshold_change received new_threshold=None. Change cancelled or dialog failed. No notification will be shown for this specific path.")
             self.update_icon() # Refresh menu state even on cancel/failure
        else: # Threshold is the same as current
             logger.info(f"TrayBase: Watch threshold ({new_threshold}%) not changed from current ({current_threshold}%).")
             self.update_icon() # Refresh menu state even if not changed

    def _set_preset_threshold(self, threshold_value: int):
        """Set watch threshold from a preset value and update."""
        current_threshold = get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        if threshold_value != current_threshold:
            logger.info(f"Preset threshold {threshold_value}% selected.")
            self._apply_threshold_change(threshold_value)
        else:
            logger.debug(f"Preset threshold {threshold_value}% is already selected.")
        return 0 # Return value expected by some tray libraries for menu actions

    def set_custom_watch_threshold(self, _=None):
        """Handles prompting the user for a custom threshold via platform-specific dialog."""
        logger.debug("TrayBase: set_custom_watch_threshold called.")
        current_threshold = self._ensure_threshold_value(
            get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        )
        logger.debug(f"TrayBase: Current threshold for custom dialog: {current_threshold}%")
        result_queue: "queue.Queue[int | None]" = queue.Queue()

        def _ask_in_thread():
            """Runs the platform-specific dialog in a separate thread."""
            logger.debug("TrayBase: _ask_in_thread started.")
            value_from_dialog = None  # Default to None
            try:
                # Call the abstract method implemented by the subclass
                threshold_dialog_result = self._ask_custom_threshold_dialog(current_threshold)
                value_from_dialog = threshold_dialog_result  # Store the actual result from dialog

                # Log after successfully getting the value, before putting it on queue
                logger.debug(f"TrayBase: _ask_custom_threshold_dialog returned: {threshold_dialog_result} (type: {type(threshold_dialog_result)})")
                # The result_queue.put will now be in the finally block
            except Exception as e:
                # This catches errors from _ask_custom_threshold_dialog or subsequent logging if it were before this block
                logger.error(f"TrayBase: Error in custom threshold dialog thread (_ask_in_thread): {e}", exc_info=True)
                # value_from_dialog remains None (its initial value) or whatever it was if error occurred after assignment
            finally:
                # Ensure that whatever value was obtained (or None if error/cancel) is put on the queue
                result_queue.put(value_from_dialog)
                logger.debug(f"TrayBase: _ask_in_thread finished, put '{value_from_dialog}' on queue.")

        def _process_result():
            """Waits for the result from the queue and processes it."""
            logger.debug("TrayBase: _process_result started, waiting for queue.")
            new_threshold_from_queue = None # Initialize
            try:
                # Block until the result is available from the dialog thread
                new_threshold_from_queue = result_queue.get(timeout=60) # Add timeout
                logger.debug(f"TrayBase: Value from result_queue: {new_threshold_from_queue} (type: {type(new_threshold_from_queue)})")
                # Call _apply_threshold_change with the result from the queue
                self._apply_threshold_change(new_threshold_from_queue)
            except queue.Empty:
                 logger.warning("TrayBase: Timeout waiting for custom threshold dialog result in _process_result.")
                 self.show_notification("Timeout", "Custom threshold dialog timed out.")
                 self._apply_threshold_change(None) # Explicitly pass None on timeout
            except Exception as e:
                 logger.error(f"TrayBase: Error processing threshold result in _process_result: {e}", exc_info=True)
                 self._apply_threshold_change(None) # Explicitly pass None on error
            logger.debug("TrayBase: _process_result finished.")


        # Start the thread to show the dialog
        dialog_thread = threading.Thread(target=_ask_in_thread, daemon=True)
        dialog_thread.start()

        # Start the thread to process the result from the queue
        processing_thread = threading.Thread(target=_process_result, daemon=True)
        processing_thread.start()

        logger.info("Started threads to ask for and process custom watch threshold.")
        # The menu action returns immediately, work happens in background threads.
        return 0 # Return value expected by some tray libraries

    # --- End Watch Threshold Logic --- 
    
    def toggle_notifications_disabled(self, _=None):
        """Toggle notifications on/off from the tray menu."""
        try:
            current_value = get_setting('disable_notifications', False)
            new_value = not current_value
            set_setting('disable_notifications', new_value)
            
            status = "disabled" if new_value else "enabled"
            logger.info(f"Notifications {status} via tray menu")
            self.update_icon()  # Refresh menu to show new checkmark state
            
        except Exception as e:
            logger.error(f"Error toggling notifications: {e}", exc_info=True)
            self.show_notification("Error", f"Failed to toggle notifications: {e}")
        
        return 0

    def toggle_rewatch_enabled(self, _=None):
        """Toggle rewatch scrobbling on/off from the tray menu."""
        try:
            media_scrobbler = self._get_media_scrobbler()
            if media_scrobbler is not None and hasattr(media_scrobbler, "refresh_account_type_if_needed"):
                media_scrobbler.refresh_account_type_if_needed(min_interval_seconds=0)
            account_type = getattr(media_scrobbler, '_account_type', None) if media_scrobbler is not None else None
            current_value = get_setting('allow_rewatch', True)
            new_value = not current_value

            if new_value and account_type not in ('pro', 'vip'):
                set_setting('allow_rewatch', False)
                logger.info("Blocked rewatch enable attempt for non-Pro/VIP account.")
                self.update_icon()
                self.show_notification(
                    "Rewatch Tracking Unavailable",
                    "Rewatch tracking requires Simkl Pro or VIP."
                )
                return 0

            set_setting('allow_rewatch', new_value)

            status = "enabled" if new_value else "disabled"
            logger.info(f"Rewatch scrobbling {status} via tray menu")
            self.update_icon()  # Refresh menu to show new checkmark state
            self.show_notification("Settings Updated", f"Rewatch scrobbling {status}.")
        except Exception as e:
            logger.error(f"Error toggling rewatch scrobbling: {e}", exc_info=True)
            self.show_notification("Error", f"Failed to toggle rewatch scrobbling: {e}")

        return 0
    
    def check_first_run(self):
        """Check if this is the first time the app is being run"""
        # Platform-specific implementation required
        self.is_first_run = False # Default value, should be overridden

    def _build_pystray_menu_items(self):
        """Builds the list of pystray menu items common to multiple platforms."""
        # Get current threshold for radio button state
        self._refresh_auth_state()
        current_threshold = self._ensure_threshold_value(
            get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        )
        is_preset = lambda val: current_threshold == val
        # Determine cached account type (do not force network refresh here)
        media_scrobbler = self._get_media_scrobbler()
        cached_account_type = None
        if media_scrobbler is not None:
            cached_account_type = getattr(media_scrobbler, '_account_type', None)
        can_record_rewatches = cached_account_type in ('pro', 'vip')

        menu_items = [
            pystray.MenuItem("MPS for SIMKL", None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Status: {self.get_status_text()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]

        # Tracking controls
        if self.status == "running":
            menu_items.append(pystray.MenuItem("Pause Tracking", self.stop_monitoring))
        else:
            menu_items.append(pystray.MenuItem("Start Tracking", self.start_monitoring))
        menu_items.append(pystray.Menu.SEPARATOR)

        # --- Scrobbling submenu ---
        threshold_submenu = pystray.Menu(
            pystray.MenuItem('65%', lambda: self._set_preset_threshold(65), checked=lambda item: is_preset(65), radio=True),
            pystray.MenuItem('80% (Default)', lambda: self._set_preset_threshold(80), checked=lambda item: is_preset(80), radio=True),
            pystray.MenuItem('90%', lambda: self._set_preset_threshold(90), checked=lambda item: is_preset(90), radio=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Custom...', self.set_custom_watch_threshold)
        )
        menu_items.append(pystray.MenuItem("Scrobbling", pystray.Menu(
            pystray.MenuItem("Retry Last Scrobble", self.try_scrobble_again),
            pystray.MenuItem("Sync Backlog Now", self.process_backlog),
            pystray.MenuItem("Completion Threshold", threshold_submenu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Record Rewatches",
                self.toggle_rewatch_enabled,
                checked=lambda item, _allowed=can_record_rewatches: get_setting('allow_rewatch', True) if _allowed else False
            ),
            pystray.MenuItem(
                "Turn Notifications Off",
                self.toggle_notifications_disabled,
                checked=lambda item: get_setting('disable_notifications', False)
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Local Watch History", self.open_watch_history),
        )))
        menu_items.append(pystray.Menu.SEPARATOR)

        # --- SIMKL submenu ---
        menu_items.append(pystray.MenuItem("SIMKL", pystray.Menu(
            pystray.MenuItem(
                lambda item: self._get_auth_menu_label(),
                self.trigger_auth_flow,
                enabled=not self._auth_in_progress
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Website", self.open_simkl),
            pystray.MenuItem("Open Watch History", self.open_simkl_history),
        )))

        # --- Maintenance submenu ---
        menu_items.append(pystray.MenuItem("Maintenance", pystray.Menu(
            pystray.MenuItem("Open Logs", self.open_logs),
            pystray.MenuItem("Open Data Folder", self.open_config_dir),
            pystray.MenuItem("Directory Filters", pystray.Menu(
                pystray.MenuItem("Edit Allow List", self.set_allow_dirs),
                pystray.MenuItem("Edit Deny List", self.set_deny_dirs),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Clear Allow List", self.clear_allow_dirs),
                pystray.MenuItem("Clear Deny List", self.clear_deny_dirs),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Clear Backlog", self.clear_backlog),
            pystray.MenuItem("Clear Cache", self.clear_cache),
            pystray.MenuItem("Clear Watch History", self.clear_watch_history),
            pystray.MenuItem("Clear Logs", self.clear_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Reset App Data (Danger)", self.clear_all_data),
        )))

        # --- More submenu ---
        menu_items.append(pystray.MenuItem("More", pystray.Menu(
            pystray.MenuItem("Donate ❤️", self.open_donation_page),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for Updates", self.check_updates_thread),
            pystray.MenuItem("Help", self.show_help),
            pystray.MenuItem("About", self.show_about),
        )))        # --- Exit (always last, separated) ---
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Exit", self.exit_app))

        return menu_items
        
    def clear_cache(self, _=None):
        """Clear disk and in-memory cache, backlog, and update tray menu."""
        logger.info("Clear cache requested from tray menu...")
        
        # Show confirmation dialog
        if not self._show_confirmation_dialog(
            "Clear Cache",
            "Are you sure you want to clear all cached media identification data and backlog?\n\n"
            "This will:\n"
            "• Clear media cache files\n"
            "• Clear backlog data\n"
            "• Reset currently tracked media\n\n"
            "Backup or Process Backlog Before this to Prevent Losses. This action cannot be undone."
        ):
            logger.info("Clear cache cancelled by user")
            return 0
        
        logger.info("Clearing cache from tray menu...")
        try:
            from simkl_mps.media_cache import MediaCache
            MediaCache.clear_media_cache_all_locations(APP_DATA_DIR)
            from simkl_mps.backlog_cleaner import BacklogCleaner
            backlog_cleaner = BacklogCleaner(APP_DATA_DIR)
            backlog_cleaner.clear()
            # Clear in-memory cache and reset tracked media in scrobbler if running
            if self.scrobbler:
                if hasattr(self.scrobbler, 'monitor') and hasattr(self.scrobbler.monitor, 'scrobbler'):
                    scrobbler = self.scrobbler.monitor.scrobbler
                    if hasattr(scrobbler, 'media_cache'):
                        scrobbler.media_cache.cache.clear()
                        scrobbler.media_cache._save_cache()
                    # Clear backlog processing state and notification throttles
                    if hasattr(scrobbler, 'clear_backlog_processing_state'):
                        scrobbler.clear_backlog_processing_state()
                for attr in ('currently_tracking', 'movie_name', 'show_name', 'media_title', 'media_type', 'season', 'episode'):
                    if hasattr(self.scrobbler, attr):
                        setattr(self.scrobbler, attr, None)
            self.show_notification("simkl-mps", "Cache cleared.")
            self.update_icon()
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            self.show_notification("simkl-mps Error", f"Failed to clear cache: {e}")
        return 0    
    
    def clear_all_data(self, _=None):
        """Clear all user data, logs, cache, backlog, playback log, watch history, and .env file."""
        logger.info("Clear all data requested from tray menu...")
        
        # Show confirmation dialog
        if not self._show_confirmation_dialog(
            "Clear All Data",
            "⚠️ WARNING: This will permanently delete ALL application data! ⚠️\n\n"
            "This will remove:\n"
            "• All cached media data\n"
            "• All log files\n"
            "• Backlog and playback history\n"
            "• Watch history\n"
            "• All settings and credentials\n"
            "• Environment configuration\n\n"
            "The application will EXIT after clearing data.\n\n"
            "This action CANNOT be undone!\n\n"
            "Are you absolutely sure you want to proceed?"
        ):
            logger.info("Clear all data cancelled by user")
            return 0
        
        logger.info("Clearing all data and logs from tray menu...")
        cleared_items = []
        failed_items = []
        
        try:
            # Clear media cache
            from simkl_mps.media_cache import MediaCache
            MediaCache.clear_media_cache_all_locations(APP_DATA_DIR)
            cleared_items.append("media cache")
            
            # Clear backlog
            from simkl_mps.backlog_cleaner import BacklogCleaner
            backlog_cleaner = BacklogCleaner(APP_DATA_DIR)
            backlog_cleaner.clear()
            cleared_items.append("backlog")
            
            # Clear log file content (instead of deleting the file to avoid "file in use" errors)
            log_path = APP_DATA_DIR / "simkl_mps.log"
            if log_path.exists():
                try:
                    # Clear the log file content instead of deleting it
                    with open(log_path, 'w', encoding='utf-8') as f:
                        f.write("")  # Clear the file content
                    logger.info("Log file content cleared.")
                    cleared_items.append("log file")
                except (PermissionError, OSError) as log_error:
                    # If we can't clear the log, continue with other cleanup
                    logger.warning(f"Could not clear log file (file may be in use): {log_error}")
                    failed_items.append("log file")
            
            # Clear playback log (in workspace root and app data dir)
            playback_log_paths = [
                Path("playback_log.jsonl"),  # Workspace root
                APP_DATA_DIR / "playback_log.jsonl",  # App data directory
            ]
            for playback_log_path in playback_log_paths:
                if playback_log_path.exists():
                    try:
                        playback_log_path.unlink()
                        logger.info(f"Deleted playback log: {playback_log_path}")
                        cleared_items.append(f"playback log ({playback_log_path.name})")
                    except (PermissionError, OSError) as e:
                        # If file is locked, try to clear its contents instead
                        try:
                            with open(playback_log_path, 'w', encoding='utf-8') as f:
                                f.write("")
                            logger.info(f"Cleared playback log content: {playback_log_path}")
                            cleared_items.append(f"playback log content cleared ({playback_log_path.name})")
                        except Exception as e2:
                            logger.warning(f"Could not clear or delete playback log {playback_log_path}: {e2}")
                            failed_items.append(f"playback log ({playback_log_path.name})")
            
            # Clear backlog.json (in workspace root and app data dir)
            backlog_json_paths = [
                Path("backlog.json"),  # Workspace root  
                APP_DATA_DIR / "backlog.json",  # App data directory
            ]
            for backlog_json_path in backlog_json_paths:
                if backlog_json_path.exists():
                    try:
                        backlog_json_path.unlink()
                        logger.info(f"Deleted backlog file: {backlog_json_path}")
                        cleared_items.append(f"backlog file ({backlog_json_path.name})")
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Could not delete backlog file {backlog_json_path}: {e}")
                        failed_items.append(f"backlog file ({backlog_json_path.name})")
            
            # Clear .env file (in workspace root and app data dir)
            env_paths = [
                Path(".env"),  # Workspace root
                APP_DATA_DIR / ".env",  # App data directory
                APP_DATA_DIR / ".simkl_mps.env",  # App-specific env file
            ]
            for env_path in env_paths:
                if env_path.exists():
                    try:
                        env_path.unlink()
                        logger.info(f"Deleted environment file: {env_path}")
                        cleared_items.append(f"environment file ({env_path.name})")
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Could not delete environment file {env_path}: {e}")
                        failed_items.append(f"environment file ({env_path.name})")
            
            # Clear watch history (via scrobbler if available)
            watch_history_manager = self._get_watch_history_manager()
            if watch_history_manager:
                try:
                    if hasattr(watch_history_manager, 'clear'):
                        watch_history_manager.clear()
                    elif hasattr(watch_history_manager, 'clear_history'):
                        watch_history_manager.clear_history()
                    cleared_items.append("watch history")
                except Exception as e:
                    logger.warning(f"Could not clear watch history: {e}")
                    failed_items.append("watch history")
            
            # Clear settings file
            settings_file = APP_DATA_DIR / "settings.json"
            if settings_file.exists():
                try:
                    settings_file.unlink()
                    logger.info(f"Deleted settings file: {settings_file}")
                    cleared_items.append("settings file")
                except (PermissionError, OSError) as e:
                    logger.warning(f"Could not delete settings file: {e}")
                    failed_items.append("settings file")
            
            # Clear in-memory cache and reset tracked media in scrobbler if running
            if self.scrobbler:
                if hasattr(self.scrobbler, 'monitor') and hasattr(self.scrobbler.monitor, 'scrobbler'):
                    scrobbler = self.scrobbler.monitor.scrobbler
                    if hasattr(scrobbler, 'media_cache'):
                        scrobbler.media_cache.cache.clear()
                        scrobbler.media_cache._save_cache()
                    # Clear backlog processing state and notification throttles
                    if hasattr(scrobbler, 'clear_backlog_processing_state'):
                        scrobbler.clear_backlog_processing_state()
                for attr in ('currently_tracking', 'movie_name', 'show_name', 'media_title', 'media_type', 'season', 'episode'):
                    if hasattr(self.scrobbler, attr):
                        setattr(self.scrobbler, attr, None)
                cleared_items.append("in-memory cache")

            # Reset authentication state after credential files are removed
            self._refresh_auth_state()
            
            # Prepare notification message
            if cleared_items and not failed_items:
                message = f"Successfully Cleared All Data"
                notification_title = "simkl-mps"
            elif cleared_items and failed_items:
                message = f"Cleared Some but Failed: {', '.join(failed_items)}"
                notification_title = "simkl-mps - Partial Success"
            elif failed_items:
                message = f"Failed to clear: {', '.join(failed_items)}"
                notification_title = "simkl-mps Error"
            else:
                message = "No data found to clear"
                notification_title = "simkl-mps"
            
            self.show_notification(notification_title, message)
            self.update_icon()
            self.exit_app()  # Exit the tray app after notifying the user
            
        except Exception as e:
            logger.error(f"Error clearing all data: {e}")
            self.show_notification("simkl-mps Error", f"Failed to clear all data: {e}")
        return 0    
    def try_scrobble_again(self, _=None):
        """Force re-identification of the currently playing media by clearing cached data and re-running identification."""
        logger.info("Forcing re-identification of currently playing media...")
        
        # Show initial notification that the process is starting
        
        try:
            media_scrobbler = self._get_media_scrobbler()
            if not media_scrobbler:
                self.show_notification("simkl-mps", "Monitoring is not active.")
                return 0

            actual_scrobbler: Any = media_scrobbler

            # Check if something is currently being tracked
            if not getattr(actual_scrobbler, "currently_tracking", None):
                self.show_notification("simkl-mps", "No media is currently being tracked.")
                return 0
            
            current_title = actual_scrobbler.currently_tracking
            current_filepath = getattr(actual_scrobbler, "current_filepath", None)
            
            logger.info(f"Re-identifying currently playing media: '{current_title}' (filepath: '{current_filepath}')")
            self.show_notification("simkl-mps", f"Attempting to re-identify '{current_title}'...")

            if current_filepath and hasattr(actual_scrobbler, "clear_file_search_rate_limit"):
                actual_scrobbler.clear_file_search_rate_limit(current_filepath)
                    
            # Determine cache keys to clear
            cache_keys_to_clear = []
            
            # Add filepath-based cache key if available
            if current_filepath:
                filepath_cache_key = os.path.basename(current_filepath).lower()
                cache_keys_to_clear.append(filepath_cache_key)
                
            # Add title-based cache key
            title_cache_key = current_title.lower()
            cache_keys_to_clear.append(title_cache_key)
              # Clear cache entries for this media
            cleared_entries = 0
            if hasattr(actual_scrobbler, 'media_cache'):
                for cache_key in cache_keys_to_clear:
                    if actual_scrobbler.media_cache.get(cache_key):
                        actual_scrobbler.media_cache.remove(cache_key)
                        logger.info(f"Cleared cache entry for key: '{cache_key}'")
                        cleared_entries += 1
                
                # Save the updated cache
                actual_scrobbler.media_cache._save_cache()
            
            # Clear scrobbler state for re-identification (but keep tracking active)
            logger.info("Clearing scrobbler identification state for re-identification...")
            
            # Store current tracking state
            was_tracking = actual_scrobbler.currently_tracking
            was_filepath = getattr(actual_scrobbler, "current_filepath", None)
            was_start_time = getattr(actual_scrobbler, "start_time", None)
            was_watch_time = getattr(actual_scrobbler, "watch_time", 0)
            was_state = getattr(actual_scrobbler, "state", None)
            was_position = getattr(actual_scrobbler, "current_position_seconds", 0)
            was_duration = getattr(actual_scrobbler, "total_duration_seconds", None)
            
            # Clear identification-related state (but preserve tracking progress)
            actual_scrobbler.simkl_id = None
            actual_scrobbler.movie_name = None
            actual_scrobbler.media_type = None
            actual_scrobbler.season = None
            actual_scrobbler.episode = None
            actual_scrobbler.completed = False
            
            # Keep the tracking active with preserved state
            actual_scrobbler.currently_tracking = was_tracking
            actual_scrobbler.current_filepath = was_filepath
            actual_scrobbler.start_time = was_start_time
            actual_scrobbler.watch_time = was_watch_time
            actual_scrobbler.state = was_state
            actual_scrobbler.current_position_seconds = was_position
            actual_scrobbler.total_duration_seconds = was_duration
              # Force re-identification
            logger.info("Forcing re-identification process...")
            
            # Import the necessary modules
            from simkl_mps.simkl_api import is_internet_connected
            
            # Try to re-identify based on available information
            if current_filepath and is_internet_connected():
                # Try file-based identification first
                logger.info(f"Attempting file-based re-identification for: '{current_filepath}'")
                  # Parse with guessit to get media type hint
                guessit_info = None
                try:
                    import guessit
                    if guessit:
                        guessit_info = guessit.guessit(os.path.basename(current_filepath))
                        logger.info(f"Guessit info for re-identification: {guessit_info}")
                except ImportError:
                    logger.warning("Guessit library not available for re-identification")
                except Exception as e:
                    logger.warning(f"Guessit parsing failed during re-identification: {e}")
                
                # Call the identification method directly
                actual_scrobbler._identify_media_from_filepath(current_filepath, guessit_info)
                
            elif current_title and is_internet_connected():
                # Try title-based identification
                logger.info(f"Attempting title-based re-identification for: '{current_title}'")
                actual_scrobbler._identify_movie(current_title)
                
            else:
                # Offline or no data available
                logger.warning("Cannot re-identify: No internet connection or insufficient data")
                if not is_internet_connected():
                    self.show_notification("simkl-mps", "Cannot re-identify: No internet connection.")
                else:
                    self.show_notification("simkl-mps", "Cannot re-identify: Insufficient media information.")
                return 0
            
            # Prepare notification message
            # if cleared_entries > 0:
            #     message = f"Re-identifying '{current_title}' (cleared {cleared_entries} cache entries)"
            # else:
            #     message = f"Re-identifying '{current_title}'"
            
            # self.show_notification("simkl-mps", message)
            self.update_icon()
            
            logger.info(f"Re-identification process initiated for '{current_title}'")
            
        except Exception as e:
            logger.error(f"Error during try scrobble again: {e}", exc_info=True)
            self.show_notification("simkl-mps Error", f"Failed to re-identify media: {e}")
        
        return 0
