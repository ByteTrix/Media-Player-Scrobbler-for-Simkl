import sys
import os
import threading
import logging
from dotenv import load_dotenv
import PySimpleGUIQt as sg
from PySimpleGUIQt import SystemTray

# Import from our package
from simkl_movie_tracker.media_tracker import MovieScrobbler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("simkl_tracker.log")
    ]
)
logger = logging.getLogger(__name__)

# Import the tracker
from main import SimklMovieTracker, load_configuration

class SimklTrayApp:
    """System tray application for Simkl Movie Tracker"""
    
    def __init__(self):
        self.tracker = None
        self.running = False
        self.tray = None
        self.menu = None
        self.client_id = None
        self.access_token = None
        
    def initialize(self):
        """Initialize the application"""
        logger.info("Initializing Simkl Movie Tracker Tray App")
        
        # Load configuration
        try:
            self.client_id, self.access_token = load_configuration()
            if not self.client_id or not self.access_token:
                sg.popup("Configuration Error", "Missing Simkl API credentials. Check your .env file.")
                return False
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            sg.popup("Error", f"Failed to load configuration: {e}")
            return False
            
        # Set up the system tray icon and menu
        self._setup_tray()
        
        # Create the tracker instance
        self.tracker = SimklMovieTracker()
        if not self.tracker.initialize():
            sg.popup("Error", "Failed to initialize the movie tracker.")
            return False
            
        return True
        
    def _setup_tray(self):
        """Set up the system tray icon and menu"""
        # Define the menu
        menu = ['', 
            ['Show Status', 'Start Tracking', 'Stop Tracking', '---', 'Exit']
        ]
        
        # Create the tray icon
        self.tray = SystemTray(menu=menu, filename=self._get_icon_path())
        self.tray.show_message("Simkl Movie Tracker", "The tracker is running in the background.")
        
    def _get_icon_path(self):
        """Get the path to the tray icon"""
        # If you have an icon file, return its path here
        # For now, using a default icon
        return None
        
    def start(self):
        """Start the application"""
        if not self.running:
            # Start the tracker in a separate thread
            threading.Thread(target=self.tracker.start, daemon=True).start()
            self.running = True
            self.tray.show_message("Simkl Movie Tracker", "Movie tracking started.")
            
    def stop(self):
        """Stop the application"""
        if self.running:
            self.tracker.stop()
            self.running = False
            self.tray.show_message("Simkl Movie Tracker", "Movie tracking stopped.")
            
    def show_status(self):
        """Show the current tracking status"""
        status_text = "Simkl Movie Tracker Status\n\n"
        
        # Get current movie if any
        if hasattr(self.tracker.scrobbler, 'currently_tracking') and self.tracker.scrobbler.currently_tracking:
            movie = self.tracker.scrobbler.currently_tracking
            movie_name = self.tracker.scrobbler.movie_name or movie
            progress = 0
            state = "Unknown"
            
            if hasattr(self.tracker.scrobbler, 'watch_time') and hasattr(self.tracker.scrobbler, 'estimated_duration'):
                watch_min = self.tracker.scrobbler.watch_time / 60
                est_duration = self.tracker.scrobbler.estimated_duration
                progress = min(100, (watch_min / est_duration) * 100)
                
            if hasattr(self.tracker.scrobbler, 'state'):
                state = self.tracker.scrobbler.state
                
            status_text += f"Currently Tracking: {movie_name}\n"
            status_text += f"Progress: {progress:.1f}%\n"
            status_text += f"State: {state}\n"
        else:
            status_text += "No movie currently being tracked.\n"
            
        # Show backlog info
        if hasattr(self.tracker.scrobbler, 'backlog'):
            pending = len(self.tracker.scrobbler.backlog.get_pending())
            if pending > 0:
                status_text += f"\nBacklog: {pending} items pending sync"
                
        sg.popup("Status", status_text)
        
    def run(self):
        """Run the application main loop"""
        # Start tracking immediately
        self.start()
        
        # Run the tray loop
        while True:
            event = self.tray.read()
            
            if event == 'Exit':
                self.stop()
                break
            elif event == 'Start Tracking':
                self.start()
            elif event == 'Stop Tracking':
                self.stop()
            elif event == 'Show Status':
                self.show_status()
                
        # Clean up
        self.tray.close()
        
def main():
    """Main entry point for the tray application"""
    app = SimklTrayApp()
    if app.initialize():
        app.run()

if __name__ == "__main__":
    main()