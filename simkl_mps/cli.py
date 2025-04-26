"""
Command-Line Interface (CLI) for the Media Player Scrobbler for SIMKL application.

Provides commands for initialization, starting/stopping the service,
managing the background service, and checking status.
"""
import argparse
import sys
import os
import colorama
import subprocess
import logging
import importlib.metadata
import json
from pathlib import Path
from colorama import Fore, Style

VERSION = "unknown" # Default fallback version

def get_version():
    """Get version information dynamically."""
    global VERSION # Allow modification of the global VERSION

    # 1. Try importlib.metadata (for installed package)
    try:
        for pkg_name in ['simkl-mps', 'simkl_mps']:
            try:
                VERSION = importlib.metadata.version(pkg_name)
                return VERSION
            except importlib.metadata.PackageNotFoundError:
                pass
    except ImportError:
        logger.debug("importlib.metadata not available.")
        pass # Ignore if importlib.metadata is not available

    # 2. Try __version__ from __init__.py (for development source)
    try:
        from simkl_mps import __version__
        VERSION = __version__
        return VERSION
    except (ImportError, AttributeError):
         logger.debug("Could not import __version__ from simkl_mps.")
         pass

    # 3. Fallback (already set)
    logger.warning(f"Could not determine version dynamically, using fallback: {VERSION}")
    return VERSION

# Initialize VERSION by calling get_version()
VERSION = get_version()

# Removed early exit for version flags - argparse will handle this.

from simkl_mps.simkl_api import pin_auth_flow, get_user_settings # Added get_user_settings
from simkl_mps.credentials import get_credentials, get_env_file_path
from simkl_mps.main import SimklScrobbler, APP_DATA_DIR, get_tray_app # Import APP_DATA_DIR for log path display and get_tray_app

colorama.init()
logger = logging.getLogger(__name__)

