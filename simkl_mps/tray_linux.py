"""
Linux-specific tray implementation for Media Player Scrobbler for SIMKL.
Provides system tray functionality for Linux platforms with support for both
AppIndicator (modern GNOME/Ubuntu) and traditional system tray.
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

from simkl_mps.tray_base import TrayAppBase, get_simkl_scrobbler, logger

# Enhance detection for Ubuntu GNOME environment
def detect_environment():
    """Detect Linux desktop environment and capabilities"""
    desktop_env = os.environ.get('XDG_CURRENT_DESKTOP', '')
    session_type = os.environ.get('XDG_SESSION_TYPE', '')
    
    # Check for GNOME AppIndicator extension
    has_appindicator_extension = False
    try:
        if 'GNOME' in desktop_env:
            # Try to check if the AppIndicator extension is enabled
            output = subprocess.check_output(
                ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                stderr=subprocess.DEVNULL
            ).decode('utf-8')
            
            # Common AppIndicator extension IDs
            extension_ids = [
                "appindicatorsupport@rgcjonas.gmail.com",  # Standard GNOME extension
                "ubuntu-appindicators@ubuntu.com",         # Ubuntu specific extension
                "appindicator@vroad.xyz"                   # Alternative extension
            ]
            
            has_appindicator_extension = any(ext_id in output for ext_id in extension_ids)
            
            if has_appindicator_extension:
                logger.info(f"Detected GNOME AppIndicator extension: {output}")
    except Exception as e:
        logger.debug(f"Error checking GNOME extensions: {e}")
    
    return {
        'desktop': desktop_env,
        'session': session_type,
        'has_appindicator': has_appindicator_extension
    }

# Determine if we can use AppIndicator
USE_APP_INDICATOR = False
env_info = detect_environment()
try:
    import gi
    gi.require_version('Gtk', '3.0')
    
    # First check if we have the extension enabled for GNOME
    if 'GNOME' in env_info['desktop'] and not env_info['has_appindicator']:
        logger.warning("GNOME detected but AppIndicator extension is not enabled.")
        logger.warning("Using fallback system tray implementation.")
        raise ImportError("AppIndicator extension not enabled in GNOME")
    
    # Try to load AppIndicator3
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import Gtk, AppIndicator3, GLib
    USE_APP_INDICATOR = True
    logger.info(f"Using AppIndicator for Linux system tray ({env_info['desktop']})")
except (ImportError, ValueError) as e:
    logger.warning(f"AppIndicator not available: {e}, falling back to pystray")
    try:
        import pystray
        from plyer import notification
        logger.info("Successfully loaded pystray as fallback")
    except ImportError as e2:
        logger.error(f"Failed to load pystray: {e2}. System tray functionality may be limited.")
    USE_APP_INDICATOR = False

# Special handling for Ubuntu Unity/GNOME without AppIndicator
if not USE_APP_INDICATOR and ('Unity' in env_info['desktop'] or 'GNOME' in env_info['desktop']):
    logger.warning("Ubuntu GNOME/Unity detected without AppIndicator support.")
    logger.warning("You may need to install 'gnome-shell-extension-appindicator' and enable it.")
    logger.warning("Install with: sudo apt install gnome-shell-extension-appindicator")
    logger.warning("Then enable in GNOME Extensions app or at https://extensions.gnome.org/")

class AppIndicatorTray:
    """AppIndicator implementation for Linux system tray"""
    
    def __init__(self, app):
        self.app = app
        self.indicator = None
        self.menu = None
        self.setup_indicator()
        
    def setup_indicator(self):
        """Set up the AppIndicator with an initial icon"""
        try:
            icon_path = self.app._get_icon_path(self.app.status)
            if not icon_path:
                # Use a system icon as fallback
                icon_path = "dialog-information"
                
            self.indicator = AppIndicator3.Indicator.new(
                "simkl-mps",
                icon_path,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            
            # Create the initial menu
            self.update_menu()
            
            logger.info("AppIndicator setup successful")
        except Exception as e:
            logger.error(f"Error setting up AppIndicator: {e}")
            raise
    
    def update_menu(self):
        """Update the AppIndicator menu"""
        try:
            menu = Gtk.Menu()
            
            # Add title item (non-clickable)
            title_item = Gtk.MenuItem(label="^_^ MPS for SIMKL")
            title_item.set_sensitive(False)
            menu.append(title_item)
            
            # Add separator
            menu.append(Gtk.SeparatorMenuItem())
            
            # Add status item
            status_text = self.app.get_status_text()
            status_item = Gtk.MenuItem(label=f"Status: {status_text}")
            status_item.set_sensitive(False)
            menu.append(status_item)
            
            # Add separator
            menu.append(Gtk.SeparatorMenuItem())
            
            # Add Start/Stop monitoring item
            if self.app.status == "running":
                stop_item = Gtk.MenuItem(label="Stop Monitoring")
                stop_item.connect("activate", self._wrap_callback(self.app.stop_monitoring))
                menu.append(stop_item)
            else:
                start_item = Gtk.MenuItem(label="Start Monitoring")
                start_item.connect("activate", self._wrap_callback(self.app.start_monitoring))
                menu.append(start_item)
            
            # Add separator
            menu.append(Gtk.SeparatorMenuItem())
            
            # Tools submenu
            tools_item = Gtk.MenuItem(label="Tools")
            tools_submenu = Gtk.Menu()
            
            logs_item = Gtk.MenuItem(label="Open Logs")
            logs_item.connect("activate", self._wrap_callback(self.app.open_logs))
            tools_submenu.append(logs_item)
            
            config_item = Gtk.MenuItem(label="Open Config Directory")
            config_item.connect("activate", self._wrap_callback(self.app.open_config_dir))
            tools_submenu.append(config_item)
            
            backlog_item = Gtk.MenuItem(label="Process Backlog Now")
            backlog_item.connect("activate", self._wrap_callback(self.app.process_backlog))
            tools_submenu.append(backlog_item)
            
            tools_item.set_submenu(tools_submenu)
            menu.append(tools_item)
            
            # Online Services submenu
            services_item = Gtk.MenuItem(label="Online Services")
            services_submenu = Gtk.Menu()
            
            simkl_item = Gtk.MenuItem(label="SIMKL Website")
            simkl_item.connect("activate", self._wrap_callback(self.app.open_simkl))
            services_submenu.append(simkl_item)
            
            history_item = Gtk.MenuItem(label="View Watch History")
            history_item.connect("activate", self._wrap_callback(self.app.open_simkl_history))
            services_submenu.append(history_item)
            
            services_item.set_submenu(services_submenu)
            menu.append(services_item)
            
            # Add separator
            menu.append(Gtk.SeparatorMenuItem())
            
            # Check for updates
            update_item = Gtk.MenuItem(label="Check for Updates")
            update_item.connect("activate", self._wrap_callback(self.app.check_updates_thread))
            menu.append(update_item)
            
            # About
            about_item = Gtk.MenuItem(label="About")
            about_item.connect("activate", self._wrap_callback(self.app.show_about))
            menu.append(about_item)
            
            # Help
            help_item = Gtk.MenuItem(label="Help")
            help_item.connect("activate", self._wrap_callback(self.app.show_help))
            menu.append(help_item)
            
            # Exit
            exit_item = Gtk.MenuItem(label="Exit")
            exit_item.connect("activate", self._wrap_callback(self.app.exit_app))
            menu.append(exit_item)
            
            menu.show_all()
            self.indicator.set_menu(menu)
            self.menu = menu
            
        except Exception as e:
            logger.error(f"Error updating AppIndicator menu: {e}")
    
    def _wrap_callback(self, callback):
        """Wrap TrayApp callbacks to be used with GTK"""
        def wrapped_callback(*args):
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in AppIndicator callback: {e}")
        return wrapped_callback
    
    def update_icon(self, icon_path=None):
        """Update the AppIndicator icon"""
        try:
            if not icon_path:
                # Get the appropriate icon based on status
                icon_path = self.app._get_icon_path(self.app.status)
            
            if icon_path:
                self.indicator.set_icon_full(icon_path, f"MPS for SIMKL - {self.app.status}")
            
            # Update menu text
            self.update_menu()
            
        except Exception as e:
            logger.error(f"Error updating AppIndicator icon: {e}")
    
    def run(self):
        """Run the GTK main loop"""
        try:
            Gtk.main()
        except Exception as e:
            logger.error(f"Error in GTK main loop: {e}")
    
    def stop(self):
        """Stop the GTK main loop"""
        try:
            Gtk.main_quit()
        except Exception as e:
            logger.error(f"Error stopping GTK main loop: {e}")


class TrayApp(TrayAppBase):
    """Linux system tray application for simkl-mps"""
    
    def __init__(self):
        super().__init__()
        
        # Set up the appropriate tray implementation based on availability
        if USE_APP_INDICATOR:
            self.indicator_tray = AppIndicatorTray(self)
            self.using_appindicator = True
            self.tray_icon = None
        else:
            self.using_appindicator = False
            self.tray_icon = None
            self.setup_icon()
    
    def setup_icon(self):
        """Setup the system tray icon using pystray"""
        if self.using_appindicator:
            return
            
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
        """Load the appropriate icon for the current status"""
        try:
            # Try multiple icon formats and fallbacks
            icon_format = "png"  # PNG is preferred on Linux
            
            # First try to find high-resolution icons
            sizes = [128, 64, 32]
            for size in sizes:
                status_icon = self.assets_dir / f"simkl-mps-{self.status}-{size}.{icon_format}"
                if status_icon.exists():
                    logger.info(f"Using high-res status icon: {status_icon}")
                    return Image.open(status_icon)
                    
                generic_icon = self.assets_dir / f"simkl-mps-{size}.{icon_format}"
                if generic_icon.exists():
                    logger.info(f"Using high-res generic icon: {generic_icon}")
                    return Image.open(generic_icon)
            
            # List of possible icon files to check in order of preference
            icon_paths = [
                # Status-specific icons
                self.assets_dir / f"simkl-mps-{self.status}.{icon_format}",
                self.assets_dir / f"simkl-mps-{self.status}.ico",  # ICO fallback
                
                # Generic icons
                self.assets_dir / f"simkl-mps.{icon_format}",
                self.assets_dir / f"simkl-mps.ico",   # ICO fallback
                
                # Look in parent directory as well (common issue in some package setups)
                Path(self.assets_dir).parent / f"simkl-mps.{icon_format}",
                Path(self.assets_dir).parent / f"simkl-mps.ico"
            ]
            
            # Verbose logging to help debug icon loading issues
            logger.debug(f"Looking for icon files in: {self.assets_dir}")
            for path in icon_paths:
                logger.debug(f"Checking for icon at: {path}")
                if path.exists():
                    logger.info(f"Found and loading tray icon: {path}")
                    return Image.open(path)
            
            logger.error(f"No suitable icon found in assets directory: {self.assets_dir}")
            logger.error(f"Expected one of: {[p.name for p in icon_paths]}")
            logger.info("Creating fallback icon...")
            return self._create_fallback_image(size=128)
                
        except FileNotFoundError as e:
            logger.error(f"Icon file not found: {e}", exc_info=True)
            logger.info("Creating fallback icon after FileNotFoundError...")
            return self._create_fallback_image(size=128)
        except Exception as e:
            logger.error(f"Error loading status icon: {e}", exc_info=True)
            logger.info("Creating fallback icon after Exception...")
            return self._create_fallback_image(size=128)

    def create_menu(self):
        """Create the system tray menu with a professional layout"""
        # This is used only for pystray implementation
        if self.using_appindicator:
            return None
            
        # Start with basic items
        menu_items = [
            pystray.MenuItem("^_^ MPS for SIMKL", None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Status: {self.get_status_text()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]

        # Add Start/Stop item
        if self.status == "running":
            # If running, show "Stop"
            menu_items.append(pystray.MenuItem("Stop Monitoring", self.stop_monitoring))
        elif self.status == "stopped" or self.status == "error" or self.status == "paused":
            # If stopped, paused, or error, show "Start"
            menu_items.append(pystray.MenuItem("Start Monitoring", self.start_monitoring))

        # Add Tools submenu
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Tools", pystray.Menu(
            pystray.MenuItem("Open Logs", self.open_logs),
            pystray.MenuItem("Open Config Directory", self.open_config_dir),
            pystray.MenuItem("Process Backlog Now", self.process_backlog),
        )))

        # Add Online Services submenu
        menu_items.append(pystray.MenuItem("Online Services", pystray.Menu(
            pystray.MenuItem("SIMKL Website", self.open_simkl),
            pystray.MenuItem("View Watch History", self.open_simkl_history),
        )))
        menu_items.append(pystray.Menu.SEPARATOR)

        # Always show "Check for Updates"
        menu_items.append(
            pystray.MenuItem(
                "Check for Updates",
                self.check_updates_thread
            )
        )

        # Add final items
        menu_items.append(pystray.MenuItem("About", self.show_about))
        menu_items.append(pystray.MenuItem("Help", self.show_help))
        menu_items.append(pystray.MenuItem("Exit", self.exit_app))

        return pystray.Menu(*menu_items)

    def update_icon(self):
        """Update the tray icon and menu to reflect the current status"""
        if self.using_appindicator:
            try:
                icon_path = self._get_icon_path(self.status)
                self.indicator_tray.update_icon(icon_path)
                logger.debug(f"Updated AppIndicator icon to status: {self.status}")
            except Exception as e:
                logger.error(f"Failed to update AppIndicator icon: {e}", exc_info=True)
        elif self.tray_icon:
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
        """Check if this is the first time the app is being run"""
        try:
            # For Linux, check for a first-run marker file
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
        """Show a desktop notification with Linux-specific methods"""
        logger.debug(f"Showing Linux notification: {title} - {message}")
        
        try:
            # Try notify-send (most standard method)
            try:
                subprocess.run(['notify-send', title, message], check=False)
                logger.debug("Linux notification sent via notify-send")
                return
            except (FileNotFoundError, subprocess.SubprocessError) as e:
                logger.debug(f"notify-send failed: {e}")
            
            # Try using zenity
            try:
                subprocess.Popen(['zenity', '--notification', '--text', f"{title}: {message}"])
                logger.debug("Linux notification sent via zenity")
                return
            except (FileNotFoundError, subprocess.SubprocessError) as e:
                logger.debug(f"zenity failed: {e}")
                
            # If AppIndicator is available, try using GTK notification
            if self.using_appindicator:
                try:
                    from gi.repository import Notify
                    if not Notify.is_initted():
                        Notify.init("simkl-mps")
                    
                    notification = Notify.Notification.new(title, message, None)
                    notification.show()
                    logger.debug("Linux notification sent via libnotify")
                    return
                except Exception as e:
                    logger.debug(f"GTK notification failed: {e}")
            
            # Try plyer as a fallback
            try:
                from plyer import notification as plyer_notification
                plyer_notification.notify(
                    title=title,
                    message=message,
                    app_name="MPS for SIMKL",
                    timeout=10
                )
                logger.debug("Linux notification sent via plyer")
                return
            except Exception as e:
                logger.debug(f"plyer notification failed: {e}")
                
        except Exception as e:
            logger.error(f"All Linux notification methods failed: {e}")
        
        # Final fallback: Print to console
        print(f"\n🔔 NOTIFICATION: {title}\n{message}\n")
        logger.info(f"Notification displayed in console: {title} - {message}")

    def show_about(self, _=None):
        """Show about dialog with Linux-specific implementation"""
        try:
            # Try to get version information
            version = "Unknown"
            
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

            # Try using zenity for a nicer dialog
            try:
                subprocess.run([
                    'zenity', '--info', 
                    '--title=About MPS for SIMKL', 
                    f'--text={about_text}'
                ])
                return 0
            except:
                pass
                
            # Try using GTK if AppIndicator is available
            if self.using_appindicator:
                try:
                    from gi.repository import Gtk
                    
                    dialog = Gtk.MessageDialog(
                        None, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                        "Media Player Scrobbler for SIMKL"
                    )
                    dialog.format_secondary_text(about_text)
                    dialog.set_title("About")
                    dialog.run()
                    dialog.destroy()
                    return 0
                except:
                    pass
                    
            # Fallback to notification
            self.show_notification("About MPS for SIMKL", about_text)
                
        except Exception as e:
            logger.error(f"Error showing about dialog: {e}")
            self.show_notification("About", "Media Player Scrobbler for SIMKL")
        return 0

    def show_help(self, _=None):
        """Show help information with Linux-specific implementation"""
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
            
        if self.using_appindicator:
            self.indicator_tray.stop()
        else:
            self.tray_icon.stop()
        return 0

    def run(self):
        """Run the tray application"""
        logger.info("Starting Media Player Scrobbler for SIMKL in tray mode")
        
        # Initialize the scrobbler
        self.scrobbler = get_simkl_scrobbler()()
        initialized = self.scrobbler.initialize()
        
        if initialized:
            # Start monitoring if initialization was successful
            started = self.start_monitoring()
            if not started:
                self.update_status("error", "Failed to start monitoring")
        else:
            self.update_status("error", "Failed to initialize")
        
        # Run the appropriate tray implementation
        try:
            if self.using_appindicator:
                logger.info("Running with AppIndicator (Ubuntu/GNOME)")
                self.indicator_tray.run()
            else:
                logger.info("Running with standard system tray (pystray)")
                self.tray_icon.run()
        except Exception as e:
            logger.error(f"Error running tray icon: {e}")
            self.show_notification("Tray Error", f"Error with system tray: {e}")
            
            # Fallback to console mode if tray fails
            try:
                print("\nSystem tray failed. Running in console mode instead.")
                print("Press Ctrl+C to exit.")
                while self.scrobbler and self.monitoring_active:
                    time.sleep(1)
            except KeyboardInterrupt:
                if self.monitoring_active:
                    self.stop_monitoring()
                    print("Monitoring stopped.")

    def check_updates_thread(self, _=None):
        """Wrapper to run the update check logic in a separate thread"""
        # Prevent multiple checks running simultaneously
        if hasattr(self, '_update_check_running') and self._update_check_running:
            logger.warning("Update check already in progress.")
            return
        self._update_check_running = True
        threading.Thread(target=self._check_updates_logic, daemon=True).start()

    def _check_updates_logic(self):
        """Check for updates using the bash updater script"""
        import subprocess
        
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
            # Use --CheckOnly flag for the new script to just check without installing
            command = ["bash", str(updater_path), "--CheckOnly"]
            
            # Make sure the script is executable
            try:
                os.chmod(str(updater_path), 0o755)
                logger.debug(f"Made updater script executable: {updater_path}")
            except Exception as e:
                logger.warning(f"Could not set executable permission on updater script: {e}")

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
                # Look for specific output patterns from the new script
                if "UPDATE_AVAILABLE:" in stdout:
                    # Extract version and URL using regex to be more robust
                    import re
                    version_match = re.search(r"UPDATE_AVAILABLE: ([0-9.]+) (https?://[^\s]+)", stdout)
                    if version_match:
                        version = version_match.group(1)
                        url = version_match.group(2)
                        logger.info(f"Update found: Version {version}")
                        
                        # Ask if the user wants to install the update
                        self.show_notification("Update Available", f"Version {version} is available.")
                        
                        # Use zenity if available for a better dialog
                        if self._ask_user_to_update(version):
                            # User wants to update - run the updater again without --CheckOnly
                            logger.info("User confirmed update, installing...")
                            self._run_update_installation()
                        else:
                            logger.info("User declined update")
                    else:
                        logger.error(f"Could not parse UPDATE_AVAILABLE string: {stdout}")
                        self.show_notification("Update Available", "An update is available. Use pip to update: pip install --upgrade simkl-mps[linux]")
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
        """Ask the user if they want to update to the new version"""
        try:
            # Try using zenity for a nice dialog (most Linux distros with GUI)
            if subprocess.run(['which', 'zenity'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
                result = subprocess.run([
                    'zenity', '--question',
                    '--title=Update Available',
                    f'--text=Version {version} is available. Do you want to update now?',
                    '--no-wrap'
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return result.returncode == 0
            else:
                # Fallback to notification + timer approach
                self.show_notification("Update Available", f"Version {version} is available. Updating in 10 seconds. Close this app to cancel.")
                # Wait 10 seconds to give user chance to cancel
                for i in range(10, 0, -1):
                    logger.debug(f"Update countdown: {i} seconds remaining")
                    time.sleep(1)
                return True
        except Exception as e:
            logger.error(f"Error asking for update confirmation: {e}")
            # Default to not updating in case of error
            return False
    
    def _run_update_installation(self):
        """Run the actual update installation"""
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