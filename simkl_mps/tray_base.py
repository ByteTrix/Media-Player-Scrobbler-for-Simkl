"""
Base tray implementation for Media Player Scrobbler for SIMKL.
Provides common functionality for all platform-specific tray implementations.
"""

import os
import sys
import time
import threading
import logging
import webbrowser
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Import API and credential functions
from simkl_mps.simkl_api import get_user_settings
from simkl_mps.credentials import get_credentials
# Import constants only, not the whole module
from simkl_mps.main import APP_DATA_DIR, APP_NAME

logger = logging.getLogger(__name__)

def get_simkl_scrobbler():
    """Lazy import for SimklScrobbler to avoid circular imports"""
    from simkl_mps.main import SimklScrobbler
    return SimklScrobbler

class TrayAppBase:
    """Base system tray application for simkl-mps"""
    
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

    def _get_icon_path(self, status="active"):
        """Get the path to an icon file based on status, prioritizing high-resolution icons"""
        try:
            # Platform-specific considerations
            if sys.platform == "win32":
                # Windows prefers ICO files, but can use high-res PNGs too
                preferred_formats = ["ico", "png"]
                preferred_sizes = [256, 128, 64, 32]  # Ordered by preference (highest first)
            elif sys.platform == "darwin":
                # macOS works best with high-res PNG files
                preferred_formats = ["png", "ico"]
                preferred_sizes = [512, 256, 128, 64]  # macOS prefers higher res
            else:
                # Linux typically uses PNG files
                preferred_formats = ["png", "ico"]
                preferred_sizes = [256, 128, 64, 32]
            
            # First, try to find size-specific icons with the status
            for size in preferred_sizes:
                for fmt in preferred_formats:
                    # Check for size-specific status icon
                    paths = [
                        self.assets_dir / f"simkl-mps-{status}-{size}.{fmt}",
                        self.assets_dir / f"simkl-mps-{size}.{fmt}"  # Generic size-specific
                    ]
                    for path in paths:
                        if path.exists():
                            logger.debug(f"Using high-resolution icon for notification: {path}")
                            return str(path)
            
            # If we don't find size-specific icons, try the standard ones
            icon_paths = []
            
            # Add status-specific icons first
            for fmt in preferred_formats:
                icon_paths.append(self.assets_dir / f"simkl-mps-{status}.{fmt}")
            
            # Add general icons as fallback
            for fmt in preferred_formats:
                icon_paths.append(self.assets_dir / f"simkl-mps.{fmt}")
            
            # Try to find any usable icon
            for path in icon_paths:
                if path.exists():
                    logger.debug(f"Using standard icon for notification: {path}")
                    return str(path)
            
            # Last resort - look in the system path for the executable's directory
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                for fmt in preferred_formats:
                    icon_path = exe_dir / f"simkl-mps.{fmt}"
                    if icon_path.exists():
                        logger.debug(f"Using executable directory icon: {icon_path}")
                        return str(icon_path)
            
            # If no icon found, return None
            logger.warning(f"No suitable icon found for notifications in: {self.assets_dir}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding icon path: {e}")
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
                count = self.scrobbler.monitor.scrobbler.process_backlog()
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

    def check_first_run(self):
        """Check if this is the first time the app is being run"""
        # Platform-specific implementation required
        self.is_first_run = False

    def update_icon(self):
        """Update the tray icon - to be implemented by platform-specific classes"""
        pass
        
    def show_notification(self, title, message):
        """Show a desktop notification - to be implemented by platform-specific classes"""
        pass
        
    def show_about(self, _=None):
        """Show about dialog - to be implemented by platform-specific classes"""
        pass
        
    def show_help(self, _=None):
        """Show help - to be implemented by platform-specific classes"""
        pass
        
    def exit_app(self, _=None):
        """Exit the application - to be implemented by platform-specific classes"""
        pass
        
    def run(self):
        """Run the tray application - to be implemented by platform-specific classes"""
        pass