def _setup_logging():
    """Configure logging for the application."""
    log_file = APP_DATA_DIR / "simkl_mps.log"
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True) # Ensure directory exists
    
    # Basic config for file logging
    logging.basicConfig(
        level=logging.DEBUG, # Log everything to file
        format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        filename=log_file,
        filemode='a' # Append to log file
    )
    
    # Configure console logging (only for INFO level and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s') # Simple format for console
    console_handler.setFormatter(formatter)
    
    # Add console handler to the root logger
    logging.getLogger('').addHandler(console_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")

def _check_prerequisites(check_token=True, check_client_id=True):
    """Helper function to check if credentials exist before running a command."""
    env_path = get_env_file_path()
    creds = get_credentials()
    error = False
    if check_client_id and not creds.get("client_id"):
        print(f"{Fore.RED}ERROR: Client ID is missing. Application build might be corrupted. Please reinstall.{Style.RESET_ALL}", file=sys.stderr)
        error = True
    if check_token and not creds.get("access_token"):
        print(f"{Fore.RED}ERROR: Access Token not found in '{env_path}'. Please run 'simkl-mps init' first.{Style.RESET_ALL}", file=sys.stderr)
        error = True
    return not error

def init_command(args):
    """
    Handles the 'init' command.
    Checks existing credentials, performs OAuth device flow if necessary,
    and saves the access token. Verifies the final configuration.
    """
    print(f"{Fore.CYAN}=== Media Player Scrobbler for SIMKL Initialization ==={Style.RESET_ALL}")
    env_path = get_env_file_path()
    print(f"Access token file: {env_path}")
    creds = get_credentials()
    client_id = creds.get("client_id")
    access_token = creds.get("access_token")
    if not client_id or not creds.get("client_secret"):
        print(f"{Fore.RED}ERROR: Client ID or Secret not found. Please reinstall the application.{Style.RESET_ALL}", file=sys.stderr)
        return 1
    print(f"{Fore.GREEN}✓ Client ID/Secret loaded.{Style.RESET_ALL}")
    if access_token:
        print(f"{Fore.GREEN}✓ Access Token found. Skipping authentication.{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}No Access Token found. Starting authentication...{Style.RESET_ALL}")
        new_access_token = pin_auth_flow(client_id)
        if not new_access_token:
            print(f"{Fore.RED}ERROR: Authentication failed or was cancelled.{Style.RESET_ALL}", file=sys.stderr)
            return 1
        print(f"{Fore.GREEN}✓ Access token saved successfully.{Style.RESET_ALL}")
        access_token = new_access_token # Use the newly obtained token

    print(f"Verifying application configuration by checking API access...")
    # Use get_user_settings for a lightweight verification check
    user_settings = get_user_settings(client_id, access_token)
    if not user_settings:
        print(f"{Fore.RED}ERROR: Configuration verification failed. Could not connect to Simkl API with the current credentials.{Style.RESET_ALL}", file=sys.stderr)
        print(f"{Fore.YELLOW}Hint: Check your internet connection, Simkl API status, or try re-initializing ('simkl-mps init').{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Log file: {APP_DATA_DIR / 'simkl_mps.log'}{Style.RESET_ALL}")
        return 1
    else:
        user_id = user_settings.get('user_id', 'N/A')
        print(f"{Fore.GREEN}✓ API connection verified successfully (User ID: {user_id}).{Style.RESET_ALL}")

    print(f"{Fore.GREEN}Initialization Complete!{Style.RESET_ALL}")
    print(f"To start monitoring and scrobbling, run: {Fore.WHITE}simkl-mps start{Style.RESET_ALL}")
    return 0

def start_command(args):
    """
    Handles the 'start' command.

    Installs the application as a startup service, launches the service,
    and launches the tray application in a detached background process.
    All components run in background - closing terminal won't affect function.
    """
    print(f"{Fore.CYAN}=== Starting Media Player Scrobbler for SIMKL ==={Style.RESET_ALL}")
    logger.info("Executing start command.")

    if not _check_prerequisites():
        print(f"{Fore.YELLOW}[!] No access token found. Running initialization...{Style.RESET_ALL}")
        init_result = init_command(args)
        if init_result != 0:
            print(f"{Fore.RED}ERROR: Initialization failed. Cannot start application.{Style.RESET_ALL}", file=sys.stderr)
            return 1

        if not _check_prerequisites():
            print(f"{Fore.RED}ERROR: Still missing credentials after initialization. Aborting start.{Style.RESET_ALL}", file=sys.stderr)
            return 1

    if os.environ.get("SIMKL_TRAY_SUBPROCESS") == "1":
        logger.info("Detected we're in the tray subprocess - running tray app directly")
        print("Running tray application directly...")
        # Get the platform-specific tray app implementation
        _, run_tray_app = get_tray_app()
        sys.exit(run_tray_app())

    print("[*] Launching application with tray icon in background...")
    logger.info("Launching tray application in detached process.")
    
    try:
        # Determine the command to launch the tray application
        if getattr(sys, 'frozen', False):
            # We're running in a PyInstaller bundle
            exe_dir = Path(sys.executable).parent
            
            # Look for the dedicated tray executable - now named "MPS for Simkl.exe"
            tray_exe_paths = [
                exe_dir / "MPS for Simkl.exe",  # Windows - new name
                exe_dir / "MPS for Simkl",      # Linux/macOS - new name
            ]
            
            # Use the first tray executable that exists
            for tray_path in tray_exe_paths:
                if tray_path.exists():
                    cmd = [str(tray_path)]
                    logger.info(f"Using dedicated tray executable: {tray_path}")
                    break
            else:
                # No dedicated tray executable found - use the main executable with the tray parameter
                cmd = [sys.executable, "tray"]
                logger.info("Using main executable with 'tray' parameter as fallback")
        else:
            # Not frozen - launch as a Python module
            cmd = [sys.executable, "-m", "simkl_mps.tray_app"]
            logger.info("Launching tray via Python module (development mode)")

        # Set up environment for subprocess
        env = os.environ.copy()
        env["SIMKL_TRAY_SUBPROCESS"] = "1"  # Mark as subprocess
        
        if sys.platform == "win32":
            # Windows-specific process creation
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.Popen(
                cmd, 
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, 
                close_fds=True, 
                shell=False,
                startupinfo=startupinfo,
                env=env
            )
            logger.info("Launched detached process on Windows")
        else:
            # Unix-like systems (Linux, macOS)
            subprocess.Popen(
                cmd, 
                start_new_session=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL, 
                close_fds=True, 
                shell=False,
                env=env
            )
            logger.info("Launched detached process on Unix-like system")

        print(f"{Fore.GREEN}[✓] Scrobbler launched successfully in background.{Style.RESET_ALL}")
        print(f"[*] Look for the SIMKL-MPS icon in your system tray.")
        print(f"{Fore.GREEN}[✓] You can safely close this terminal window. All processes will continue running.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        logger.exception(f"Failed to launch detached tray process: {e}")
        print(f"{Fore.RED}ERROR: Failed to launch application in background: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def tray_command(args):
    """
    Handles the 'tray' command.

    Runs ONLY the tray application attached to the current terminal.
    Logs will be printed to the terminal.
    Closing the terminal will stop the application.
    """
    print(f"{Fore.CYAN}=== Starting Media Player Scrobbler for SIMKL (Tray Foreground Mode) ==={Style.RESET_ALL}")
    logger.info("Executing tray command (foreground).")
    if not _check_prerequisites(): return 1

    print("[*] Launching tray application in foreground...")
    print("[*] Logs will be printed below. Press Ctrl+C to exit.")
    try:
        # Get the platform-specific tray app implementation
        _, run_tray_app = get_tray_app()
        return run_tray_app() # Run directly and return its exit code
    except KeyboardInterrupt:
        logger.info("Tray application stopped by user (Ctrl+C).")
        print("\n[*] Tray application stopped.")
        return 0
    except Exception as e:
        logger.exception(f"Failed to run tray application in foreground: {e}")
        print(f"{Fore.RED}ERROR: Failed to run tray application: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def version_command(args):
    """
    Displays version information about the application.
    
    Shows the current installed version of simkl-mps.
    """
    print(f"{Fore.CYAN}=== simkl-mps Version Information ==={Style.RESET_ALL}")
    logger.info(f"Displaying version information: {VERSION}")
    
    print(f"simkl-mps v{VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")

    if getattr(sys, 'frozen', False):
        print(f"Installation: Packaged executable")
        print(f"Executable: {sys.executable}")
    else:
        print(f"Installation: Running from source")
    
    print(f"\nData directory: {APP_DATA_DIR}")
    return 0

def check_for_updates(silent=False):
    """
    Check for updates to the application.
    
    Args:
        silent (bool): If True, run silently with no user interaction
        
    Returns:
        bool: True if update check was successful, False otherwise
    """
    logger.info("Checking for updates...")
    
    try:
        import subprocess
        import os
        from pathlib import Path
        
        # Get the path to the updater script
        if getattr(sys, 'frozen', False):
            # Running as frozen executable
            updater_path = Path(sys.executable).parent / "updater.ps1"
        else:
            # Running in development mode
            updater_path = Path(__file__).parent / "utils" / "updater.ps1"
        
        if not updater_path.exists():
            logger.error(f"Updater script not found at {updater_path}")
            return False
            
        # Build the PowerShell command
        args = [
            "powershell.exe",
            "-ExecutionPolicy", "Bypass",
            "-File", str(updater_path)
        ]
        
        if silent:
            args.append("-Silent")
            
        args.append("-CheckOnly")  # Just check, don't install automatically
        
        # Run the updater
        logger.debug(f"Running updater: {' '.join(args)}")
        subprocess.Popen(args)
        return True
        
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return False

def exit_command(args):
    """
    Handles the 'exit' command.
    
    Finds and terminates all running instances of the application,
    ensuring all background activities are properly stopped.
    """
    print(f"{Fore.CYAN}=== Stopping Media Player Scrobbler for SIMKL ==={Style.RESET_ALL}")
    logger.info("Executing exit command to terminate all instances.")
    
    if sys.platform == "win32":
        # Windows implementation
        import ctypes
        import win32com.client
        import win32gui
        import win32process
        import win32con
        
        print("[*] Looking for running SIMKL-MPS instances...")
        killed_any = False
        
        try:
            # First approach: Find by window title/class and send WM_CLOSE
            def enum_windows_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    
                    # Check for our app window (both executable and Python process)
                    if "MPS for SIMKL" in window_text or "simkl-mps" in window_text.lower():
                        logger.info(f"Found window: '{window_text}', class: '{class_name}'")
                        results.append(hwnd)
                        
                    # Also look for pystray windows (development mode)
                    if class_name == "pystray" or "simkl-mps" in class_name.lower():
                        logger.info(f"Found pystray window: '{window_text}', class: '{class_name}'")
                        results.append(hwnd)
                return True
            
            window_handles = []
            win32gui.EnumWindows(enum_windows_callback, window_handles)
            
            for hwnd in window_handles:
                try:
                    # Get process ID for the window
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    logger.info(f"Sending close command to window with PID: {pid}")
                    
                    # Try to post a close message
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    killed_any = True
                except Exception as e:
                    logger.error(f"Failed to close window: {e}")
            
            # Second approach: Find processes by executable name
            try:
                wmi = win32com.client.GetObject('winmgmts:')
                
                process_names = [
                    "MPS for SIMKL.exe",
                    "MPSS.exe",
                    "simkl-mps.exe",
                    "python.exe"
                ]
                
                for process_name in process_names:
                    processes = []
                    
                    if process_name == "python.exe":
                        # Only target Python processes running our module
                        processes = wmi.ExecQuery(
                            f"SELECT * FROM Win32_Process WHERE Name = '{process_name}' AND CommandLine LIKE '%simkl_mps%'"
                        )
                    else:
                        processes = wmi.ExecQuery(f"SELECT * FROM Win32_Process WHERE Name = '{process_name}'")
                    
                    for process in processes:
                        try:
                            pid = process.ProcessId
                            cmd_line = process.CommandLine or ""
                            
                            # Skip the current process
                            if pid == os.getpid():
                                continue
                                
                            # For python.exe, confirm it's actually our app
                            if process_name == "python.exe" and "simkl_mps" not in cmd_line.lower():
                                logger.debug(f"Skipping Python process (PID: {pid}) - not related to simkl-mps")
                                continue
                                
                            logger.info(f"Terminating process: {process_name} (PID: {pid})")
                            print(f"[*] Terminating process: {process_name} (PID: {pid})")
                            process.Terminate()
                            killed_any = True
                        except Exception as e:
                            logger.error(f"Failed to terminate process {process_name}: {e}")
            except Exception as e:
                logger.error(f"Error accessing WMI: {e}")
        
        except Exception as e:
            logger.error(f"Error during Windows process termination: {e}", exc_info=True)
            print(f"{Fore.RED}ERROR: Could not terminate processes: {e}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    
    elif sys.platform == "darwin":
        # macOS implementation
        import subprocess
        
        print("[*] Looking for running SIMKL-MPS instances...")
        killed_any = False
        
        try:
            # Find processes
            cmd = [
                "pgrep", "-f", "simkl-mps|simkl_mps|MPS for SIMKL"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            pids = result.stdout.strip().split()
            
            # Terminate each process except the current one
            for pid in pids:
                pid = pid.strip()
                if pid and pid.isdigit() and int(pid) != os.getpid():
                    logger.info(f"Terminating process with PID: {pid}")
                    print(f"[*] Terminating process with PID: {pid}")
                    try:
                        subprocess.run(["kill", pid])
                        killed_any = True
                    except Exception as e:
                        logger.error(f"Failed to terminate process {pid}: {e}")
            
        except Exception as e:
            logger.error(f"Error during macOS process termination: {e}", exc_info=True)
            print(f"{Fore.RED}ERROR: Could not terminate processes: {e}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    
    else:
        # Linux implementation
        import subprocess
        
        print("[*] Looking for running SIMKL-MPS instances...")
        killed_any = False
        
        try:
            # First find the relevant processes
            cmd = [
                "pgrep", "-f", "simkl-mps|simkl_mps|MPS for SIMKL"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            pids = result.stdout.strip().split()
            
            # Terminate each process except the current one
            for pid in pids:
                pid = pid.strip()
                if pid and pid.isdigit() and int(pid) != os.getpid():
                    logger.info(f"Terminating process with PID: {pid}")
                    print(f"[*] Terminating process with PID: {pid}")
                    try:
                        subprocess.run(["kill", pid])
                        killed_any = True
                    except Exception as e:
                        logger.error(f"Failed to terminate process {pid}: {e}")
            
        except Exception as e:
            logger.error(f"Error during Linux process termination: {e}", exc_info=True)
            print(f"{Fore.RED}ERROR: Could not terminate processes: {e}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    
    # Check if we killed anything
    if killed_any:
        print(f"{Fore.GREEN}[✓] Successfully terminated SIMKL-MPS processes.{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}[!] No running SIMKL-MPS processes were found.{Style.RESET_ALL}")
        
    print(f"{Fore.GREEN}[✓] Application has been stopped.{Style.RESET_ALL}")
    return 0

def create_parser():
    """
    Creates and configures the argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="simkl-mps: Automatically scrobble movie watch history to Simkl.",
        formatter_class=argparse.RawTextHelpFormatter # Preserve help text formatting
    )

    parser.add_argument("--version", "-v", action="store_true", 
                       help="Display version information and exit")
                       
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True) # Make command required

    init_parser = subparsers.add_parser(
        "init",
        aliases=['i'],
        help="Initialize or re-authenticate the scrobbler with your Simkl account."
    )

    start_parser = subparsers.add_parser(
        "start",
        aliases=['s'],
        help="Run ALL components (background service + tray icon). Terminal can be closed."
    )

    tray_parser = subparsers.add_parser(
        "tray",
        aliases=['t'],
        help="Run ONLY tray icon attached to the terminal (shows logs)."
    )

    version_parser = subparsers.add_parser(
        "version",
        aliases=['V'],
        help="Display the current installed version of simkl-mps."
    )
    
    exit_parser = subparsers.add_parser(
        "exit",
        aliases=['e', 'stop', 'quit'],
        help="Stop all running instances of the application and terminate all background activities."
    )
    
    return parser

def main():
    """
    Main entry point for the CLI application.

    Parses arguments and dispatches to the appropriate command function.

    Returns:
        int: Exit code (0 for success, 1 for errors).
    """
    # Check for common Linux dependency issues before setting up logging
    if sys.platform == 'linux':
        try:
            # Try to import PyGObject - this will fail if system dependencies are missing
            import gi
        except ImportError as e:
            # Provide helpful guidance for Linux users with missing dependencies
            if "gi" in str(e) or "gobject" in str(e).lower():
                print(f"{Fore.RED}ERROR: Missing required Linux system dependencies for PyGObject/GTK.{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Please install the required system packages before installing simkl-mps:{Style.RESET_ALL}")
                print("\nFor Ubuntu/Debian:")
                print("  sudo apt install python3-pip python3-dev python3-setuptools wmctrl xdotool python3-gi python3-gi-cairo gir1.2-gtk-3.0 libgirepository1.0-dev libcairo2-dev pkg-config libnotify-bin python3-venv")
                print("\nFor Fedora/RHEL/CentOS:")
                print("  sudo dnf install python3-pip python3-devel gobject-introspection-devel cairo-devel pkg-config python3-gobject gtk3 wmctrl xdotool libnotify")
                print("\nFor Arch Linux:")
                print("  sudo pacman -S python-pip python-setuptools python-gobject gtk3 gobject-introspection cairo pkg-config wmctrl xdotool libnotify")
                print("\nThen reinstall with: pip install --no-binary=:all: \"simkl-mps[linux]\"")
                print("Or with pipx: pipx install --system-site-packages \"simkl-mps[linux]\"")
                return 1
    
    # Setup logging AFTER the dependency check
    _setup_logging()
    
    parser = create_parser()
    args = parser.parse_args()

    # If no command was provided (e.g., just 'simkl-mps'), print help.
    # Note: 'required=True' in add_subparsers makes this less likely, but good practice.
    if not hasattr(args, 'command') or not args.command:
        parser.print_help()
        return 0
        
    # Check for updates only when starting the full background service
    if os.environ.get("SIMKL_TRAY_SUBPROCESS") != "1" and args.command == "start":
        # Check if user has enabled update checks - Windows only feature
        if sys.platform == 'win32':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\kavinthangavel\Media Player Scrobbler for SIMKL") as key:
                    check_updates = winreg.QueryValueEx(key, "CheckUpdates")[0]
                    if check_updates == 1:
                        logger.info("Auto-update check enabled, checking for updates...")
                        check_for_updates(silent=True)
            except (OSError, ImportError, Exception) as e:
                # If registry key doesn't exist or other error, default to checking for updates
                logger.debug(f"Error checking update preferences, defaulting to check: {e}")
                check_for_updates(silent=True)
        # For other platforms, we don't check for updates automatically yet
        else:
            logger.debug("Auto-update checking is currently only available on Windows")

    command_map = {
        "init": init_command,
        "start": start_command,
        "tray": tray_command,
        "version": version_command,
        "exit": exit_command,
        "help": lambda _: parser.print_help()
    }

    if args.command in command_map:
        try:
            logger.info(f"Executing command: {args.command}")
            exit_code = command_map[args.command](args)
            logger.info(f"Command '{args.command}' finished with exit code {exit_code}.")
            return exit_code
        except Exception as e:

            logger.exception(f"Unhandled exception during command '{args.command}': {e}")
            print(f"\n{Fore.RED}UNEXPECTED ERROR: An error occurred during the '{args.command}' command.{Style.RESET_ALL}", file=sys.stderr)
            print(f"{Fore.RED}Details: {e}{Style.RESET_ALL}", file=sys.stderr)
            print(f"{Fore.YELLOW}Please check the log file for more information: {APP_DATA_DIR / 'simkl_mps.log'}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    else:

        logger.error(f"Unknown command received: {args.command}")
        parser.print_help()
        return 1

if __name__ == "__main__":

    sys.exit(main())