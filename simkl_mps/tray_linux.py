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
import re
from pathlib import Path
from PIL import Image

from typing import Any, Optional, cast

from simkl_mps.tray_base import TrayAppBase, get_simkl_scrobbler, logger
from simkl_mps.config_manager import get_setting, DEFAULT_THRESHOLD, DEFAULT_MIN_REWATCH_WATCH_SECONDS # Import for menu state and dialog

Gtk: Any = None
AppIndicator3: Any = None
GLib: Any = None
pystray: Any = cast(Any, None)

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
    import gi  # type: ignore[import]
    gi.require_version('Gtk', '3.0')
    
    # First check if we have the extension enabled for GNOME
    if 'GNOME' in env_info['desktop'] and not env_info['has_appindicator']:
        logger.warning("GNOME detected but AppIndicator extension is not enabled.")
        logger.warning("Using fallback system tray implementation.")
        raise ImportError("AppIndicator extension not enabled in GNOME")
    
    # Try to load AppIndicator3
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import Gtk as GtkModule, AppIndicator3 as AppIndicatorModule, GLib as GLibModule  # type: ignore[import]
    Gtk = cast(Any, GtkModule)
    AppIndicator3 = cast(Any, AppIndicatorModule)
    GLib = cast(Any, GLibModule)
    USE_APP_INDICATOR = True
    logger.info(f"Using AppIndicator for Linux system tray ({env_info['desktop']})")
