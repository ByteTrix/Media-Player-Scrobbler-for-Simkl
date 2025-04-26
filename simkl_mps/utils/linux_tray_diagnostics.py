#!/usr/bin/env python3
"""
Diagnostic script for Linux tray icon issues.
This script checks dependencies and environment for Linux tray icon support.
"""

import os
import sys
import subprocess
import platform

# Terminal colors for better readability
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def print_section(title):
    """Print a section title with formatting"""
    print(f"\n{BLUE}{'=' * 20} {title} {'=' * 20}{RESET}")

def print_success(message):
    """Print success message"""
    print(f"{GREEN}✓ {message}{RESET}")

def print_warning(message):
    """Print warning message"""
    print(f"{YELLOW}⚠ {message}{RESET}")

def print_error(message):
    """Print error message"""
    print(f"{RED}✗ {message}{RESET}")

def print_info(message):
    """Print info message"""
    print(f"  {message}")

def check_command(command, description):
    """Check if a command is available"""
    try:
        subprocess.run(["which", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print_success(f"{description} is installed ({command})")
        return True
    except subprocess.CalledProcessError:
        print_error(f"{description} is not installed ({command})")
        return False

def check_package(package_name):
    """Check if a Python package is available"""
    try:
        __import__(package_name)
        print_success(f"Python package '{package_name}' is installed")
        return True
    except ImportError:
        print_error(f"Python package '{package_name}' is not installed")
        return False

def check_dbus_session():
    """Check if DBUS_SESSION_BUS_ADDRESS is set"""
    dbus_addr = os.environ.get('DBUS_SESSION_BUS_ADDRESS')
    if dbus_addr:
        print_success(f"DBUS_SESSION_BUS_ADDRESS is set: {dbus_addr}")
        return True
    else:
        print_error("DBUS_SESSION_BUS_ADDRESS is not set")
        return False

def check_desktop_environment():
    """Detect the desktop environment"""
    # Try to get from XDG_CURRENT_DESKTOP
    desktop = os.environ.get('XDG_CURRENT_DESKTOP')
    if desktop:
        print_success(f"Desktop environment detected: {desktop}")
        return desktop

    # Try to get from DESKTOP_SESSION
    desktop_session = os.environ.get('DESKTOP_SESSION')
    if desktop_session:
        print_success(f"Desktop session detected: {desktop_session}")
        return desktop_session

    # Try to determine by checking running processes
    try:
        output = subprocess.check_output(['ps', '-e']).decode('utf-8')
        if 'gnome-session' in output:
            print_success("Desktop environment detected: GNOME")
            return "GNOME"
        elif 'kwin' in output:
            print_success("Desktop environment detected: KDE")
            return "KDE"
        elif 'xfce4-session' in output:
            print_success("Desktop environment detected: XFCE")
            return "XFCE"
        elif 'cinnamon-session' in output:
            print_success("Desktop environment detected: Cinnamon")
            return "Cinnamon"
        elif 'mate-session' in output:
            print_success("Desktop environment detected: MATE")
            return "MATE"
    except:
        pass

    print_warning("Could not detect desktop environment")
    return "Unknown"

def check_wayland():
    """Check if running on Wayland"""
    wayland_display = os.environ.get('WAYLAND_DISPLAY')
    if wayland_display:
        print_warning(f"Running on Wayland (WAYLAND_DISPLAY={wayland_display})")
        return True
    
    session_type = os.environ.get('XDG_SESSION_TYPE')
    if session_type == 'wayland':
        print_warning("Running on Wayland (XDG_SESSION_TYPE=wayland)")
        return True
    
    print_info("Not running on Wayland (using X11 or other)")
    return False

def check_tray_support():
    """Check for tray icon support in the desktop environment"""
    desktop = check_desktop_environment()
    wayland = check_wayland()
    
    if wayland:
        # Check for Wayland-specific issues
        if desktop in ["GNOME", "Unity"]:
            print_warning("GNOME on Wayland may require the 'AppIndicator and KStatusNotifierItem Support' extension")
            print_info("Install from: https://extensions.gnome.org/extension/615/appindicator-support/")
        elif desktop == "KDE":
            print_success("KDE on Wayland should support system tray icons")
        else:
            print_warning("Wayland support for system tray icons varies by desktop environment")
    else:
        # X11-specific checks
        if desktop in ["GNOME", "Unity"]:
            try:
                # Check if GNOME Shell extensions are enabled
                output = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "enabled-extensions"]).decode('utf-8')
                if "appindicatorsupport@rgcjonas.gmail.com" in output:
                    print_success("GNOME AppIndicator extension is enabled")
                else:
                    print_warning("GNOME AppIndicator extension may not be enabled")
                    print_info("Install: sudo apt install gnome-shell-extension-appindicator")
                    print_info("Or from: https://extensions.gnome.org/extension/615/appindicator-support/")
            except:
                print_warning("Could not check GNOME Shell extensions")
        elif desktop == "KDE":
            print_success("KDE generally has good support for system tray icons")
        elif desktop in ["XFCE", "MATE", "Cinnamon"]:
            print_success(f"{desktop} generally has good support for system tray icons")
        else:
            print_warning("Unknown desktop environment - tray support status unknown")

def run_diagnostics():
    """Run all diagnostics"""
    print_section("System Information")
    print_info(f"OS: {platform.system()} {platform.release()}")
    print_info(f"Distribution: {platform.platform()}")
    print_info(f"Python version: {sys.version.split()[0]}")
    
    print_section("Desktop Environment")
    check_desktop_environment()
    check_wayland()
    check_dbus_session()
    check_tray_support()
    
    print_section("Required Commands")
    check_command("notify-send", "Notification sender")
    check_command("zenity", "Zenity dialog tool")
    
    print_section("Python Dependencies")
    check_package("gi")
    try:
        import gi
        print_info("Checking GI versions...")
        try:
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk
            print_success("GTK 3.0 is available")
        except (ImportError, ValueError) as e:
            print_error(f"Error importing GTK: {e}")
            print_info("Try: sudo apt install python3-gi gir1.2-gtk-3.0")
        
        try:
            gi.require_version('AppIndicator3', '0.1')
            from gi.repository import AppIndicator3
            print_success("AppIndicator3 is available")
        except (ImportError, ValueError) as e:
            print_error(f"Error importing AppIndicator3: {e}")
            print_info("Try: sudo apt install gir1.2-appindicator3-0.1")
        
        try:
            gi.require_version('Notify', '0.7')
            from gi.repository import Notify
            print_success("Notify API is available")
        except (ImportError, ValueError) as e:
            print_error(f"Error importing Notify: {e}")
            print_info("Try: sudo apt install gir1.2-notify-0.7")
    except:
        pass
    
    check_package("pystray")
    check_package("PIL")
    check_package("plyer")
    
    print_section("Diagnostic Complete")
    print_info("If issues persist, check application logs for more details:")
    print_info("You can find logs by running: simkl-mps tray")
    print_info("This will run the application in foreground mode with logs visible")

if __name__ == "__main__":
    run_diagnostics()