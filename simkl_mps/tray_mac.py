"""
macOS-specific tray implementation for Media Player Scrobbler for SIMKL.
Provides system tray (menu bar) functionality for macOS platforms.
"""

import os
import sys
import time
import threading
import logging
import webbrowser
import subprocess
from pathlib import Path
from PIL import Image
import pystray
from plyer import notification

from simkl_mps.tray_base import TrayAppBase, get_simkl_scrobbler, logger
from simkl_mps.config_manager import get_setting, DEFAULT_THRESHOLD # Import for threshold menu

class TrayAppMac(TrayAppBase):
    """macOS system tray application for simkl-mps"""
    
    def __init__(self):
        super().__init__()
        self.tray_icon = None
        self._setup_auto_update_if_needed()
        self.setup_icon()
    
    def setup_icon(self):
        """Setup the system tray icon for macOS menu bar"""
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
    
    def load_icon_for_status(self):
        """Load the appropriate icon PIL.Image for the current status using the base class path finder."""
        icon_path_str = self._get_icon_path(status=self.status) # Use base class method

        if icon_path_str:
            try:
                icon_path = Path(icon_path_str)
                if icon_path.exists():
                    logger.debug(f"Loading tray icon from base path: {icon_path}")
                    # Load the image using PIL
                    img = Image.open(icon_path)
                    img.load() # Explicitly load image data
                    return img
                else:
                    logger.error(f"Icon path returned by base class does not exist: {icon_path}")
            except FileNotFoundError:
                logger.error(f"Icon file not found at path from base class: {icon_path_str}", exc_info=True)
            except Exception as e:
                # Catch potential PIL errors (e.g., UnidentifiedImageError)
                logger.error(f"Error loading icon from path {icon_path_str} with PIL: {type(e).__name__} - {e}", exc_info=True)
        else:
             logger.warning(f"Base class _get_icon_path did not return a path for status '{self.status}'.")

        # Fallback if base method fails or loading fails
        logger.warning("Falling back to generated image for tray icon.")
        return self._create_fallback_image()

    def create_menu(self):
        """Create the pystray menu using the base class helper."""
        # Build the list of menu items using the base class method
        menu_items = self._build_pystray_menu_items()
        # Create the pystray Menu object from the list
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

    def check_first_run(self):
        """Check if this is the first time the app is being run on macOS"""
        try:
            # For macOS, check for a first-run marker file in the application support directory
            first_run_marker = self.config_path.parent / ".first_run_complete"
            if first_run_marker.exists():
                self.is_first_run = False
            else:
                self.is_first_run = True
                # Create the marker file for next time
                try:
                    first_run_marker.touch()
                except Exception as e:
                    logger.warning(f"Error creating first run marker file: {e}")
            
        except Exception as e:
            logger.error(f"Unexpected error in first run check: {e}")
            self.is_first_run = False  # Default to not showing the notification on error

    def show_notification(self, title, message):
        """Show a desktop notification on macOS"""
        logger.debug(f"Showing macOS notification: {title} - {message}")
        
        try:
            # Try using plyer first
            try:
                notification.notify(
                    title=title,
                    message=message,
                    app_name="MPS for SIMKL",
                    timeout=10
                )
                logger.debug("macOS notification sent via plyer")
                return
            except Exception as plyer_err:
                logger.warning(f"Plyer notification failed: {plyer_err}")
            
            # Fallback to AppleScript
            try:
                # Escape double quotes in message and title
                title_escaped = title.replace('"', '\\"')
                message_escaped = message.replace('"', '\\"')
                
                cmd = f'''osascript -e 'display notification "{message_escaped}" with title "{title_escaped}"' '''
                os.system(cmd)
                logger.debug("macOS notification sent via AppleScript")
                return
            except Exception as as_err:
                logger.warning(f"AppleScript notification failed: {as_err}")
                
        except Exception as e:
            logger.error(f"All macOS notification methods failed: {e}")
        
        # Final fallback: Print to console
        print(f"\n🔔 NOTIFICATION: {title}\n{message}\n")
        logger.info(f"Notification displayed in console: {title} - {message}")

    def show_about(self, _=None):
        """Show application information on macOS"""
        try:
            # Try to get version information
            version = "Unknown"
            
            # Try to get from pkg_resources
            try:
                import pkg_resources
                version = pkg_resources.get_distribution("simkl-mps").version
            except:
                pass
            
            # Build the about text
            about_text = f"""Media Player Scrobbler for SIMKL
Version: {version}
Author: kavinthangavel
License: GNU GPL v3

Automatically track and scrobble your media to SIMKL."""

            # Use AppleScript dialog on macOS
            escaped_text = about_text.replace('"', '\\"')
            os.system(f'osascript -e \'display dialog "{escaped_text}" buttons {{"OK"}} default button "OK" with title "About MPS for SIMKL"\'')
                
        except Exception as e:
            logger.error(f"Error showing about dialog: {e}")
            self.show_notification("About", "Media Player Scrobbler for SIMKL")
        return 0

    def show_help(self, _=None):
        """Show help information on macOS"""
        try:
            # Open documentation
            help_url = "https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl#readme"
            webbrowser.open(help_url)
        except Exception as e:
            logger.error(f"Error showing help: {e}")
            self.show_notification("Help", "Visit https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl#readme for help")
        return 0

    def exit_app(self, _=None):
        """Exit the application"""
        logger.info("Exiting application from tray")
        if self.monitoring_active:
            self.stop_monitoring()
        if self.tray_icon:
            self.tray_icon.stop()
        return 0

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

    def check_updates_thread(self, _=None):
        """Wrapper to run the update check logic in a separate thread"""
        # Prevent multiple checks running simultaneously
        if hasattr(self, '_update_check_running') and self._update_check_running:
            logger.warning("Update check already in progress.")
            return
        self._update_check_running = True
        threading.Thread(target=self._check_updates_logic, daemon=True).start()

    def _check_updates_logic(self):
        """Check for updates using the shell script and update UI"""
        import subprocess
        import re
        
        logger.info("Checking for updates...")
        self.show_notification("Checking for Updates", "Looking for updates to MPS for SIMKL...")

        updater_script = 'updater.sh' 
        updater_path = self._get_updater_path(updater_script)

        if not updater_path or not updater_path.exists():
            logger.error(f"Updater script not found: {updater_path}")
            self.show_notification("Update Error", "Updater script not found.")
            self.update_icon() # Refresh menu
            self._update_check_running = False
            return

        try:
            # Make sure the script is executable
            try:
                os.chmod(str(updater_path), 0o755)
                logger.debug(f"Made updater script executable: {updater_path}")
            except Exception as e:
                logger.warning(f"Could not set executable permission on updater script: {e}")
            
            # Use --CheckOnly flag for the new script to just check without installing
            command = ["bash", str(updater_path), "--CheckOnly"]

            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False
            )

            stdout = process.stdout.strip()
            stderr = process.stderr.strip()
            exit_code = process.returncode

            logger.info(f"Update check script exited with code: {exit_code}")
            logger.debug(f"Update check stdout: {stdout}")
            if stderr:
                logger.debug(f"Update check stderr: {stderr}")

            # Process based on exit code first
            if exit_code != 0:
                # Exit code 1 from script means check failed
                if exit_code == 1:
                    logger.error("Update check failed (script exit code 1).")
                    self.show_notification("Update Check Failed", "Could not check for updates. Please try again later or check logs.")
                else:
                    # General script execution error
                    logger.error(f"Update check script failed with exit code {exit_code}. Stderr: {stderr}")
                    self.show_notification("Update Error", f"Failed to run update check script (Code: {exit_code}).")
            else:
                # Look for specific output patterns from the updated script
                if "UPDATE_AVAILABLE:" in stdout:
                    # Extract version and URL using regex to be more robust
                    version_match = re.search(r"UPDATE_AVAILABLE: ([0-9.]+) (https?://[^\s]+)", stdout)
                    if version_match:
                        version = version_match.group(1)
                        url = version_match.group(2)
                        logger.info(f"Update found: Version {version}")
                        
                        # Ask if the user wants to install the update
                        if self._ask_user_to_update(version):
                            # User wants to update - run the updater again without --CheckOnly
                            logger.info("User confirmed update, installing...")
                            self._run_update_installation()
                        else:
                            logger.info("User declined update")
                    else:
                        logger.error(f"Could not parse UPDATE_AVAILABLE string: {stdout}")
                        self.show_notification("Update Available", "An update is available. Use pip to update: pip install --upgrade simkl-mps[macos]")
                elif "NO_UPDATE:" in stdout:
                    # Extract current version
                    version_match = re.search(r"NO_UPDATE: ([0-9.]+)", stdout)
                    if version_match:
                        version = version_match.group(1)
                        logger.info(f"No update available. Current version: {version}")
                        self.show_notification("No Updates Available", f"You are already running the latest version ({version}).")
                    else:
                        logger.debug(f"Could not parse NO_UPDATE string: {stdout}")
                        self.show_notification("No Updates Available", "You are already running the latest version.")
                else:
                    # Unexpected output
                    logger.warning(f"Unexpected output from update check script: {stdout}")
                    self.show_notification("Update Check Info", "Update check completed with unclear results. Check logs.")

        except FileNotFoundError:
            logger.error(f"Error running update check: bash not found.")
            self.show_notification("Update Error", "bash not found.")
        except Exception as e:
            logger.error(f"Error during update check: {e}", exc_info=True)
            self.show_notification("Update Error", f"An error occurred during update check: {e}")
        finally:
            self.update_icon() # Refresh menu state
            self._update_check_running = False
    
    def _ask_user_to_update(self, version):
        """Ask the user if they want to update to the new version using macOS dialog"""
        try:
            # Use AppleScript to show a dialog with "Update" and "Later" buttons
            cmd = f'''osascript -e 'display dialog "A new version ({version}) of Media Player Scrobbler for SIMKL is available. Do you want to update now?" buttons {{"Later", "Update Now"}} default button "Update Now" with title "Update Available"' '''
            result = os.system(cmd)
            
            # AppleScript returns 0 if user clicked "Update Now"
            return result == 0
        except Exception as e:
            logger.error(f"Error asking for update confirmation: {e}")
            # For macOS, default to showing a notification without auto-updating
            self.show_notification("Update Available", f"Version {version} is available. Use pip to update manually.")
            return False
    
    def _run_update_installation(self):
        """Run the actual update installation for macOS"""
        try:
            updater_script = 'updater.sh'
            updater_path = self._get_updater_path(updater_script)
            
            if not updater_path or not updater_path.exists():
                logger.error(f"Updater script not found for installation: {updater_path}")
                self.show_notification("Update Error", "Updater script not found.")
                return False
            
            # Show notification
            self.show_notification("Installing Update", "Installing update. The application will restart when complete.")
            
            # Run the update script without --CheckOnly to perform the actual update
            subprocess.Popen(
                ["bash", str(updater_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            # Exit the application to allow the update to complete
            logger.info("Exiting application for update to complete")
            time.sleep(1)
            self.exit_app()
            return True
            
        except Exception as e:
            logger.error(f"Error running update installation: {e}")
            self.show_notification("Update Error", f"Failed to start update installation: {e}")
            return False
            
    def _setup_auto_update_if_needed(self):
        """Set up auto-updates for macOS if this is the first run"""
        try:
            # Check if LaunchAgent exists and create it if not
            import os
            from pathlib import Path
            
            # Create LaunchAgents directory if it doesn't exist
            launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
            os.makedirs(launch_agents_dir, exist_ok=True)
            
            # Path to the LaunchAgent plist
            plist_path = launch_agents_dir / "com.kavinthangavel.simkl-mps.updater.plist"
            
            # Only create the LaunchAgent if it doesn't exist
            if not plist_path.exists() and self.is_first_run:
                # Get the path to the updater script
                updater_path = self._get_updater_path("updater.sh")
                
                if updater_path and updater_path.exists():
                    # Create the plist contents
                    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kavinthangavel.simkl-mps.updater</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>{updater_path} --check-only</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Day</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>12</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>'''
                    
                    # Write the plist file
                    with open(plist_path, "w") as f:
                        f.write(plist_content)
                    
                    # Load the LaunchAgent
                    os.system(f"launchctl load {plist_path}")
                    
                    logger.info(f"Created and loaded LaunchAgent for auto-updates: {plist_path}")
        except Exception as e:
            logger.error(f"Error setting up macOS auto-updates: {e}")

    def _ask_custom_threshold_dialog(self, current_threshold: int) -> int | None:
        """macOS-specific implementation to ask for threshold using AppleScript."""
        try:
            # Use AppleScript to ask for a number input
            cmd = f'''osascript -e '
                set answer to text returned of (display dialog "Enter watch completion threshold (%):" \\
                default answer "{current_threshold}" \\
                with title "Set Watch Threshold" \\
                buttons {{"Cancel", "OK"}} default button "OK")
                return answer
            ' '''
            
            # Run the AppleScript and get the result
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                try:
                    # Try to convert the input to an integer
                    value = int(result.stdout.strip())
                    if 1 <= value <= 100:
                        logger.info(f"User entered custom threshold: {value}")
                        return value
                    else:
                        # Show error for out of range value
                        self.show_notification("Invalid Input", "Threshold must be between 1 and 100.")
                        logger.warning(f"User entered out of range threshold: {value}")
                        return None
                except ValueError:
                    # Show error for non-numeric input
                    self.show_notification("Invalid Input", "Please enter a number between 1 and 100.")
                    logger.warning(f"User entered non-numeric threshold: {result.stdout.strip()}")
                    return None
            else:
                # User cancelled or dialog failed
                logger.debug("User cancelled custom threshold input.")
                return None
        except Exception as e:
            logger.error(f"Error showing AppleScript threshold dialog: {e}", exc_info=True)
            self.show_notification("Error", f"Could not get custom threshold: {e}")
            return None

def run_tray_app():
    """Run the application in tray mode"""
    try:
        app = TrayAppMac()
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