"""
System tray implementation for SIMKL Scrobbler.
Provides a system tray icon and notifications for background operation.
"""

import os
import io
import sys
import time
import threading
import logging
import pathlib
from PIL import Image, ImageDraw, ImageFont
import pystray
from plyer import notification
from .main import SimklScrobbler, APP_DATA_DIR
import webbrowser
from pathlib import Path

# Configure module logging
logger = logging.getLogger(__name__)

class TrayApp:
    """System tray application for SIMKL Scrobbler"""
    
    def __init__(self):
        self.scrobbler = None
        self.tray_icon = None
        self.monitoring_active = False
        self.status = "stopped"  # running, paused, error, stopped
        self.status_details = ""
        self.last_scrobbled = None
        self.config_path = APP_DATA_DIR / ".simkl_scrobbler.env"
        self.log_path = APP_DATA_DIR / "simkl-scrobbler.log"
        self.setup_icon()
    
    def setup_icon(self):
        """Setup the system tray icon"""
        try:
            image = self.create_image()
            self.tray_icon = pystray.Icon(
                "simkl_scrobbler",
                image,
                "SIMKL Scrobbler",
                menu=self.create_menu()
            )
            logger.info("Tray icon setup successfully")
        except Exception as e:
            logger.error(f"Error setting up tray icon: {e}")
            raise

    def create_image(self, size=128):
        """Create the tray icon image with status indicator"""
        width = size
        height = size
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Status colors
        if self.status == "running":
            color = (34, 177, 76)
            ring_color = (22, 117, 50)
        elif self.status == "paused":
            color = (255, 127, 39)
            ring_color = (204, 102, 31)
        elif self.status == "error":
            color = (237, 28, 36)
            ring_color = (189, 22, 29)
        else:
            color = (112, 146, 190)
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
            pystray.MenuItem("📌 SIMKL Scrobbler", None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Status: {self.get_status_text()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        if self.status == "running":
            menu_items.append(pystray.MenuItem("Pause", self.pause_monitoring))
        else:
            menu_items.append(pystray.MenuItem("Start", self.start_monitoring))
        menu_items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Tools", pystray.Menu(
                pystray.MenuItem("Open Logs", self.open_logs),
                pystray.MenuItem("Open Config Directory", self.open_config_dir),
                pystray.MenuItem("Process Backlog Now", self.process_backlog),
            )),
            pystray.MenuItem("Online Services", pystray.Menu(
                pystray.MenuItem("SIMKL Website", self.open_simkl),
                pystray.MenuItem("View Watch History", self.open_simkl_history),
                pystray.MenuItem("Check for Updates", self.check_updates)
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("About", self.show_about),
            pystray.MenuItem("Help", self.show_help),
            pystray.MenuItem("Exit", self.exit_app)
        ]
        return pystray.Menu(*menu_items)

    def update_icon(self):
        """Update the tray icon and menu"""
        if self.tray_icon:
            self.tray_icon.icon = self.create_image()
            self.tray_icon.menu = self.create_menu()
            status_map = {"running": "Active", "paused": "Paused", "stopped": "Stopped", "error": "Error"}
            self.tray_icon.title = f"SIMKL Scrobbler - {status_map.get(self.status, 'Unknown')}"

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
        webbrowser.open("https://github.com/kavinthangavel/simkl-movie-tracker/releases")

    def show_help(self, _=None):
        """Show help information"""
        webbrowser.open("https://github.com/kavinthangavel/simkl-scrobbler/wiki")

    def show_about(self, _=None):
        """Show information about the application and ensure tray remains responsive after closing dialog"""
        about_text = (
            "SIMKL Scrobbler\n\n"
            "Automatically tracks and scrobbles movies you watch to your SIMKL account.\n\n"
            "Supports multiple media players and provides automatic movie identification.\n\n"
            "Author: Kavin Thangavel\n"
            "Website: https://github.com/kavinthangavel/simkl-movie-tracker\n\n"
            "© 2023-2024 All Rights Reserved"
        )
        def show_dialog():
            try:
                if sys.platform == 'win32':
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, about_text, "About SIMKL Scrobbler", 0)
                else:
                    try:
                        import tkinter as tk
                        from tkinter import messagebox
                        root = tk.Tk()
                        root.withdraw()
                        messagebox.showinfo("About SIMKL Scrobbler", about_text)
                        root.destroy()
                    except Exception:
                        print("\nAbout SIMKL Scrobbler:")
                        print(about_text)
            except Exception as e:
                logger.error(f"Error showing about dialog: {e}")
        # Run the dialog in a thread so it doesn't block the tray event loop
        threading.Thread(target=show_dialog, daemon=True).start()

    def run(self):
        """Run the tray application"""
        logger.info("Starting SIMKL Scrobbler in tray mode")
        self.scrobbler = SimklScrobbler()
        if not self.scrobbler.initialize():
            print("Failed to initialize. Please check your credentials.")
            self.status = "error"
            self.update_icon()
            return
        self.start_monitoring()
        try:
            self.tray_icon.run()
        except Exception as e:
            logger.error(f"Error running tray icon: {e}")
            print(f"Error with system tray: {e}")
            print("Falling back to console mode. Press Ctrl+C to stop.")
            try:
                while self.scrobbler and self.monitoring_active:
                    time.sleep(1)
            except KeyboardInterrupt:
                if self.monitoring_active:
                    self.stop_monitoring()
                print("Stopped monitoring.")

    def start_monitoring(self, _=None):
        """Start the scrobbler monitoring"""
        if not self.monitoring_active:
            if self.scrobbler.start():
                self.monitoring_active = True
                self.status = "running"
                self.update_icon()
                self.show_notification(
                    "SIMKL Scrobbler",
                    "Media monitoring started"
                )
                logger.info("Monitoring started from tray")
                print("Monitoring started")
            else:
                self.status = "error"
                self.update_icon()
                self.show_notification(
                    "SIMKL Scrobbler Error",
                    "Failed to start monitoring"
                )
                print("Failed to start monitoring")

    def pause_monitoring(self, _=None):
        """Pause monitoring (actually pause scrobbling, not just stop)"""
        if self.monitoring_active and self.status == "running":
            # If SimklScrobbler has a pause method, use it. Otherwise, stop and keep state.
            if hasattr(self.scrobbler, "pause"):
                self.scrobbler.pause()
            else:
                self.scrobbler.stop()
            self.status = "paused"
            self.update_icon()
            self.show_notification(
                "SIMKL Scrobbler",
                "Monitoring paused"
            )
            logger.info("Monitoring paused from tray")
            print("Monitoring paused")

    def resume_monitoring(self, _=None):
        """Resume monitoring from paused state"""
        if self.monitoring_active and self.status == "paused":
            # If SimklScrobbler has a resume method, use it. Otherwise, start again.
            if hasattr(self.scrobbler, "resume"):
                self.scrobbler.resume()
            else:
                self.scrobbler.start()
            self.status = "running"
            self.update_icon()
            self.show_notification(
                "SIMKL Scrobbler",
                "Monitoring resumed"
            )
            logger.info("Monitoring resumed from tray")
            print("Monitoring resumed")

    def stop_monitoring(self, _=None):
        """Stop the scrobbler monitoring"""
        if self.monitoring_active:
            self.scrobbler.stop()
            self.monitoring_active = False
            self.status = "stopped"
            self.update_icon()
            self.show_notification(
                "SIMKL Scrobbler",
                "Media monitoring stopped"
            )
            logger.info("Monitoring stopped from tray")
            print("Monitoring stopped")
            return True
        return False

    def process_backlog(self, _=None):
        """Process the backlog from the tray menu"""
        def _process():
            try:
                count = self.scrobbler.monitor.scrobbler.process_backlog()
                if count > 0:
                    self.show_notification(
                        "SIMKL Scrobbler",
                        f"Processed {count} backlog items"
                    )
                else:
                    self.show_notification(
                        "SIMKL Scrobbler",
                        "No backlog items to process"
                    )
            except Exception as e:
                logger.error(f"Error processing backlog: {e}")
                self.status = "error"
                self.update_icon()
                self.show_notification(
                    "SIMKL Scrobbler Error",
                    "Failed to process backlog"
                )
        threading.Thread(target=_process, daemon=True).start()

    def open_logs(self, _=None):
        """Open the log file"""
        log_path = APP_DATA_DIR
        try:
            if sys.platform == "win32":
                os.startfile(str(log_path))
            elif sys.platform == "darwin":
                os.system(f"open '{str(log_path)}'")
            else:
                os.system(f"xdg-open '{str(log_path)}'")
            self.show_notification(
                "SIMKL Scrobbler",
                "Log folder opened."
            )
        except Exception as e:
            logger.error(f"Error opening log file: {e}")
            self.show_notification(
                "SIMKL Scrobbler Error",
                f"Could not open log file: {e}"
            )

    def exit_app(self, _=None):
        """Exit the application"""
        logger.info("Exiting application from tray")
        if self.monitoring_active:
            self.stop_monitoring()
        if self.tray_icon:
            self.tray_icon.stop()

    def show_notification(self, title, message):
        """Show a desktop notification"""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="SIMKL Scrobbler",
                timeout=5
            )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            print(f"{title}: {message}")

def run_tray_app():
    """Run the application in tray mode"""
    try:
        # Setup logging to file when run directly
        if __name__ == "__main__":
            # Configure additional file logging when run as standalone
            from .main import APP_DATA_DIR
            log_file = APP_DATA_DIR / "tray_app.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
            logging.getLogger().addHandler(file_handler)
            logging.getLogger().setLevel(logging.INFO)
            logger.info(f"Tray application started directly, logging to {log_file}")
        
        app = TrayApp()
        app.run()
    except Exception as e:
        logger.error(f"Critical error in tray app: {e}")
        print(f"Failed to start in tray mode: {e}")
        
        # Fall back to console mode
        print("Falling back to console mode.")
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
    # When run directly, configure basic logging first
    logging.basicConfig(level=logging.INFO, 
                      format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    sys.exit(run_tray_app())
