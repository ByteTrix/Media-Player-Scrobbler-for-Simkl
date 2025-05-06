"""
Windows-specific System tray implementation for Media Player Scrobbler for SIMKL.
Uses pystray and tkinter for the UI elements.
"""

import os
import sys
import time
import threading
import logging
import webbrowser
import subprocess # Added for running updater script
from pathlib import Path
from PIL import Image # Keep PIL.Image for loading
import pystray
from plyer import notification
import ctypes # Added for native Windows dialogs
import tkinter as tk
from tkinter import simpledialog, messagebox # Keep messagebox for about/help fallbacks

# Import Base Class and common functions/constants
from simkl_mps.tray_base import TrayAppBase, get_simkl_scrobbler
from simkl_mps.config_manager import get_setting, DEFAULT_THRESHOLD # Keep for menu state check
from simkl_mps.main import APP_DATA_DIR # Keep for log/config paths

logger = logging.getLogger(__name__)


class TrayAppWin(TrayAppBase):
    """Windows System tray application for simkl-mps using pystray"""

    def __init__(self):
        super().__init__() # Call base class constructor
        self.tray_icon = None # Initialize tray_icon attribute
        self._update_check_running = False # Initialize update check flag
        self._setup_auto_update_if_needed() # Run platform-specific setup
        self.setup_icon()

    def setup_icon(self):
        """Setup the pystray system tray icon"""
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
            # Log exception type and full traceback for better debugging
            logger.error(f"Error setting up tray icon: {type(e).__name__} - {e}", exc_info=True)
            raise
    
    def load_icon_for_status(self):
        """Load the appropriate icon PIL.Image for the current status using the base class path finder."""
        icon_path_str = self._get_icon_path(status=self.status) # Use base class method

        if icon_path_str:
            try:
                icon_path = Path(icon_path_str)
                if icon_path.exists():
                    logger.debug(f"Loading tray icon from base path: {icon_path}")
                    # Ensure the image is loaded correctly, especially for ICO on Windows
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
    
    # _create_fallback_image is now in base class

    # get_status_text is now in base class

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

    # open_config_dir is now in base class

    def show_about(self, _=None):
        """Show application information using Tkinter"""
        try:
            # Try multiple ways to get the version information
            version = "Unknown"
            
            # 1. Try to get from pkg_resources
            try:
                import pkg_resources
                version = pkg_resources.get_distribution("simkl-mps").version
            except (pkg_resources.DistributionNotFound, ImportError):
                # 2. Try to get from registry (Windows) - Removed version.txt check
                if version == "Unknown" and sys.platform == 'win32':
                    try:
                        import winreg
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\kavinthangavel\Media Player Scrobbler for SIMKL")
                        version = winreg.QueryValueEx(key, "Version")[0]
                        winreg.CloseKey(key)
                    except:
                        pass
            
            # Get license information
            license_name = "GNU GPL v3"
            try:
                if sys.platform == 'win32':
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\kavinthangavel\Media Player Scrobbler for SIMKL")
                    license_name = winreg.QueryValueEx(key, "License")[0]
                    winreg.CloseKey(key)
            except:
                pass
            
            # Build the about text with the version and license
            about_text = f"""Media Player Scrobbler for SIMKL
Version: {version}
Author: kavinthangavel
License: {license_name}

Automatically track and scrobble your media to SIMKL."""

            # Use tkinter on Windows with proper event handling
            def show_dialog():
                dialog_root = tk.Tk()
                dialog_root.withdraw()
                dialog_root.attributes("-topmost", True)  # Keep dialog on top

                # Add protocol handler for window close button
                dialog_root.protocol("WM_DELETE_WINDOW", dialog_root.destroy)

                # Show the dialog and wait for it to complete
                messagebox.showinfo("About", about_text, parent=dialog_root)

                # Clean up
                dialog_root.destroy()

            # Run in a separate thread to avoid blocking the main thread
            threading.Thread(target=show_dialog, daemon=True).start()

        except Exception as e:
            logger.error(f"Error showing about dialog: {e}")
            self.show_notification("About", "Media Player Scrobbler for SIMKL")
        return 0

    def show_help(self, _=None):
        """Show help information using Tkinter as fallback"""
        try:
            # Open documentation or show help dialog
            help_url = "https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/wiki"
            webbrowser.open(help_url)
        except Exception as e:
            logger.error(f"Error showing help: {e}")
            
            # Fallback help text if browser doesn't open
            help_text = """Media Player Scrobbler for SIMKL

This application automatically tracks what you watch in supported media players and updates your SIMKL account.

Supported players:
- VLC
- MPV
- MPC-HC

Tips:
- Make sure you've authorized with SIMKL
- The app runs in your system tray
- Check logs if you encounter problems"""
            
            # Show help text in a Tkinter dialog as a fallback
            def show_dialog():
                dialog_root = tk.Tk()
                dialog_root.withdraw()
                dialog_root.attributes("-topmost", True)

                # Add protocol handler for window close button
                dialog_root.protocol("WM_DELETE_WINDOW", dialog_root.destroy)

                # Show the dialog and wait for it to complete
                messagebox.showinfo("Help", help_text, parent=dialog_root)

                # Clean up
                dialog_root.destroy()

            # Run in a separate thread to avoid blocking the main thread
            threading.Thread(target=show_dialog, daemon=True).start()
        return 0

    # open_simkl is now in base class
    # open_simkl_history is now in base class

    def check_updates_thread(self, _=None):
        """Wrapper to run the Windows update check logic in a separate thread"""
        # Prevent multiple checks running simultaneously
        if hasattr(self, '_update_check_running') and self._update_check_running:
            logger.warning("Update check already in progress.")
            return
        self._update_check_running = True
        threading.Thread(target=self._check_updates_logic, daemon=True).start()

    def _check_updates_logic(self):
        """Check for updates using the PowerShell script (Windows specific)"""
        logger.info("Checking for updates...")
        self.show_notification("Checking for Updates", "Looking for updates to MPS for SIMKL...")

        # Get current version first
        current_version = "Unknown"
        try:
            # 1. Try to get from pkg_resources
            try:
                import pkg_resources
                current_version = pkg_resources.get_distribution("simkl-mps").version
            except (pkg_resources.DistributionNotFound, ImportError):
                # 2. Try to get from registry (Windows)
                if sys.platform == 'win32':
                    try:
                        import winreg
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\kavinthangavel\Media Player Scrobbler for SIMKL")
                        current_version = winreg.QueryValueEx(key, "Version")[0]
                        winreg.CloseKey(key)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Error getting current version: {e}")

        system = sys.platform.lower()
        updater_script = 'updater.ps1' if system == 'win32' else 'updater.sh' # Adapt for other OS if needed
        updater_path = self._get_updater_path(updater_script)

        if not updater_path or not updater_path.exists():
            logger.error(f"Updater script not found: {updater_path}")
            self.show_notification("Update Error", "Updater script not found.")
            self.update_icon() # Refresh menu
            self._update_check_running = False
            return

        try:
            if system == 'win32':
                # Add -Silent parameter to prevent the updater from showing its own notifications
                command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(updater_path), "-CheckOnly", "-Silent"]
                # Hide PowerShell window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0 # SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                # Basic command for sh script (adapt if needed)
                command = ["bash", str(updater_path), "--check-only", "--silent"] # Assuming sh script supports --silent
                startupinfo = None
                creationflags = 0

            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False, # Don't raise exception on non-zero exit code
                startupinfo=startupinfo,
                creationflags=creationflags,
                encoding='utf-8' # Ensure correct decoding
            )

            stdout = process.stdout.strip()
            stderr = process.stderr.strip()
            exit_code = process.returncode

            logger.info(f"Update check script exited with code: {exit_code}")
            logger.debug(f"Update check stdout: {stdout}")
            if stderr:
                logger.error(f"Update check stderr: {stderr}")

            # Process based on exit code first
            if exit_code != 0:
                 # Exit code 1 from PS script means check failed
                if exit_code == 1 and system == 'win32':
                    logger.error("Update check failed (script exit code 1).")
                    self.show_notification("Update Check Failed", "Could not check for updates. Please try again later or check logs.")
                else:
                    # General script execution error
                    logger.error(f"Update check script failed with exit code {exit_code}. Stderr: {stderr}")
                    self.show_notification("Update Error", f"Failed to run update check script (Code: {exit_code}).")

            # Process stdout if exit code was 0
            elif stdout.startswith("UPDATE_AVAILABLE:"):
                try:
                    parts = stdout.split(" ", 2) # UPDATE_AVAILABLE: <version> <url>
                    new_version = parts[1]
                    url = parts[2]
                    logger.info(f"Update found: Version {new_version}")
                    
                    # First show notification that update is available with both versions
                    self.show_notification("Update Available", 
                        f"New version available!\nCurrent: {current_version}\nNew: {new_version}\n\nOpening download page...")
                    
                    # Short delay to ensure notification appears before browser opens
                    time.sleep(1)
                    
                    # Then open the release page automatically
                    webbrowser.open(url)
                    
                except IndexError:
                    logger.error(f"Could not parse UPDATE_AVAILABLE string: {stdout}")
                    self.show_notification("Update Error", "Failed to parse update information.")
            elif stdout.startswith("NO_UPDATE:"):
                try:
                    version = stdout.split(" ", 1)[1]
                    logger.info(f"No update available. Current version: {version}")
                    self.show_notification("No Updates Available", f"You are already running the latest version ({version}).")
                except IndexError:
                     logger.error(f"Could not parse NO_UPDATE string: {stdout}")
                     self.show_notification("No Updates Available", "You are already running the latest version.")
            else:
                # Unexpected output
                logger.warning(f"Unexpected output from update check script: {stdout}")
                self.show_notification("Update Check Info", "Update check completed with unclear results. Check logs.")

        except FileNotFoundError:
             logger.error(f"Error running update check: Command not found (powershell/bash?).")
             self.show_notification("Update Error", "Required command (powershell/bash) not found.")
        except Exception as e:
            logger.error(f"Error during update check: {e}", exc_info=True)
            self.show_notification("Update Error", f"An error occurred during update check: {e}")
        finally:
            self.update_icon() # Refresh menu state
            self._update_check_running = False

    # _get_updater_path is now in base class
    # _get_icon_path is now in base class

    def show_notification(self, title, message):
        """Show a desktop notification using winotify (persistent) or plyer as fallback on Windows, with cross-platform support."""
        logger.debug(f"Attempting to show notification: {title} - {message}")
        
        # Try winotify for persistent Action Center notifications
        if sys.platform == 'win32':
            try:
                from winotify import Notification
                # icon_path = self._get_icon_path(self.status)  # Use the same icon logic as tray
                toast = Notification(
                    app_id="kavinthangavel.simkl-mps",  # Must match AppUserModelID in installer
                    title=title,
                    msg=message,
                    # icon=icon_path if icon_path else None
                )
                toast.show()
                logger.debug("Notification sent via winotify with AppUserModelID and icon")
                return
            except ImportError:
                logger.info("winotify not installed, falling back to plyer/other methods.")
            except Exception as e:
                logger.warning(f"winotify notification failed: {e}")
        
        # Fallback: plyer (not persistent in Action Center)
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="MPS for SIMKL",
                timeout=10
            )
            logger.debug("Icon-less notification sent successfully via plyer")
            return
        except Exception as plyer_err:
            logger.warning(f"Basic notification failed: {plyer_err}")
        
        # Fallback: PowerShell or Windows Forms
        try:
            if sys.platform == 'win32':
                # Windows: Try PowerShell with no icon references
                try:
                    import subprocess
                    script = f'''
                    Add-Type -AssemblyName System.Windows.Forms
                    $notification = New-Object System.Windows.Forms.NotifyIcon
                    $notification.Text = "MPS for SIMKL"
                    $notification.Visible = $true
                    $notification.BalloonTipTitle = "{title}"
                    $notification.BalloonTipText = "{message}"
                    $notification.ShowBalloonTip(10000)
                    Start-Sleep -Seconds 5
                    $notification.Dispose()
                    '''
                    with open("temp_notify.ps1", "w") as f:
                        f.write(script)
                    subprocess.Popen(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", "temp_notify.ps1"],
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    logger.debug("Windows System.Windows.Forms notification sent")
                    return
                except Exception as win_err:
                    logger.warning(f"Alternative Windows notification failed: {win_err}")
                # Windows MessageBox fallback
                try:
                    import ctypes
                    MessageBox = ctypes.windll.user32.MessageBoxW
                    MB_ICONINFORMATION = 0x40
                    MessageBox(None, message, title, MB_ICONINFORMATION)
                    logger.debug("Windows MessageBox notification shown")
                    return
                except Exception as mb_err:
                    logger.warning(f"Windows MessageBox notification failed: {mb_err}")
        except Exception as native_err:
            logger.error(f"All native notification methods failed: {native_err}")
        
        # Final fallback: Print to console
        print(f"\n🔔 NOTIFICATION: {title}\n{message}\n")
        logger.info(f"Notification displayed in console: {title} - {message}")
        return 0

    def run(self):
        """Run the pystray application"""
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

    # start_monitoring is now in base class
    # stop_monitoring is now in base class
    # process_backlog is now in base class
    # open_logs is now in base class

    # --- Watch Threshold Implementation ---

    def _ask_custom_threshold_dialog(self, current_threshold: int) -> int | None:
        """Implementation of the abstract method to ask for threshold using Tkinter."""
        dialog_root = None
        try:
            # We need a hidden root window for the dialog to work correctly,
            # especially when run without a pre-existing Tkinter main loop.
            dialog_root = tk.Tk()
            dialog_root.withdraw() # Hide the root window
            dialog_root.attributes("-topmost", True) # Keep dialog on top
            dialog_root.focus_force() # Try to bring focus

            threshold = simpledialog.askinteger(
                "Set Watch Threshold",
                f"Enter watch completion threshold (%):\n(Current: {current_threshold}%)",
                parent=dialog_root, # Associate with hidden root
                minvalue=1,
                maxvalue=100,
                initialvalue=current_threshold
            )
            return threshold # Returns the integer or None if cancelled
        except (tk.TclError, ValueError, Exception) as e:
            logger.error(f"Error showing Tkinter threshold dialog: {e}", exc_info=True)
            return None # Return None on any error
        finally:
            # Ensure the hidden root window is destroyed after the dialog closes
            if dialog_root:
                try:
                    # Schedule the destroy call in the Tkinter event loop
                    dialog_root.after(0, dialog_root.destroy)
                except Exception as e:
                    logger.debug(f"Error destroying Tkinter root (might be already closed): {e}")

    # _set_preset_threshold is now in base class
    # set_custom_watch_threshold is now in base class

    # --- End Watch Threshold Implementation ---

    def exit_app(self, _=None):
        """Exit the pystray application"""
        logger.info("Exiting application from tray")
        if self.monitoring_active:
            self.stop_monitoring()
        if self.tray_icon:
            self.tray_icon.stop()
        return 0

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
                            def show_auto_update_dialog():
                                dialog_root = tk.Tk()
                                dialog_root.withdraw()
                                dialog_root.attributes("-topmost", True)
                                
                                # Add protocol handler for window close button
                                dialog_root.protocol("WM_DELETE_WINDOW", lambda: dialog_root.destroy())
                                
                                # Ask user about enabling auto-updates
                                result = messagebox.askyesno(
                                    "MPSS Auto-Update", 
                                    "Would you like to enable weekly automatic update checks?",
                                    parent=dialog_root
                                )
                                
                                # Process the result before destroying the root
                                if result:
                                    # Run the setup script
                                    subprocess.run(['bash', str(setup_script_path)])
                                
                                # Ensure dialog is destroyed
                                dialog_root.destroy()
                            
                            # Run dialog in a separate thread to avoid blocking
                            dialog_thread = threading.Thread(target=show_auto_update_dialog, daemon=True)
                            dialog_thread.start()
                            dialog_thread.join(timeout=10)  # Wait for dialog with timeout
                
                # Remove the first_run file regardless of outcome
                first_run_file.unlink(missing_ok=True)
        
        except Exception as e:
            logger.error(f"Error setting up auto-updates: {e}")

    # _setup_auto_update_if_needed remains platform-specific for now

    def check_first_run(self):
        """Windows-specific check for first run using registry"""
        try:
            # Create a registry key to track app states on Windows
            if sys.platform == 'win32':
                import winreg
                try:
                    # Try to open the registry key
                    registry_path = r"Software\kavinthangavel\Media Player Scrobbler for SIMKL"
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, 
                                        winreg.KEY_READ | winreg.KEY_WRITE)
                    
                    # Check if this is the first run
                    try:
                        # If we can read the FirstRun value, it's not the first run
                        first_run = winreg.QueryValueEx(key, "FirstRun")[0]
                        self.is_first_run = False
                    except FileNotFoundError:
                        # If FirstRun value doesn't exist, this is the first run
                        self.is_first_run = True
                        winreg.SetValueEx(key, "FirstRun", 0, winreg.REG_DWORD, 1)
                    except WindowsError:
                        # If there's any other error, assume it's not first run
                        self.is_first_run = False
                        
                    winreg.CloseKey(key)
                    
                except FileNotFoundError:
                    # If the key doesn't exist, create it and mark as first run
                    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry_path)
                    winreg.SetValueEx(key, "FirstRun", 0, winreg.REG_DWORD, 1)
                    winreg.CloseKey(key)
                    self.is_first_run = True
                except Exception as e:
                    logger.warning(f"Error checking first run status in registry: {e}")
                    # Assume not first run on error
                    self.is_first_run = False
            
            logger.debug(f"First run check result: {self.is_first_run}")
            
        except Exception as e:
            logger.error(f"Unexpected error in first run check: {e}")
            self.is_first_run = False  # Default to not showing the notification on error

def run_tray_app():
    """Run the Windows tray application"""
    try:
        app = TrayAppWin()
        app.run()
    except Exception as e:
        # Log the full traceback for critical startup errors
        logger.error(f"Critical error preventing tray app startup: {type(e).__name__} - {e}", exc_info=True)
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
