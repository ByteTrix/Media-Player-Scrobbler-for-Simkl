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
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import abc
import pystray

# Import API and credential functions
from simkl_mps.simkl_api import get_user_settings
from simkl_mps.credentials import get_credentials
# Import constants only, not the whole module
from simkl_mps.main import APP_DATA_DIR, APP_NAME
# Import settings functions
from simkl_mps.config_manager import get_setting, set_setting, DEFAULT_THRESHOLD

logger = logging.getLogger(__name__)

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

    def __init__(self):
        self.scrobbler = None
        self.monitoring_active = False
        self.status = "stopped"
        self.status_details = ""
        self.last_scrobbled = None
        self.config_path = APP_DATA_DIR / ".simkl_mps.env"
        self.log_path = APP_DATA_DIR / "simkl_mps.log"
        
        # Track whether this is a first run (for notifications)
        self.is_first_run = False
        self.check_first_run()

        # Improved asset path resolution for frozen applications
        if getattr(sys, 'frozen', False):
            # When frozen, look for assets in multiple locations
            base_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
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
            
            # Use the improved get_user_settings function that tries account endpoint first
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
                
            try:
                started = self.scrobbler.start()
                if started:
                    self.monitoring_active = True
                    self.update_status("running")
                    
                    # Only show notification if:
                    # 1. This is the first run of the app after installation
                    # 2. User manually started the app from the menu
                    if self.is_first_run or is_manual_start:
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
        def _process():
            try:
                result = self.scrobbler.monitor.scrobbler.process_backlog()
                
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

    # --- Watch Threshold Logic ---

    def _apply_threshold_change(self, new_threshold: int):
        """Applies the threshold change: saves, updates scrobbler, notifies, updates UI."""
        current_threshold = get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        if new_threshold is not None and new_threshold != current_threshold:
            try:
                set_setting('watch_completion_threshold', new_threshold)
                logger.info(f"Watch completion threshold set to {new_threshold}%")
                self.show_notification("Settings Updated", f"Watch threshold set to {new_threshold}%")

                # Attempt to update the running scrobbler instance
                if self.scrobbler and hasattr(self.scrobbler, 'monitor') and \
                   hasattr(self.scrobbler.monitor, 'scrobbler') and \
                   hasattr(self.scrobbler.monitor.scrobbler, 'completion_threshold'):

                    self.scrobbler.monitor.scrobbler.completion_threshold = new_threshold # Store as percentage
                    logger.debug(f"Updated running scrobbler instance threshold to {new_threshold}%")
                else:
                    logger.warning("Could not update running scrobbler instance threshold (not found or not running).")

                self.update_icon() # Refresh menu to show new checkmark/state

            except Exception as e:
                logger.error(f"Error applying watch threshold change: {e}", exc_info=True)
                self.show_notification("Error", f"Failed to set watch threshold: {e}")
                self.update_icon() # Still update icon on error
        elif new_threshold is None:
             logger.debug("Threshold change cancelled or dialog failed.")
             self.update_icon() # Refresh menu state even on cancel/failure
        else: # Threshold is the same as current
             logger.debug("Watch threshold not changed.")
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
        current_threshold = get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        result_queue = queue.Queue()

        def _ask_in_thread():
            """Runs the platform-specific dialog in a separate thread."""
            try:
                # Call the abstract method implemented by the subclass
                threshold = self._ask_custom_threshold_dialog(current_threshold)
                result_queue.put(threshold)
            except Exception as e:
                logger.error(f"Error in custom threshold dialog thread: {e}", exc_info=True)
                result_queue.put(None) # Ensure queue gets an item even on error

        def _process_result():
            """Waits for the result from the queue and processes it."""
            try:
                # Block until the result is available from the dialog thread
                new_threshold = result_queue.get(timeout=60) # Add timeout
            except queue.Empty:
                 logger.warning("Timeout waiting for custom threshold dialog result.")
                 new_threshold = None # or some default value
                 self.show_notification("Timeout", "Custom threshold dialog timed out.")
            except queue.Empty:
                 logger.warning("Timeout waiting for custom threshold dialog result.")
                 self.update_icon() # Refresh menu state on timeout
            except Exception as e:
                 logger.error(f"Error processing threshold result: {e}", exc_info=True)
                 self.update_icon() # Refresh menu state on error

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

    def check_first_run(self):
        """Check if this is the first time the app is being run"""
        # Platform-specific implementation required
        self.is_first_run = False # Default value, should be overridden
        
    def _build_pystray_menu_items(self):
        """Builds the list of pystray menu items common to multiple platforms."""
        # Get current threshold for radio button state
        current_threshold = get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)
        is_preset = lambda val: current_threshold == val

        # Start with basic items
        menu_items = [
            pystray.MenuItem("^_^ MPS for SIMKL", None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Status: {self.get_status_text()}", None, enabled=False), # Use lambda for dynamic text
            pystray.Menu.SEPARATOR,
        ]

        # Add Start/Stop item dynamically
        if self.status == "running":
            menu_items.append(pystray.MenuItem("Stop Monitoring", self.stop_monitoring))
        else: # Covers "stopped", "paused", "error"
            menu_items.append(pystray.MenuItem("Start Monitoring", self.start_monitoring))

        # --- Threshold Submenu ---
        threshold_submenu = pystray.Menu(
            pystray.MenuItem(
                '65%',
                lambda: self._set_preset_threshold(65),
                checked=lambda item: is_preset(65),
                radio=True
            ),
            pystray.MenuItem(
                '80% (Default)',
                lambda: self._set_preset_threshold(80),
                checked=lambda item: is_preset(80),
                radio=True
            ),
            pystray.MenuItem(
                '90%',
                lambda: self._set_preset_threshold(90),
                checked=lambda item: is_preset(90),
                radio=True
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                'Custom...',
                self.set_custom_watch_threshold # Call base class method
            )
        )

        # Add Tools submenu
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Tools", pystray.Menu(
            pystray.MenuItem("Local Watch History", self.open_watch_history),
            pystray.MenuItem("Watch Threshold (%)", threshold_submenu),
            pystray.MenuItem("Process Backlog Now", self.process_backlog),
            pystray.MenuItem("Open Logs", self.open_logs),
            pystray.MenuItem("Open Config Directory", self.open_config_dir),
        )))

        # Add Online Services submenu
        menu_items.append(pystray.MenuItem("Online Services", pystray.Menu(
            pystray.MenuItem("SIMKL Website", self.open_simkl),
            pystray.MenuItem("SIMKL Watch History", self.open_simkl_history),
        )))
        menu_items.append(pystray.Menu.SEPARATOR)

        # Check for Updates (Platform-specific action, but item is common)
        # The actual check logic might differ, but the menu item itself can be defined here.
        # The platform-specific check_updates_thread method will be called.
        menu_items.append(
            pystray.MenuItem(
                "Check for Updates",
                # Assuming each subclass implements check_updates_thread or similar
                lambda: self.check_updates_thread() if hasattr(self, 'check_updates_thread') else None
            )
        )

        # Add final items
        menu_items.append(pystray.MenuItem("About", self.show_about))
        menu_items.append(pystray.MenuItem("Help", self.show_help))
        menu_items.append(pystray.MenuItem("Exit", self.exit_app))

        return menu_items