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
from pathlib import Path
from colorama import Fore, Style

VERSION = "1.0.0"  # Default fallback version

def get_version():
    """Get version information dynamically, using modern approaches."""

    try:

        for pkg_name in ['simkl-mps', 'simkl_mps']:
            try:
                return importlib.metadata.version(pkg_name)
            except importlib.metadata.PackageNotFoundError:
                pass
    except (ImportError, AttributeError):
        pass

    try:
        import subprocess
        try:

            result = subprocess.run(
                ['git', 'describe', '--tags', '--always'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    except ImportError:
        pass

    try:
        from simkl_mps import __version__
        return __version__
    except (ImportError, AttributeError):
        pass

    try:

        import simkl_mps
        pkg_dir = Path(simkl_mps.__file__).parent
        version_file = pkg_dir / 'VERSION'
        if version_file.exists():
            return version_file.read_text().strip()
    except (ImportError, AttributeError, OSError):
        pass

    return VERSION

VERSION = get_version()


if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v", "version"]:
    print(f"simkl-mps v{VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    sys.exit(0)

from simkl_mps.simkl_api import authenticate
from simkl_mps.credentials import get_credentials, get_env_file_path
from simkl_mps.main import SimklScrobbler, APP_DATA_DIR # Import APP_DATA_DIR for log path display
from simkl_mps.tray_app import run_tray_app

colorama.init()
logger = logging.getLogger(__name__)

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
    print(f"[*] Using Access Token file: {env_path}")
    logger.info("Initiating initialization process.")

    print("[*] Loading credentials...")
    creds = get_credentials()
    client_id = creds.get("client_id")
    access_token = creds.get("access_token")

    if not client_id or not creds.get("client_secret"):
        logger.critical("Initialization failed: Client ID or Secret missing (build issue).")
        print(f"{Fore.RED}CRITICAL ERROR: Client ID or Secret not found. Build may be corrupted. Please reinstall.{Style.RESET_ALL}", file=sys.stderr)
        return 1
    else:
        logger.debug("Client ID and Secret loaded successfully (from build).")
        print(f"{Fore.GREEN}[✓] Client ID/Secret loaded successfully.{Style.RESET_ALL}")

    if access_token:
        logger.info("Existing access token found.")
        print(f"{Fore.GREEN}[✓] Access Token found.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[!] Skipping authentication process.{Style.RESET_ALL}")
    else:
        logger.warning("Access token not found, initiating authentication.")
        print(f"{Fore.YELLOW}[!] Access Token not found. Starting authentication...{Style.RESET_ALL}")

        new_access_token = authenticate(client_id)

        if not new_access_token:
            logger.error("Authentication process failed or was cancelled.")
            print(f"{Fore.RED}ERROR: Authentication failed or was cancelled.{Style.RESET_ALL}", file=sys.stderr)
            return 1

        logger.info("Authentication successful, saving new access token.")
        print(f"\n[*] Saving new access token to: {env_path}")
        try:

            env_path.parent.mkdir(parents=True, exist_ok=True)
            with open(env_path, "w", encoding='utf-8') as env_file:

                env_file.write("# Simkl Access Token obtained via 'simkl-mps init'\n")
                env_file.write(f"SIMKL_ACCESS_TOKEN={new_access_token}\n")
            logger.info(f"Access token successfully saved to {env_path}.")
            print(f"{Fore.GREEN}[✓] Access token saved successfully.{Style.RESET_ALL}")

            access_token = new_access_token
        except IOError as e:
            logger.exception(f"Failed to save access token to {env_path}: {e}")
            print(f"{Fore.RED}ERROR: Failed to save access token: {e}{Style.RESET_ALL}", file=sys.stderr)
            return 1

    print(f"\n[*] Verifying application configuration...")
    logger.info("Verifying configuration by initializing SimklScrobbler instance.")
    verifier_scrobbler = SimklScrobbler()
    if not verifier_scrobbler.initialize():
         logger.error("Configuration verification failed after initialization attempt.")
         print(f"{Fore.RED}ERROR: Configuration verification failed. Check logs for details: {APP_DATA_DIR / 'simkl_mps.log'}{Style.RESET_ALL}", file=sys.stderr)
         print(f"{Fore.YELLOW}Hint: If the token seems valid but verification fails, check Simkl API status or report a bug.{Style.RESET_ALL}")
         return 1

    logger.info("Initialization and verification successful.")
    print(f"\n{Fore.GREEN}========================================={Style.RESET_ALL}")
    print(f"{Fore.GREEN}✓ Initialization Complete!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}========================================={Style.RESET_ALL}")
    print(f"\n[*] To start monitoring and scrobbling, run:")
    print(f"    {Fore.WHITE}simkl-mps start{Style.RESET_ALL}")
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
        from simkl_mps.tray_app import run_tray_app
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


        from simkl_mps.tray_app import run_tray_app
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
    
    return parser

def main():
    """
    Main entry point for the CLI application.

    Parses arguments and dispatches to the appropriate command function.

    Returns:
        int: Exit code (0 for success, 1 for errors).
    """
    parser = create_parser()
    args = parser.parse_args()

    if getattr(args, 'version', False):
        return version_command(args)

    if not hasattr(args, 'command') or not args.command:
        parser.print_help()
        return 0
        
    # Check for updates when starting the app (except for the tray subprocess)
    if os.environ.get("SIMKL_TRAY_SUBPROCESS") != "1" and args.command in ["start", "tray"]:
        # Check if user has enabled update checks
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\kavinthangavel\Media Player Scrobbler for SIMKL") as key:
                check_updates = winreg.QueryValueEx(key, "CheckUpdates")[0]
                if check_updates == 1:
                    logger.info("Auto-update check enabled, checking for updates...")
                    check_for_updates(silent=True)
        except (OSError, ImportError, Exception) as e:
            # If registry key doesn't exist or other error, default to checking for updates
            logger.debug(f"Error checking update preferences, defaulting to check: {e}")
            check_for_updates(silent=True)

    command_map = {
        "init": init_command,
        "start": start_command,
        "tray": tray_command,
        "version": version_command,
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