except (ImportError, ValueError) as e:
    logger.warning(f"AppIndicator not available: {e}, falling back to pystray")
    try:
        import pystray as pystray_module
        pystray = cast(Any, pystray_module)
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
        self.indicator: Any = cast(Any, None)
        self.menu: Any = cast(Any, None)
        self.setup_indicator()
        
    def setup_indicator(self):
        """Set up the AppIndicator with an initial icon"""
        try:
            icon_path = self.app._get_icon_path(self.app.status)
            if not icon_path:
                # Use a system icon as fallback
                icon_path = "dialog-information"
                
            indicator_class = cast(Any, AppIndicator3)
            self.indicator = indicator_class.Indicator.new(
                "simkl-mps",
                icon_path,
                indicator_class.IndicatorCategory.APPLICATION_STATUS
            )
            indicator_obj = cast(Any, self.indicator)
            indicator_obj.set_status(indicator_class.IndicatorStatus.ACTIVE)
            
            # Create the initial menu
            self.update_menu()
            
            logger.info("AppIndicator setup successful")
        except Exception as e:
            logger.error(f"Error setting up AppIndicator: {e}")
            raise
    
    def update_menu(self):
        """Update the AppIndicator menu"""
        try:
            gtk_module = cast(Any, Gtk)
            menu = gtk_module.Menu()
            self.app._refresh_auth_state()
            
            # Add title item (non-clickable)
            title_item = gtk_module.MenuItem(label="^_^ MPS for SIMKL")
            title_item.set_sensitive(False)
            menu.append(title_item)
            
            # Add separator
            menu.append(gtk_module.SeparatorMenuItem())
            
            # Add status item
            status_text = self.app.get_status_text()
            status_item = gtk_module.MenuItem(label=f"Status: {status_text}")
            status_item.set_sensitive(False)
            menu.append(status_item)
            
            # Add separator
            menu.append(gtk_module.SeparatorMenuItem())
            
            # Add Start/Stop monitoring item
            if self.app.status == "running":
                stop_item = gtk_module.MenuItem(label="Stop Monitoring")
                stop_item.connect("activate", self._wrap_callback(self.app.stop_monitoring))
                menu.append(stop_item)
            else:
                start_item = gtk_module.MenuItem(label="Start Monitoring")
                start_item.connect("activate", self._wrap_callback(self.app.start_monitoring))
                menu.append(start_item)
            
            # Add separator
            menu.append(gtk_module.SeparatorMenuItem())
            
            # --- Scrobbling submenu ---
            scrobbling_item = gtk_module.MenuItem(label="Scrobbling")
            scrobbling_submenu = gtk_module.Menu()
            
            retry_item = gtk_module.MenuItem(label="Retry Last Scrobble")
            retry_item.connect("activate", self._wrap_callback(self.app.try_scrobble_again))
            scrobbling_submenu.append(retry_item)
            
            sync_item = gtk_module.MenuItem(label="Sync Backlog Now")
            sync_item.connect("activate", self._wrap_callback(self.app.process_backlog))
            scrobbling_submenu.append(sync_item)
            
            # --- Threshold Submenu (nested under Scrobbling) ---
            threshold_item = gtk_module.MenuItem(label="Completion Threshold")
            threshold_submenu = gtk_module.Menu()
            threshold_group = None # Will hold the first RadioMenuItem for grouping

            current_threshold = get_setting('watch_completion_threshold', DEFAULT_THRESHOLD)

            def create_preset_item(value, label):
                nonlocal threshold_group
                # Use RadioMenuItem instead of CheckMenuItem for proper radio behavior
                if threshold_group is None:
                    # First item in the group
                    item = gtk_module.RadioMenuItem(label=label)
                    threshold_group = item
                else:
                    # Subsequent items join the group
                    item = gtk_module.RadioMenuItem(group=threshold_group, label=label)

                item.set_active(current_threshold == value)
                item.connect("activate", lambda w, v=value: self._wrap_callback(lambda: self.app._set_preset_threshold(v))())
                return item

            threshold_submenu.append(create_preset_item(65, "65%"))
            threshold_submenu.append(create_preset_item(80, "80% (Default)"))
            threshold_submenu.append(create_preset_item(90, "90%"))
            threshold_submenu.append(gtk_module.SeparatorMenuItem())

            custom_item = gtk_module.MenuItem(label="Custom...")
            custom_item.connect("activate", self._wrap_callback(self.app.set_custom_watch_threshold))
            threshold_submenu.append(custom_item)

            threshold_item.set_submenu(threshold_submenu)
            scrobbling_submenu.append(threshold_item)

            # Minimum Watch Time submenu
            min_watch_item = gtk_module.MenuItem(label="Minimum Watch Time")
            min_watch_submenu = gtk_module.Menu()
            min_watch_group = None
            current_min_watch = get_setting('min_rewatch_watch_seconds', DEFAULT_MIN_REWATCH_WATCH_SECONDS)

            def create_min_watch_preset_item(value, label):
                nonlocal min_watch_group
                if min_watch_group is None:
                    item = gtk_module.RadioMenuItem(label=label)
                    min_watch_group = item
                else:
                    item = gtk_module.RadioMenuItem(group=min_watch_group, label=label)

                item.set_active(current_min_watch == value)
                item.connect("activate", lambda w, v=value: self._wrap_callback(lambda: self.app._set_preset_min_watch_time(v))())
                return item

            min_watch_submenu.append(create_min_watch_preset_item(0, "None (0s)"))
            min_watch_submenu.append(create_min_watch_preset_item(60, "1 Minute (60s)"))
            min_watch_submenu.append(create_min_watch_preset_item(180, "3 Minutes (Default)"))
            min_watch_submenu.append(create_min_watch_preset_item(300, "5 Minutes (300s)"))
            min_watch_submenu.append(create_min_watch_preset_item(600, "10 Minutes (600s)"))
            min_watch_submenu.append(gtk_module.SeparatorMenuItem())

            custom_min_watch_item = gtk_module.MenuItem(label="Custom...")
            custom_min_watch_item.connect("activate", self._wrap_callback(self.app.set_custom_min_watch_time))
            min_watch_submenu.append(custom_min_watch_item)

            min_watch_item.set_submenu(min_watch_submenu)
            scrobbling_submenu.append(min_watch_item)

            scrobbling_submenu.append(gtk_module.SeparatorMenuItem())
            
            # Notifications toggle
            notifications_disabled = get_setting('disable_notifications', False)
            notifications_item = gtk_module.CheckMenuItem(label="Turn Notifications Off")
            notifications_item.set_active(notifications_disabled)
            notifications_item.connect("activate", self._wrap_callback(self.app.toggle_notifications_disabled))
            scrobbling_submenu.append(notifications_item)
            
            scrobbling_submenu.append(gtk_module.SeparatorMenuItem())
            
            watch_history_item = gtk_module.MenuItem(label="Open Local Watch History")
            watch_history_item.connect("activate", self._wrap_callback(self.app.open_watch_history))
            scrobbling_submenu.append(watch_history_item)
            
            scrobbling_item.set_submenu(scrobbling_submenu)
            menu.append(scrobbling_item)
            
            # --- SIMKL submenu ---
            simkl_item = gtk_module.MenuItem(label="SIMKL")
            simkl_submenu = gtk_module.Menu()
            
            auth_label = "Authenticate" if not self.app.is_authenticated else "Re-authenticate"
            if self.app._auth_in_progress:
                auth_label = "Authenticating..."
            auth_item = gtk_module.MenuItem(label=auth_label)
            auth_item.set_sensitive(not self.app._auth_in_progress)
            auth_item.connect("activate", self._wrap_callback(self.app.trigger_auth_flow))
            simkl_submenu.append(auth_item)
            
            simkl_submenu.append(gtk_module.SeparatorMenuItem())
            
            website_item = gtk_module.MenuItem(label="Open Website")
            website_item.connect("activate", self._wrap_callback(self.app.open_simkl))
            simkl_submenu.append(website_item)
            
            simkl_history_item = gtk_module.MenuItem(label="Open Watch History")
            simkl_history_item.connect("activate", self._wrap_callback(self.app.open_simkl_history))
            simkl_submenu.append(simkl_history_item)
            
            simkl_item.set_submenu(simkl_submenu)
            menu.append(simkl_item)
            
            # --- Maintenance submenu ---
            maintenance_item = gtk_module.MenuItem(label="Maintenance")
            maintenance_submenu = gtk_module.Menu()
            
            logs_item = gtk_module.MenuItem(label="Open Logs")
            logs_item.connect("activate", self._wrap_callback(self.app.open_logs))
            maintenance_submenu.append(logs_item)
            
            config_item = gtk_module.MenuItem(label="Open Data Folder")
            config_item.connect("activate", self._wrap_callback(self.app.open_config_dir))
            maintenance_submenu.append(config_item)

            filters_item = gtk_module.MenuItem(label="Directory Filters")
            filters_submenu = gtk_module.Menu()

            allow_item = gtk_module.MenuItem(label="Edit Allow List")
            allow_item.connect("activate", self._wrap_callback(self.app.set_allow_dirs))
            filters_submenu.append(allow_item)

            deny_item = gtk_module.MenuItem(label="Edit Deny List")
            deny_item.connect("activate", self._wrap_callback(self.app.set_deny_dirs))
            filters_submenu.append(deny_item)

            filters_submenu.append(gtk_module.SeparatorMenuItem())

            clear_allow_item = gtk_module.MenuItem(label="Clear Allow List")
            clear_allow_item.connect("activate", self._wrap_callback(self.app.clear_allow_dirs))
            filters_submenu.append(clear_allow_item)

            clear_deny_item = gtk_module.MenuItem(label="Clear Deny List")
            clear_deny_item.connect("activate", self._wrap_callback(self.app.clear_deny_dirs))
            filters_submenu.append(clear_deny_item)

            filters_item.set_submenu(filters_submenu)
            maintenance_submenu.append(filters_item)
            
            maintenance_submenu.append(gtk_module.SeparatorMenuItem())
            
            clear_backlog_item = gtk_module.MenuItem(label="Clear Backlog")
            clear_backlog_item.connect("activate", self._wrap_callback(self.app.clear_backlog))
            maintenance_submenu.append(clear_backlog_item)
            
            clear_cache_item = gtk_module.MenuItem(label="Clear Cache")
            clear_cache_item.connect("activate", self._wrap_callback(self.app.clear_cache))
            maintenance_submenu.append(clear_cache_item)
            
            clear_history_item = gtk_module.MenuItem(label="Clear Watch History")
            clear_history_item.connect("activate", self._wrap_callback(self.app.clear_watch_history))
            maintenance_submenu.append(clear_history_item)
            
            clear_logs_item = gtk_module.MenuItem(label="Clear Logs")
            clear_logs_item.connect("activate", self._wrap_callback(self.app.clear_logs))
            maintenance_submenu.append(clear_logs_item)
            
            maintenance_submenu.append(gtk_module.SeparatorMenuItem())
            
            reset_item = gtk_module.MenuItem(label="Reset App Data (Danger)")
            reset_item.connect("activate", self._wrap_callback(self.app.clear_all_data))
            maintenance_submenu.append(reset_item)
            
            maintenance_item.set_submenu(maintenance_submenu)
            menu.append(maintenance_item)
            
            # --- More submenu ---
            more_item = gtk_module.MenuItem(label="More")
            more_submenu = gtk_module.Menu()
            
            donate_item = gtk_module.MenuItem(label="Donate ❤️")
            donate_item.connect("activate", self._wrap_callback(self.app.open_donation_page))
            more_submenu.append(donate_item)
            
            more_submenu.append(gtk_module.SeparatorMenuItem())
            
            update_item = gtk_module.MenuItem(label="Check for Updates")
            update_item.connect("activate", self._wrap_callback(self.app.check_updates_thread))
            more_submenu.append(update_item)
            
            help_item = gtk_module.MenuItem(label="Help")
            help_item.connect("activate", self._wrap_callback(self.app.show_help))
            more_submenu.append(help_item)
            
            about_item = gtk_module.MenuItem(label="About")
            about_item.connect("activate", self._wrap_callback(self.app.show_about))
            more_submenu.append(about_item)
            
            more_item.set_submenu(more_submenu)
            menu.append(more_item)
            
            # Add separator
            menu.append(gtk_module.SeparatorMenuItem())
            
            # Exit
            exit_item = gtk_module.MenuItem(label="Exit")
            exit_item.connect("activate", self._wrap_callback(self.app.exit_app))
            menu.append(exit_item)
            
            menu.show_all()
            indicator_obj = cast(Any, self.indicator)
            indicator_obj.set_menu(menu)
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


