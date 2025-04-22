"""
Service runner for SIMKL Scrobbler.
Runs the scrobbler in the background without a tray icon.
"""

import time
import sys
import logging
import signal
from plyer import notification
from .main import SimklScrobbler, APP_DATA_DIR

# Configure module logging
logger = logging.getLogger(__name__)

class ScrobblerService:
    """Runs the scrobbler as a standalone service without tray icon"""
    
    def __init__(self):
        self.scrobbler = None
        self.running = False
    
    def run(self):
        """Run the scrobbler service"""
        logger.info("Starting SIMKL Scrobbler service")
        
        # Handle signals for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Initialize scrobbler
        self.scrobbler = SimklScrobbler()
        if not self.scrobbler.initialize():
            logger.error("Failed to initialize scrobbler")
            self.show_notification(
                "SIMKL Scrobbler Error",
                "Failed to initialize. Please check your credentials."
            )
            return 1
            
        # Set the notification callback for the MovieScrobbler instance
        if hasattr(self.scrobbler, 'monitor') and hasattr(self.scrobbler.monitor, 'scrobbler'):
            self.scrobbler.monitor.scrobbler.set_notification_callback(self.show_notification)
            logger.debug("Set notification callback on MovieScrobbler")
        
        # Start monitoring
        if not self.scrobbler.start():
            logger.error("Failed to start scrobbler")
            self.show_notification(
                "SIMKL Scrobbler Error",
                "Failed to start monitoring."
            )
            return 1
        
        # Successfully started
        self.running = True
        self.show_notification(
            "SIMKL Scrobbler Service",
            "Media monitoring service started successfully."
        )
        
        # Keep process running
        try:
            # Process backlog initially
            self._process_backlog()
            
            # Main loop - periodically check backlog
            last_backlog_check = time.time()
            while self.running and self.scrobbler.running:
                time.sleep(10)  # Sleep to prevent high CPU usage
                
                # Process backlog every 5 minutes
                current_time = time.time()
                if current_time - last_backlog_check > 300:  # 300 seconds = 5 minutes
                    self._process_backlog()
                    last_backlog_check = current_time
                    
        except KeyboardInterrupt:
            logger.info("Service interrupted")
        finally:
            self._cleanup()
        
        return 0
    
    def _signal_handler(self, sig, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        self.running = False
    
    def _cleanup(self):
        """Clean up resources"""
        if self.scrobbler:
            self.scrobbler.stop()
            logger.info("Scrobbler service stopped")
            self.show_notification(
                "SIMKL Scrobbler Service",
                "Media monitoring service stopped."
            )
    
    def _process_backlog(self):
        """Process the backlog items"""
        try:
            if self.scrobbler and self.scrobbler.monitor:
                count = self.scrobbler.monitor.scrobbler.process_backlog()
                if count > 0:
                    logger.info(f"Processed {count} backlog items")
                    self.show_notification(
                        "SIMKL Scrobbler",
                        f"Processed {count} backlog items"
                    )
        except Exception as e:
            logger.error(f"Error processing backlog: {e}")
    
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

def run_service():
    """Run the scrobbler as a service"""
    service = ScrobblerService()
    return service.run()

if __name__ == "__main__":
    sys.exit(run_service())
