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
from PIL import Image, ImageDraw
import pystray
from plyer import notification
from .main import SimklScrobbler, APP_DATA_DIR

# Configure module logging
logger = logging.getLogger(__name__)

class TrayApp:
    """System tray application for SIMKL Scrobbler"""
    
    def __init__(self):
        self.scrobbler = None
        self.tray_icon = None
        self.monitoring_active = False
        self.setup_icon()
    
    def setup_icon(self):
        """Setup the system tray icon"""
        try:
            # Create a simple icon programmatically
            image = self.create_simple_icon()
            
            # Create the tray icon
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
    
    def create_simple_icon(self, size=64, bg_color=(240, 240, 240), fg_color=(66, 133, 244)):
        """Create a simple programmatically generated icon"""
        # Create a blank image with a white background
        image = Image.new('RGB', (size, size), color=bg_color)
        draw = ImageDraw.Draw(image)
        
        # Draw a colored circle
        padding = int(size * 0.1)
        draw.ellipse(
            [(padding, padding), (size - padding, size - padding)],
            fill=fg_color
        )
        
        # Add a simple "S" in the middle (if PIL version supports text)
        try:
            # Try to get a font - if not available, will skip this part
            draw.text(
                (size // 2 - 10, size // 2 - 15),
                "S",
                fill=(255, 255, 255),
            )
        except Exception:
            pass
            
        return image
    
    def create_menu(self):
        """Create the system tray menu"""
        return pystray.Menu(
            pystray.MenuItem(
                "Start Monitoring", 
                self.start_monitoring,
                enabled=lambda item: not self.monitoring_active
            ),
            pystray.MenuItem(
                "Stop Monitoring", 
                self.stop_monitoring,
                enabled=lambda item: self.monitoring_active
            ),
            pystray.MenuItem("Process Backlog", self.process_backlog),
            pystray.MenuItem("Open Logs", self.open_logs),
            pystray.MenuItem("About", self.show_about),
            pystray.MenuItem("Exit", self.exit_app)
        )
    
    def run(self):
        """Run the tray application"""
        logger.info("Starting SIMKL Scrobbler in tray mode")
        
        # Initialize scrobbler
        self.scrobbler = SimklScrobbler()
        if not self.scrobbler.initialize():
            print("Failed to initialize. Please check your credentials.")
            return
        
        # Auto-start monitoring
        self.start_monitoring()
            
        # Run the icon in the system tray with error handling
        try:
            self.tray_icon.run()
        except Exception as e:
            logger.error(f"Error running tray icon: {e}")
            print(f"Error with system tray: {e}")
            print("Falling back to console mode. Press Ctrl+C to stop.")
            
            # Keep the app running in console mode if tray fails
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
                self.show_notification(
                    "SIMKL Scrobbler", 
                    "Media monitoring started"
                )
                logger.info("Monitoring started from tray")
                print("Monitoring started")
            else:
                self.show_notification(
                    "SIMKL Scrobbler Error", 
                    "Failed to start monitoring"
                )
                print("Failed to start monitoring")
    
    def stop_monitoring(self, _=None):
        """Stop the scrobbler monitoring"""
        if self.monitoring_active:
            self.scrobbler.stop()
            self.monitoring_active = False
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
                self.show_notification(
                    "SIMKL Scrobbler Error", 
                    "Failed to process backlog"
                )
        
        # Run in a separate thread to avoid blocking the UI
        threading.Thread(target=_process, daemon=True).start()
    
    def open_logs(self, _=None):
        """Open the log file"""
        log_path = APP_DATA_DIR / "simkl_scrobbler.log"
        try:
            if sys.platform == "win32":
                os.startfile(str(log_path))  # Convert to string to ensure compatibility
            elif sys.platform == "darwin":  # macOS
                os.system(f"open '{str(log_path)}'")
            else:  # Linux
                os.system(f"xdg-open '{str(log_path)}'")
        except Exception as e:
            logger.error(f"Error opening log file: {e}")
            print(f"Could not open log file: {e}")
    
    def show_about(self, _=None):
        """Show about information"""
        self.show_notification(
            "About SIMKL Scrobbler", 
            "SIMKL Scrobbler automatically tracks movies you watch and syncs them to your SIMKL account."
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
            # Print to console as fallback
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