class TrayAppLinux(TrayAppBase):
    """Linux system tray application for simkl-mps"""
    
    def __init__(self):
        super().__init__()
        
        # Set up the appropriate tray implementation based on availability
        if (USE_APP_INDICATOR):
            self.indicator_tray = AppIndicatorTray(self)
            self.using_appindicator = True
            self.tray_icon: Any = cast(Any, None)
        else:
            self.using_appindicator = False
            self.tray_icon = cast(Any, None)
            self.setup_icon()
    
    def setup_icon(self):
        """Setup the system tray icon using pystray"""
        if self.using_appindicator:
            return

        if pystray is None:
            raise RuntimeError("pystray module not available")
            
        try:
            image = self.load_icon_for_status()

            pystray_module = cast(Any, pystray)
            self.tray_icon = pystray_module.Icon(
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
        """Load the appropriate icon PIL.Image for the current status using the base class path finder (for pystray fallback)."""
        # This method is only used when AppIndicator is NOT available.
        icon_path_str = self._get_icon_path(status=self.status) # Use base class method

        if icon_path_str:
            try:
                icon_path = Path(icon_path_str)
                if icon_path.exists():
                    logger.debug(f"Loading pystray icon from base path: {icon_path}")
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
        logger.warning("Falling back to generated image for pystray icon.")
        return self._create_fallback_image(size=128) # Use a reasonable size for Linux tray

    def create_menu(self):
        """Create the pystray menu using the base class helper (only for pystray fallback)."""
        # This is used only for pystray implementation
        if self.using_appindicator:
            return None # AppIndicator uses its own GTK menu

        # Build the list of menu items using the base class method
        menu_items = self._build_pystray_menu_items()
        # Create the pystray Menu object from the list
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
        if get_setting('disable_notifications', False):
            logger.debug(f"Linux notification suppressed by user setting: {title}")
            return

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
                    from gi.repository import Notify  # type: ignore[import]
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
                from plyer import notification as plyer_notification_module
                notifier = cast(Any, plyer_notification_module)
                notifier.notify(
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
            about_text = self._build_about_text()

            # Try using zenity for a nicer dialog
            try:
                subprocess.run([
                    'zenity', '--info', 
                    '--title=About MPS for SIMKL', 
                    f'--text={about_text}'
                ])
                return None
            except:
                pass
                
            # Try using GTK if AppIndicator is available
            if self.using_appindicator:
                try:
                    from gi.repository import Gtk  # type: ignore[import]
                    
                    dialog = Gtk.MessageDialog(
                        None, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                        "Media Player Scrobbler for SIMKL"
                    )
                    dialog.format_secondary_text(about_text)
                    dialog.set_title("About")
                    dialog.run()
                    dialog.destroy()
                    return None
                except:
                    pass
                    
            # Fallback to notification
            self.show_notification("About MPS for SIMKL", about_text)
                
        except Exception as e:
            logger.error(f"Error showing about dialog: {e}")
            self.show_notification("About", "Media Player Scrobbler for SIMKL")
        return None

    def show_help(self, _=None):
        """Show help information with Linux-specific implementation"""
        try:
            # Open documentation
            help_url = "https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl#readme"
            webbrowser.open(help_url)
        except Exception as e:
            logger.error(f"Error showing help: {e}")
            self.show_notification("Help", "Visit https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl#readme for help")
        return None

    def exit_app(self, _=None):
        """Exit the application"""
        logger.info("Exiting application from tray")
        if self.monitoring_active:
            self.stop_monitoring()
            
        if self.using_appindicator:
            if self.indicator_tray:
                self.indicator_tray.stop()
        else:
            tray_icon = cast(Any, self.tray_icon)
            if tray_icon:
                tray_icon.stop()
        return None

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
                tray_icon = cast(Any, self.tray_icon)
                if tray_icon:
                    tray_icon.run()
                else:
                    raise RuntimeError("Tray icon not initialized")
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

    # --- Watch Threshold Implementation ---

    def _ask_custom_threshold_dialog(self, current_threshold: int) -> Optional[int]:
        """Ask user for custom threshold using zenity."""
        logger.debug("Attempting to ask for custom threshold using zenity.")
        try:
            # Check if zenity is available
            if subprocess.run(['which', 'zenity'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
                logger.warning("zenity command not found. Cannot ask for custom threshold.")
                self.show_notification("Cannot Set Custom Threshold", "zenity command not found. Please install zenity.")
                return None

            # Use zenity to get input
            process = subprocess.run(
                [
                    'zenity', '--entry',
                    '--title=Set Watch Threshold',
                    f'--text=Enter watch completion threshold (%):\n(Current: {current_threshold}%)',
                    f'--entry-text={current_threshold}'
                ],
                capture_output=True,
                text=True,
                check=False # Don't raise error on non-zero exit (e.g., cancel)
            )

            if process.returncode == 0: # 0 means OK was pressed
                try:
                    value = int(process.stdout.strip())
                    if 1 <= value <= 100:
                        logger.info(f"User entered custom threshold: {value}")
                        return value
                    else:
                        logger.warning(f"User entered invalid threshold value: {value}")
                        self.show_notification("Invalid Input", "Threshold must be between 1 and 100.")
                        return None
                except ValueError:
                    logger.warning(f"User entered non-integer value: {process.stdout.strip()}")
                    self.show_notification("Invalid Input", "Please enter a number between 1 and 100.")
                    return None
            else: # User cancelled or closed the dialog
                logger.debug("User cancelled custom threshold input via zenity.")
                return None

        except FileNotFoundError:
            logger.error("zenity command not found, even after 'which' check (unexpected).")
            self.show_notification("Error", "zenity command not found.")
            return None

    def _ask_custom_min_watch_time_dialog(self, current_seconds: int) -> Optional[int]:
        """Ask user for custom minimum watch time in seconds using zenity."""
        logger.debug("Attempting to ask for custom minimum watch time using zenity.")
        try:
            if subprocess.run(['which', 'zenity'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
                logger.warning("zenity command not found. Cannot ask for custom minimum watch time.")
                self.show_notification("Cannot Set Custom Time", "zenity command not found. Please install zenity.")
                return None

            process = subprocess.run(
                [
                    'zenity', '--entry',
                    '--title=Set Minimum Watch Time',
                    f'--text=Enter minimum watch time (seconds):\n(Current: {current_seconds}s)',
                    f'--entry-text={current_seconds}'
                ],
                capture_output=True,
                text=True,
                check=False
            )

            if process.returncode == 0:
                try:
                    value = int(process.stdout.strip())
                    if 0 <= value <= 86400:
                        logger.info(f"User entered custom minimum watch time: {value}")
                        return value
                    else:
                        logger.warning(f"User entered invalid minimum watch time value: {value}")
                        self.show_notification("Invalid Input", "Minimum watch time must be between 0 and 86400 seconds.")
                        return None
                except ValueError:
                    logger.warning(f"User entered non-integer value: {process.stdout.strip()}")
                    self.show_notification("Invalid Input", "Please enter a valid number of seconds.")
                    return None
            else:
                logger.debug("User cancelled custom minimum watch time input via zenity.")
                return None

        except FileNotFoundError:
            logger.error("zenity command not found, even after 'which' check (unexpected).")
            self.show_notification("Error", "zenity command not found.")
            return None

    def _ask_directory_filter_dialog(self, title: str, current_value: str, help_text: str) -> Optional[str]:
        """Ask user for directory filters using zenity entry (comma/semicolon separated)."""
        try:
            if subprocess.run(['which', 'zenity'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
                self.show_notification("Cannot Edit Filters", "zenity is not installed. Please install zenity.")
                return None

            initial_value = current_value.replace("\n", "; ") if current_value else ""
            process = subprocess.run(
                [
                    'zenity', '--entry',
                    f'--title={title}',
                    f'--text={help_text}\nSeparate entries with commas or semicolons.',
                    f'--entry-text={initial_value}'
                ],
                capture_output=True,
                text=True,
                check=False
            )

            if process.returncode == 0:
                return process.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Error using zenity for directory filters: {e}", exc_info=True)
            self.show_notification("Error", f"Could not edit directory filters: {e}")
            return None

    # _set_preset_threshold is handled by base class
    # set_custom_watch_threshold is handled by base class

    # --- End Watch Threshold Implementation ---

def run_tray_app():
    """Run the application in tray mode"""
    try:
        app = TrayAppLinux()
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
