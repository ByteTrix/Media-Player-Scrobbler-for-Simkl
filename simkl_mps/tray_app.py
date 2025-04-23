"""
System tray implementation for Media Player Scrobbler for SIMKL.
Provides a system tray icon and notifications for background operation.
"""

import os
import sys
import time
import threading
import logging
import webbrowser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pystray
from plyer import notification

# Import constants only, not the whole module
from simkl_mps.main import APP_DATA_DIR, APP_NAME

logger = logging.getLogger(__name__)

def get_simkl_scrobbler():
    """Lazy import for SimklScrobbler to avoid circular imports"""
    from simkl_mps.main import SimklScrobbler
    return SimklScrobbler

class TrayApp:
    """System tray application for simkl-mps"""
    
    def __init__(self):
        self.scrobbler = None
        self.tray_icon = None
        self.monitoring_active = False
        self.status = "stopped"
        self.status_details = ""
        self.last_scrobbled = None
        self.config_path = APP_DATA_DIR / ".simkl_mps.env"
        self.log_path = APP_DATA_DIR / "simkl_mps.log"

        # Improved asset path resolution for frozen applications
        if getattr(sys, 'frozen', False):
            # When frozen, look for assets in multiple locations
            base_dir = Path(sys._MEIPASS)
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
            self.assets_dir = Path(__file__).parent / "assets"
            logger.info(f"Using assets directory from source: {self.assets_dir}")
        
        # Check for first run auto-update setup
        self._setup_auto_update_if_needed()
        
        self.setup_icon()
    
    def setup_icon(self):
        """Setup the system tray icon"""
        try:
            image = self.load_icon_for_status()
            
            self.tray_icon = pystray.Icon(
                "simkl-mps",
                image,
                "MPS for SIMKL",
                menu=self.create_menu()
            )
            logger.info("Tray icon setup successfully")
        except Exception as e:
            logger.error(f"Error setting up tray icon: {e}")
            raise
    
    def update_status(self, new_status, details="", last_scrobbled=None):
        """Update the status and refresh the icon"""
        if new_status != self.status or details != self.status_details or last_scrobbled != self.last_scrobbled:
            self.status = new_status
            self.status_details = details
            if last_scrobbled:
                self.last_scrobbled = last_scrobbled
            self.update_icon()
            logger.debug(f"Status updated to {new_status} - {details}")
    
    def load_icon_for_status(self):
        """Load the appropriate icon for the current status"""
        try:
            # Try multiple icon formats and fallbacks
            icon_format = "ico" if sys.platform == "win32" else "png"
            
            # List of possible icon files to check in order of preference
            icon_paths = [
                # Status-specific icons
                self.assets_dir / f"simkl-mps-{self.status}.{icon_format}",
                self.assets_dir / f"simkl-mps-{self.status}.png",  # PNG fallback
                self.assets_dir / f"simkl-mps-{self.status}.ico",  # ICO fallback
                
                # Generic icons
                self.assets_dir / f"simkl-mps.{icon_format}",
                self.assets_dir / f"simkl-mps.png",  # PNG fallback
                self.assets_dir / f"simkl-mps.ico"   # ICO fallback
            ]
            
            # Use the first icon that exists
            for icon_path in icon_paths:
                if icon_path.exists():
                    logger.debug(f"Loading tray icon: {icon_path}")
                    return Image.open(icon_path)
            
            logger.error(f"No suitable icon found in assets directory: {self.assets_dir}")
            logger.error(f"Expected one of: {[p.name for p in icon_paths]}")
            return self._create_fallback_image()
            
        except FileNotFoundError as e:
            logger.error(f"Icon file not found: {e}", exc_info=True)
            return self._create_fallback_image()
        except Exception as e:
            logger.error(f"Error loading status icon: {e}", exc_info=True)
            return self._create_fallback_image()
    
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

    def create_menu(self):
        """Create the system tray menu with a professional layout"""
        menu_items = [
            pystray.MenuItem("📌 MPS for SIMKL", None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Status: {self.get_status_text()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        
        if self.status == "running" or self.status == "active":
            menu_items.append(pystray.MenuItem("Pause", self.pause_monitoring))
        else:
            menu_items.append(pystray.MenuItem("Start", self.start_monitoring))
        
        menu_items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for Updates", self.check_updates),  # Moved to top level
            pystray.MenuItem("Tools", pystray.Menu(
                pystray.MenuItem("Open Logs", self.open_logs),
                pystray.MenuItem("Open Config Directory", self.open_config_dir),
                pystray.MenuItem("Process Backlog Now", self.process_backlog),
            )),
            pystray.MenuItem("Online Services", pystray.Menu(
                pystray.MenuItem("SIMKL Website", self.open_simkl),
                pystray.MenuItem("View Watch History", self.open_simkl_history),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("About", self.show_about),
            pystray.MenuItem("Help", self.show_help),
            pystray.MenuItem("Exit", self.exit_app)
        ])
        
        return pystray.Menu(*menu_items)

    def update_icon(self):
        """Update the tray icon and menu to reflect the current status"""
        if self.tray_icon:
            try:
                new_icon = self.load_icon_for_status()
                self.tray_icon.icon = new_icon
                self.tray_icon.menu = self.create_menu()
                status_map = {
                    "running": "Active", 
                    "paused": "Paused", 
                    "stopped": "Stopped", 
                    "error": "Error"
                }
                status_text = status_map.get(self.status, "Unknown")
                if self.status_details:
                    status_text += f" - {self.status_details}"
                
                self.tray_icon.title = f"MPS for SIMKL - {status_text}"
                
                logger.debug(f"Updated tray icon to status: {self.status}")
            except Exception as e:
                logger.error(f"Failed to update tray icon: {e}", exc_info=True)

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

    def open_simkl(self, _=None):
        """Open the SIMKL website"""
        webbrowser.open("https://simkl.com")

    def open_simkl_history(self, _=None):
        """Open the SIMKL history page"""
        webbrowser.open("https://simkl.com/movies/history/")

    def check_updates(self, _=None):
        """Check for updates to the application"""
        logger.info("Checking for updates...")
        
        import platform
        import subprocess
        import sys
        from pathlib import Path
        
        system = platform.system().lower()
        
        try:
            if system == 'windows':
                # Windows update using PowerShell
                from simkl_mps.cli import check_for_updates
                check_for_updates(silent=False)
            elif system == 'darwin':  # macOS
                # Use macOS update script
                updater_path = self._get_updater_path('updater.sh')
                if updater_path.exists():
                    subprocess.Popen(['bash', str(updater_path)])
                else:
                    self.show_notification("Update Error", "Updater script not found for macOS")
            elif system == 'linux':
                # Use Linux update script
                updater_path = self._get_updater_path('updater.sh')
                if updater_path.exists():
                    subprocess.Popen(['bash', str(updater_path)])
                else:
                    self.show_notification("Update Error", "Updater script not found for Linux")
            else:
                self.show_notification("Update Error", f"Updates not supported on {system}")
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            self.show_notification("Update Error", f"Failed to check for updates: {e}")

    def _get_updater_path(self, filename):
        """Get the path to the updater script"""
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

    def show_notification(self, title, message):
        """Show a desktop notification"""
        try:
            # Get the app icon path for notifications
            icon_path = self._get_icon_path("active")
            
            notification.notify(
                title=title,
                message=message,
                app_name="MPS for SIMKL",  # Fixed app name without .exe
                app_icon=icon_path,        # Add icon to notifications
                timeout=10
            )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def run(self):
        """Run the tray application"""
        logger.info("Starting Media Player Scrobbler for SIMKL in tray mode")
        self.scrobbler = get_simkl_scrobbler()()
        initialized = self.scrobbler.initialize()
        if initialized:
            started = self.start_monitoring()
            if not started:
                self.update_status("error", "Failed to start monitoring")
        else:
            self.update_status("error", "Failed to initialize")
            
        try:
            self.tray_icon.run()
        except Exception as e:
            logger.error(f"Error running tray icon: {e}")
            self.show_notification("Tray Error", f"Error with system tray: {e}")
            
            try:
                while self.scrobbler and self.monitoring_active:
                    time.sleep(1)
            except KeyboardInterrupt:
                if self.monitoring_active:
                    self.stop_monitoring()

    def start_monitoring(self, _=None):
        """Start the scrobbler monitoring"""
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

    def pause_monitoring(self, _=None):
        """Pause monitoring (actually pause scrobbling, not just stop)"""
        if self.monitoring_active and self.status == "running":
            if hasattr(self.scrobbler, "pause"):
                self.scrobbler.pause()
            else:
                self.scrobbler.stop()
            self.update_status("paused")
            self.show_notification(
                "simkl-mps",
                "Monitoring paused"
            )
            logger.info("Monitoring paused from tray")

    def resume_monitoring(self, _=None):
        """Resume monitoring from paused state"""
        if self.monitoring_active and self.status == "paused":
            if hasattr(self.scrobbler, "resume"):
                self.scrobbler.resume()
            else:
                self.scrobbler.start()
            self.update_status("running")
            self.show_notification(
                "simkl-mps",
                "Monitoring resumed"
            )
            logger.info("Monitoring resumed from tray")

    def stop_monitoring(self, _=None):
        """Stop the scrobbler monitoring"""
        if self.monitoring_active:
            self.scrobbler.stop()
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
        threading.Thread(target=_process, daemon=True).start()

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

    def exit_app(self, _=None):
        """Exit the application"""
        logger.info("Exiting application from tray")
        if self.monitoring_active:
            self.stop_monitoring()
        if self.tray_icon:
            self.tray_icon.stop()

    def _setup_auto_update_if_needed(self):
        """Set up auto-updates if this is the first run"""
        try:
            import platform
            import subprocess
            import os
            from pathlib import Path
            
            config_dir = Path.home() / ".config" / "simkl-mps"
            first_run_file = config_dir / "first_run"
            
            # Only run if the first_run file exists
            if first_run_file.exists():
                system = platform.system().lower()
                
                if system == 'darwin':  # macOS
                    # The LaunchAgent should already be set up by the installer
                    # Just run the updater with the first-run check flag
                    updater_path = self._get_updater_path('updater.sh')
                    if updater_path.exists():
                        subprocess.Popen(['bash', str(updater_path), '--check-first-run'])
                
                elif system.startswith('linux'):
                    # For Linux, check if systemd is available and if the timer is set up
                    updater_path = self._get_updater_path('updater.sh')
                    setup_script_path = self._get_updater_path('setup-auto-update.sh')
                    
                    if updater_path.exists():
                        # Run the updater with the first-run check flag
                        subprocess.Popen(['bash', str(updater_path), '--check-first-run'])
                    
                    # If setup script exists and systemd is available but timer not set up,
                    # ask the user if they want to enable auto-updates
                    if setup_script_path.exists():
                        import tkinter as tk
                        from tkinter import messagebox
                        
                        systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
                        timer_file = systemd_user_dir / "simkl-mps-updater.timer"
                        
                        if not timer_file.exists():
                            # Create a hidden root window
                            root = tk.Tk()
                            root.withdraw()
                            
                            # Ask user about enabling auto-updates
                            if messagebox.askyesno(
                                "MPSS Auto-Update", 
                                "Would you like to enable weekly automatic update checks?"
                            ):
                                # Run the setup script
                                subprocess.run(['bash', str(setup_script_path)])
                            
                            root.destroy()
                
                # Remove the first_run file regardless of outcome
                first_run_file.unlink(missing_ok=True)
        
        except Exception as e:
            logger.error(f"Error setting up auto-updates: {e}")

def run_tray_app():
    """Run the application in tray mode"""
    try:
        app = TrayApp()
        app.run()
    except Exception as e:
        logger.error(f"Critical error in tray app: {e}")
        print(f"Failed to start in tray mode: {e}")
        print("Falling back to console mode.")
        
        # Only import SimklScrobbler here to avoid circular imports
        from simkl_mps.main import SimklScrobbler
        
        scrobbler = SimklScrobbler()
        if scrobbler.initialize():
            print("Scrobbler initialized. Press Ctrl+C to exit.")
            if scrobbler.start():
                try:
                    while scrobbler.running:
                        time.sleep(1)
                except KeyboardInterrupt:
                    scrobbler.stop()
                    print("Stopped monitoring.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                      format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    sys.exit(run_tray_app())
