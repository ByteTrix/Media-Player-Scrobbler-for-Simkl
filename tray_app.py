import sys
import os
import threading
import logging
import time
from pathlib import Path
from dotenv import load_dotenv
import pystray
from PIL import Image, ImageDraw
import PySimpleGUIQt as sg

# Import from our package
from simkl_movie_tracker.simkl_api import authenticate
from main import SimklMovieTracker, load_configuration

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("simkl_tracker.log")
    ]
)
logger = logging.getLogger(__name__)

class SimklTrayApp:
    """System tray application for Simkl Movie Tracker"""
    
    def __init__(self):
        self.tracker = None
        self.running = False
        self.tray = None
        self.client_id = None
        self.access_token = None
        self.app_path = os.path.abspath(sys.argv[0])
        self.startup_path = os.path.join(
            os.path.expanduser('~'), 
            'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
        )
        self.log_file_path = os.path.abspath("simkl_tracker.log")
        self.env_file_path = os.path.abspath(".env")
        self.menu_update_running = False
        self.current_movie = "None"
        self.progress = "0%"
        
    def initialize(self):
        """Initialize the application"""
        logger.info("Initializing Simkl Movie Tracker Tray App")
        
        # Step 1: Load or get configuration
        self.client_id, self.access_token = self.get_configuration()
        if not self.client_id:
            sg.popup("Configuration Error", "Missing Simkl Client ID. Cannot continue.")
            return False
            
        # Step 2: Create the tracker instance
        self.tracker = SimklMovieTracker()
        if not self.tracker.initialize():
            sg.popup("Error", "Failed to initialize the movie tracker.")
            return False
            
        # Step 3: Check if first run and ask about startup
        if not self.is_already_in_startup() and self.should_run_at_startup():
            self.add_to_startup()
            
        # Step 4: Set up the system tray icon and menu
        if not self._setup_tray():
            return False
            
        return True
        
    def get_configuration(self):
        """Load or acquire Simkl API credentials"""
        load_dotenv()
        client_id = os.getenv("SIMKL_CLIENT_ID")
        access_token = os.getenv("SIMKL_ACCESS_TOKEN")
        
        if not client_id:
            sg.popup("Missing Configuration", 
                    "No Simkl Client ID found. Please create an application on Simkl and get a Client ID.")
            return None, None
            
        if not access_token:
            sg.popup("Authentication Required", 
                    "You need to authenticate with Simkl. A browser window will open and you'll be asked to enter a PIN.")
            access_token = authenticate(client_id)
            
            if access_token:
                self.save_token_to_env(access_token)
            else:
                sg.popup("Authentication Failed", 
                        "Failed to authenticate with Simkl. Please try again later.")
                return client_id, None
                
        return client_id, access_token
        
    def save_token_to_env(self, token):
        """Save access token to .env file"""
        env_file = Path(self.env_file_path)
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                lines = f.readlines()
                
            token_exists = False
            for i, line in enumerate(lines):
                if line.startswith('SIMKL_ACCESS_TOKEN='):
                    lines[i] = f'SIMKL_ACCESS_TOKEN={token}\n'
                    token_exists = True
                    break
                    
            if not token_exists:
                lines.append(f'SIMKL_ACCESS_TOKEN={token}\n')
                
            with open(env_file, 'w') as f:
                f.writelines(lines)
        else:
            with open(env_file, 'w') as f:
                if self.client_id:
                    f.write(f'SIMKL_CLIENT_ID={self.client_id}\n')
                f.write(f'SIMKL_ACCESS_TOKEN={token}\n')
                
        logger.info("Saved access token to .env file")
        
    def is_already_in_startup(self):
        """Check if the app is already set to run at startup"""
        shortcut_path = os.path.join(self.startup_path, "Simkl Movie Tracker.lnk")
        return os.path.exists(shortcut_path)
        
    def should_run_at_startup(self):
        """Ask user if they want the app to run at startup"""
        result = sg.popup_yes_no(
            "Startup Configuration",
            "Would you like Simkl Movie Tracker to run automatically when Windows starts?",
            keep_on_top=True
        )
        return result == "Yes"
        
    def add_to_startup(self):
        """Add the application to Windows startup"""
        try:
            import win32com.client
            
            shortcut_path = os.path.join(self.startup_path, "Simkl Movie Tracker.lnk")
            
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            shortcut.Targetpath = python_exe
            shortcut.Arguments = f'"{self.app_path}"'
            shortcut.WorkingDirectory = os.path.dirname(self.app_path)
            shortcut.IconLocation = self.app_path
            shortcut.save()
            
            logger.info(f"Added to startup: {shortcut_path}")
            sg.popup("Startup Configuration", "Simkl Movie Tracker will now run at Windows startup.")
            return True
        except Exception as e:
            logger.error(f"Error adding to startup: {e}")
            sg.popup("Error", f"Failed to add to startup: {e}")
            return False
    
    def _get_icon_path(self):
        """Get the path to the tray icon"""
        # Try to find an icon in the same directory as the app
        icon_path = os.path.join(os.path.dirname(self.app_path), "icon.png")
        if os.path.exists(icon_path):
            return icon_path
            
        # Or try common icon locations
        for ext in ['.png', '.ico']:
            for name in ['icon', 'simkl_icon', 'app_icon']:
                path = os.path.join(os.path.dirname(self.app_path), f"{name}{ext}")
                if os.path.exists(path):
                    return path
        
        # If no icon found, return None to create a default one
        return None
    
    def _create_default_icon(self):
        """Create a default icon if no icon file is found"""
        # Create a simple white icon with "S" in the middle
        image = Image.new('RGB', (64, 64), color=(50, 50, 50))
        draw = ImageDraw.Draw(image)
        draw.text((25, 20), "S", fill=(255, 255, 255))
        return image
            
    def _setup_tray(self):
        """Set up the system tray icon using pystray"""
        try:
            # Get icon path or create default icon
            icon_path = self._get_icon_path()
            if icon_path:
                logger.info(f"Using icon file: {icon_path}")
                icon_image = Image.open(icon_path)
            else:
                logger.info("Creating default icon")
                icon_image = self._create_default_icon()
            
            # Create the menu items
            self.menu = self._create_menu()
            
            # Create the tray icon
            self.tray = pystray.Icon(
                "simkl_tracker", 
                icon_image, 
                "Simkl Movie Tracker",
                menu=self.menu
            )
            
            # Start the tray icon in a separate thread
            threading.Thread(target=self.tray.run, daemon=True).start()
            
            logger.info("Tray created successfully")
            return True
        except Exception as e:
            logger.error(f"Error setting up system tray: {e}")
            sg.popup("Error", f"Failed to set up system tray: {e}")
            return False
    
    def _create_menu(self):
        """Create the tray menu with pystray"""
        # Define a dummy action for disabled items
        dummy_action = lambda icon, item: None
        
        return pystray.Menu(
            pystray.MenuItem(f"Currently Tracking: {self.current_movie}", dummy_action, enabled=False),
            pystray.MenuItem(f"Progress: {self.progress}", dummy_action, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Status", lambda icon, item: self.show_status()),
            pystray.MenuItem("Start Tracking", lambda icon, item: self.start()),
            pystray.MenuItem("Stop Tracking", lambda icon, item: self.stop()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stop Tracking Current File", lambda icon, item: self.stop_tracking_current_file()),
            pystray.MenuItem("Open Log File", lambda icon, item: self.open_log_file()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.exit())
        )
    
    def _update_tray_menu(self):
        """Update the tray menu with current tracking info"""
        if not self.tray:
            return
            
        self.current_movie = "None"
        self.progress = "0%"
        
        if (hasattr(self.tracker, 'scrobbler') and 
            self.tracker.scrobbler and 
            hasattr(self.tracker.scrobbler, 'currently_tracking') and 
            self.tracker.scrobbler.currently_tracking):
            
            movie_name = None
            if hasattr(self.tracker.scrobbler, 'movie_name'):
                movie_name = self.tracker.scrobbler.movie_name
            
            self.current_movie = movie_name or self.tracker.scrobbler.currently_tracking
            
            if hasattr(self.tracker.scrobbler, 'watch_time') and hasattr(self.tracker.scrobbler, 'estimated_duration'):
                if self.tracker.scrobbler.estimated_duration > 0:
                    watch_min = self.tracker.scrobbler.watch_time / 60
                    est_duration = self.tracker.scrobbler.estimated_duration
                    self.progress = f"{min(100, (watch_min / est_duration) * 100):.1f}%"
        
        try:
            # Update menu with new values
            self.menu = self._create_menu()
            self.tray.menu = self.menu  # Update the menu property directly
            logger.debug("Tray menu updated successfully")
        except Exception as e:
            logger.error(f"Error updating tray menu: {e}")
                
    def start(self):
        """Start the application"""
        if not self.running:
            threading.Thread(target=self.tracker.start, daemon=True).start()
            self.running = True
            self._show_notification("Simkl Movie Tracker", "Movie tracking started.")
            logger.info("Movie tracking started")
            
    def stop(self):
        """Stop the application"""
        if self.running:
            self.tracker.stop()
            self.running = False
            self._show_notification("Simkl Movie Tracker", "Movie tracking stopped.")
            logger.info("Movie tracking stopped")
    
    def _show_notification(self, title, message):
        """Show a notification using pystray"""
        if self.tray and hasattr(self.tray, 'notify'):
            try:
                self.tray.notify(message)
            except Exception as e:
                logger.error(f"Error showing notification: {e}")
                # Fallback to sg.popup
                sg.popup_no_wait(title, message, auto_close=True, auto_close_duration=3)
        else:
            # Fallback to sg.popup
            sg.popup_no_wait(title, message, auto_close=True, auto_close_duration=3)
            
    def stop_tracking_current_file(self):
        """Stop tracking the current file without stopping the entire tracker"""
        if self.running and hasattr(self.tracker, 'scrobbler') and self.tracker.scrobbler:
            current_movie = self.tracker.scrobbler.currently_tracking
            if current_movie:
                self.tracker.scrobbler.currently_tracking = None
                self.tracker.scrobbler.state = "stopped"
                self._show_notification("Simkl Movie Tracker", f"Stopped tracking: {current_movie}")
                logger.info(f"Stopped tracking: {current_movie}")
                self._update_tray_menu()
            else:
                self._show_notification("Simkl Movie Tracker", "No movie currently being tracked.")
                logger.info("No movie currently being tracked")
                
    def show_status(self):
        """Show the current tracking status"""
        status_text = "Simkl Movie Tracker Status\n\n"
        
        if (hasattr(self.tracker, 'scrobbler') and 
            self.tracker.scrobbler and 
            hasattr(self.tracker.scrobbler, 'currently_tracking') and 
            self.tracker.scrobbler.currently_tracking):
            
            movie = self.tracker.scrobbler.currently_tracking
            movie_name = self.tracker.scrobbler.movie_name if hasattr(self.tracker.scrobbler, 'movie_name') else movie
            progress = 0
            state = "Unknown"
            player = self.tracker.scrobbler.current_player if hasattr(self.tracker.scrobbler, 'current_player') else "Unknown"
            
            if hasattr(self.tracker.scrobbler, 'watch_time') and hasattr(self.tracker.scrobbler, 'estimated_duration'):
                watch_min = self.tracker.scrobbler.watch_time / 60
                est_duration = self.tracker.scrobbler.estimated_duration
                progress = min(100, (watch_min / est_duration) * 100)
                
            if hasattr(self.tracker.scrobbler, 'state'):
                state = self.tracker.scrobbler.state
                
            status_text += f"Currently Tracking: {movie_name}\n"
            status_text += f"Media Player: {player}\n"
            status_text += f"Progress: {progress:.1f}%\n"
            status_text += f"State: {state}\n"
            
            if hasattr(self.tracker.scrobbler, 'simkl_id') and self.tracker.scrobbler.simkl_id:
                status_text += f"Simkl ID: {self.tracker.scrobbler.simkl_id}\n"
        else:
            status_text += "No movie currently being tracked.\n"
            
        if hasattr(self.tracker, 'scrobbler') and hasattr(self.tracker.scrobbler, 'backlog'):
            pending = len(self.tracker.scrobbler.backlog.get_pending())
            if pending > 0:
                status_text += f"\nBacklog: {pending} items pending sync"
                
        status_text += f"\n\nLog file: {self.log_file_path}"
                
        sg.popup("Status", status_text, keep_on_top=True)
        
    def open_log_file(self):
        """Open the log file in the default text editor"""
        if os.path.exists(self.log_file_path):
            try:
                os.startfile(self.log_file_path)
                logger.info(f"Opened log file: {self.log_file_path}")
            except Exception as e:
                logger.error(f"Error opening log file: {e}")
                sg.popup("Error", f"Failed to open log file: {e}")
        else:
            logger.warning("Log file not found")
            sg.popup("Error", "Log file not found.")
    
    def exit(self):
        """Exit the application"""
        try:
            self.stop()
            self.menu_update_running = False
            # Stop the tray icon
            if self.tray:
                self.tray.stop()
            logger.info("Application exiting")
            # Exit the application after a short delay
            threading.Timer(0.5, lambda: os._exit(0)).start()
        except Exception as e:
            logger.error(f"Error during exit: {e}")
            os._exit(1)
        
    def run(self):
        """Run the application main loop"""
        logger.info("Starting Simkl Movie Tracker tray application")
        
        # Start the tracking
        self.start()
        
        # Start the menu update thread
        self.menu_update_running = True
        threading.Thread(target=self._menu_update_loop, daemon=True).start()
        
        # With pystray, the main thread doesn't need to block in a loop
        # as the tray icon is running in its own thread.
        # We can keep the main thread alive with a simple while loop if needed
        try:
            while self.menu_update_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.exit()
        
    def _menu_update_loop(self):
        """Loop to update the tray menu with current tracking info"""
        logger.info("Starting menu update loop")
        while self.menu_update_running:
            try:
                self._update_tray_menu()
            except Exception as e:
                logger.error(f"Error in menu update loop: {e}")
            time.sleep(5)
        logger.info("Menu update loop stopped")
        
def main():
    """Main entry point for the tray application"""
    try:
        logger.info("Starting Simkl Movie Tracker Tray App")
        app = SimklTrayApp()
        if app.initialize():
            app.run()
        else:
            logger.error("Failed to initialize Simkl Movie Tracker Tray App")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        sg.popup_error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()