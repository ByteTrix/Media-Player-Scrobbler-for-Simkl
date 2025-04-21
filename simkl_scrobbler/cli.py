"""
Command-Line Interface (CLI) for the Simkl Scrobbler application.

Provides commands for initialization, starting/stopping the service,
managing the background service, and checking status.
"""
import argparse
import sys
import colorama
import subprocess
import logging
from colorama import Fore, Style

# Version information 
VERSION = "1.0.0"  

# Quick version check before importing all dependencies
# This prevents dependency errors when just checking version
if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v", "version"]:
    print(f"Simkl Scrobbler v{VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    sys.exit(0)

# Only import other modules when not just checking version
from .simkl_api import authenticate
from .credentials import get_credentials, get_env_file_path
from .main import SimklScrobbler, APP_DATA_DIR # Import APP_DATA_DIR for log path display
from .tray_app import run_tray_app
from .service_manager import install_service, uninstall_service, service_status

# Initialize colorama for colored terminal output
colorama.init()
logger = logging.getLogger(__name__)

# Version information retrieval with fallbacks
def get_version():
    """Get version information dynamically, falling back to hardcoded value if needed."""
    # Method 1: Check for __version__ in package __init__.py
    try:
        from simkl_scrobbler import __version__
        return __version__
    except (ImportError, AttributeError):
        pass
    
    # Method 2: Use importlib.metadata (Python 3.8+)
    try:
        import importlib.metadata
        return importlib.metadata.version('simkl-movie-tracker')
    except (ImportError, importlib.metadata.PackageNotFoundError):
        pass
    
    # We're no longer using pkg_resources since it causes issues on some systems
    # Return the hardcoded version instead
    return VERSION

def _check_prerequisites(check_token=True, check_client_id=True):
    """Helper function to check if credentials exist before running a command."""
    env_path = get_env_file_path()
    creds = get_credentials()
    error = False
    if check_client_id and not creds.get("client_id"):
        print(f"{Fore.RED}ERROR: Client ID is missing. Application build might be corrupted. Please reinstall.{Style.RESET_ALL}", file=sys.stderr)
        error = True
    if check_token and not creds.get("access_token"):
        print(f"{Fore.RED}ERROR: Access Token not found in '{env_path}'. Please run 'simkl-scrobbler init' first.{Style.RESET_ALL}", file=sys.stderr)
        error = True
    return not error

def init_command(args):
    """
    Handles the 'init' command.

    Checks existing credentials, performs OAuth device flow if necessary,
    and saves the access token. Verifies the final configuration.
    """
    print(f"{Fore.CYAN}=== Simkl Scrobbler Initialization ==={Style.RESET_ALL}")
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
        # Authentication process (user interaction handled by authenticate function)
        new_access_token = authenticate(client_id)

        if not new_access_token:
            logger.error("Authentication process failed or was cancelled.")
            print(f"{Fore.RED}ERROR: Authentication failed or was cancelled.{Style.RESET_ALL}", file=sys.stderr)
            return 1

        logger.info("Authentication successful, saving new access token.")
        print(f"\n[*] Saving new access token to: {env_path}")
        try:
            # Ensure parent directory exists
            env_path.parent.mkdir(parents=True, exist_ok=True)
            with open(env_path, "w", encoding='utf-8') as env_file:
                # Add a comment indicating the source
                env_file.write("# Simkl Access Token obtained via 'simkl-scrobbler init'\n")
                env_file.write(f"SIMKL_ACCESS_TOKEN={new_access_token}\n")
            logger.info(f"Access token successfully saved to {env_path}.")
            print(f"{Fore.GREEN}[✓] Access token saved successfully.{Style.RESET_ALL}")
            # Update variable for verification step
            access_token = new_access_token
        except IOError as e:
            logger.exception(f"Failed to save access token to {env_path}: {e}")
            print(f"{Fore.RED}ERROR: Failed to save access token: {e}{Style.RESET_ALL}", file=sys.stderr)
            return 1

    # Verification step
    print(f"\n[*] Verifying application configuration...")
    logger.info("Verifying configuration by initializing SimklScrobbler instance.")
    verifier_scrobbler = SimklScrobbler()
    if not verifier_scrobbler.initialize():
         logger.error("Configuration verification failed after initialization attempt.")
         print(f"{Fore.RED}ERROR: Configuration verification failed. Check logs for details: {APP_DATA_DIR / 'simkl_scrobbler.log'}{Style.RESET_ALL}", file=sys.stderr)
         print(f"{Fore.YELLOW}Hint: If the token seems valid but verification fails, check Simkl API status or report a bug.{Style.RESET_ALL}")
         return 1

    logger.info("Initialization and verification successful.")
    print(f"\n{Fore.GREEN}========================================={Style.RESET_ALL}")
    print(f"{Fore.GREEN}✓ Initialization Complete!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}========================================={Style.RESET_ALL}")
    print(f"\n[*] To start monitoring and scrobbling, run:")
    print(f"    {Fore.WHITE}simkl-scrobbler start{Style.RESET_ALL}")
    return 0

def start_command(args):
    """
    Handles the 'start' command.

    Installs the application as a startup service (if possible) and
    launches the tray application in a detached background process.
    """
    print(f"{Fore.CYAN}=== Starting Simkl Scrobbler ==={Style.RESET_ALL}")
    logger.info("Executing start command.")
    if not _check_prerequisites(): return 1

    # Attempt service installation
    print("[*] Ensuring background service is installed for auto-startup...")
    logger.info("Attempting to install/verify startup service.")
    try:
        success = install_service()
        if success:
            logger.info("Startup service installed or already present.")
            print(f"{Fore.GREEN}[✓] Startup service installed/verified.{Style.RESET_ALL}")
        else:
            # Log as warning, but proceed with launching tray app anyway
            logger.warning("Failed to install startup service (non-critical).")
            print(f"{Fore.YELLOW}[!] Warning: Failed to install as a startup service. Scrobbler will run but won't start automatically on boot.{Style.RESET_ALL}")
    except Exception as e:
        logger.exception(f"Error during startup service installation: {e}")
        print(f"{Fore.YELLOW}[!] Warning: Error installing startup service: {e}. Scrobbler will run but won't start automatically on boot.{Style.RESET_ALL}")

    # Launch tray app in background
    print("[*] Launching application with tray icon in background...")
    logger.info("Launching tray application in detached process.")
    try:
        # Determine command based on execution context (frozen/script)
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, "tray"]
            logger.debug("Launching frozen executable for tray.")
        else:
            cmd = [sys.executable, "-m", "simkl_scrobbler.tray_app"]
            logger.debug("Launching tray via python module.")

        # Platform-specific detached process creation
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True, shell=False)
            logger.info("Launched detached process on Windows.")
        else: # Assume Unix-like
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
            logger.info("Launched detached process on Unix-like system.")

        print(f"{Fore.GREEN}[✓] Scrobbler launched successfully in background.{Style.RESET_ALL}")
        print(f"[*] Look for the Simkl Scrobbler icon in your system tray.")
        return 0
    except Exception as e:
        logger.exception(f"Failed to launch detached tray process: {e}")
        print(f"{Fore.RED}ERROR: Failed to launch application in background: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def tray_command(args):
    """
    Handles the 'tray' command.

    Runs the application with a system tray icon directly in the foreground
    (or background if launched internally with --detach).
    """
    logger.info("Executing tray command.")
    # Internal check for detached mode (used by start_command)
    detached_mode = hasattr(args, 'detach') and args.detach
    if not detached_mode:
        print(f"{Fore.CYAN}=== Starting Simkl Scrobbler (Tray Mode) ==={Style.RESET_ALL}")
        if not _check_prerequisites(): return 1
        print(f"{Fore.YELLOW}[!] Running in foreground. Closing this terminal will stop the application.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[!] Use 'simkl-scrobbler start' to run persistently in the background.{Style.RESET_ALL}")
    else:
         # If detached, prerequisites should have been checked by start_command
         logger.info("Running tray command in detached mode (internal call).")


    print("[*] Launching application with system tray icon...")
    try:
        run_tray_app() # This function blocks until the tray app exits
        logger.info("Tray application exited normally.")
        return 0
    except KeyboardInterrupt:
        logger.info("Tray application interrupted by user (KeyboardInterrupt).")
        print(f"\n{Fore.YELLOW}[!] Tray application stopped.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        logger.exception(f"Error running tray application: {e}")
        print(f"{Fore.RED}ERROR: Failed to start tray application: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def service_command(args):
    """
    Handles the 'service' command (potentially deprecated).

    Launches the scrobbler core logic in a detached background process
    without a tray icon.
    """
    # Note: This command might be less useful now that 'start' handles
    # service installation and launches the tray app. Consider removal.
    print(f"{Fore.CYAN}=== Starting Simkl Scrobbler (Background Service Mode) ==={Style.RESET_ALL}")
    logger.warning("Executing potentially deprecated 'service' command.")
    if not _check_prerequisites(): return 1

    print("[*] Launching background service process (no tray icon)...")
    logger.info("Launching service runner in detached process.")
    try:
        if getattr(sys, 'frozen', False):
            start_args = [sys.executable, "service-run"] # Assuming a dedicated entry point if frozen
            logger.debug("Launching frozen executable for service runner.")
        else:
            start_args = [sys.executable, "-m", "simkl_scrobbler.service_runner"]
            logger.debug("Launching service runner via python module.")

        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(start_args, creationflags=CREATE_NO_WINDOW, close_fds=True, shell=False)
            logger.info("Launched detached service process on Windows.")
        else:
            subprocess.Popen(start_args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
            logger.info("Launched detached service process on Unix-like system.")

        print(f"{Fore.GREEN}[✓] Background service process started successfully.{Style.RESET_ALL}")
        print(f"[*] Check logs for activity: {APP_DATA_DIR / 'simkl_scrobbler.log'}")
        return 0
    except Exception as e:
        logger.exception(f"Failed to launch background service process: {e}")
        print(f"{Fore.RED}ERROR: Failed to start background service: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def install_service_command(args):
    """Handles the 'install-service' command."""
    print(f"{Fore.CYAN}=== Simkl Scrobbler Service Installation ==={Style.RESET_ALL}")
    logger.info("Executing install-service command.")
    # Check token prerequisite - service needs it to run later
    if not _check_prerequisites(check_token=True, check_client_id=False): return 1

    print("[*] Attempting to install the application as a system startup service...")
    try:
        success = install_service()
        if success:
            logger.info("Startup service installed successfully.")
            print(f"{Fore.GREEN}[✓] Service installed successfully! It will run automatically on system startup.{Style.RESET_ALL}")
            return 0
        else:
            logger.error("Service installation failed (install_service returned False).")
            print(f"{Fore.RED}ERROR: Failed to install the service. Check logs or permissions.{Style.RESET_ALL}", file=sys.stderr)
            return 1
    except Exception as e:
        logger.exception(f"Error during service installation: {e}")
        print(f"{Fore.RED}ERROR: An unexpected error occurred during service installation: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def uninstall_service_command(args):
    """Handles the 'uninstall-service' command."""
    print(f"{Fore.CYAN}=== Simkl Scrobbler Service Uninstallation ==={Style.RESET_ALL}")
    logger.info("Executing uninstall-service command.")

    print("[*] Attempting to uninstall the system startup service...")
    try:
        success = uninstall_service()
        if success:
            logger.info("Startup service uninstalled successfully.")
            print(f"{Fore.GREEN}[✓] Service uninstalled successfully!{Style.RESET_ALL}")
            return 0
        else:
            logger.error("Service uninstallation failed (uninstall_service returned False).")
            print(f"{Fore.RED}ERROR: Failed to uninstall the service. It might not have been installed.{Style.RESET_ALL}", file=sys.stderr)
            return 1 # Indicate failure, even if it wasn't installed
    except Exception as e:
        logger.exception(f"Error during service uninstallation: {e}")
        print(f"{Fore.RED}ERROR: An unexpected error occurred during service uninstallation: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def service_status_command(args):
    """Handles the 'service-status' command."""
    print(f"{Fore.CYAN}=== Simkl Scrobbler Service Status ==={Style.RESET_ALL}")
    logger.info("Executing service-status command.")

    print("[*] Checking status of the system startup service...")
    try:
        status = service_status()
        logger.info(f"Service status check returned: {status}")
        if status is True:
            print(f"{Fore.GREEN}[✓] Service is installed, configured for startup, and appears to be running.{Style.RESET_ALL}")
        elif status == "CONFIGURED" or status == "LOADED":
             print(f"{Fore.YELLOW}[!] Service is installed and configured for startup, but is not currently running.{Style.RESET_ALL}")
             print(f"[*] You can try starting it manually or restarting your computer.")
        else: # False or other string indicates not installed/configured
             print(f"{Fore.YELLOW}[!] Service is not installed or not configured for startup.{Style.RESET_ALL}")
             print(f"[*] Use 'simkl-scrobbler install-service' to install it.")
        return 0
    except Exception as e:
        logger.exception(f"Error checking service status: {e}")
        print(f"{Fore.RED}ERROR: An unexpected error occurred while checking service status: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def version_command(args):
    """Displays version information about the application."""
    print(f"{Fore.CYAN}=== Simkl Scrobbler Version Information ==={Style.RESET_ALL}")
    logger.info(f"Displaying version information: {VERSION}")
    
    print(f"Simkl Scrobbler v{VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    
    # Display whether running as frozen executable or from source
    if getattr(sys, 'frozen', False):
        print(f"Installation: Packaged executable")
        print(f"Executable: {sys.executable}")
    else:
        print(f"Installation: Running from source")
    
    print(f"\nData directory: {APP_DATA_DIR}")
    return 0

def create_parser():
    """
    Creates and configures the argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Simkl Scrobbler: Automatically scrobble movie watch history to Simkl.",
        formatter_class=argparse.RawTextHelpFormatter # Preserve help text formatting
    )
    
    # Add version option directly to main parser
    parser.add_argument("--version", "-v", action="store_true", 
                       help="Display version information and exit")
                       
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True) # Make command required

    # --- Init Command ---
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize or re-authenticate the scrobbler with your Simkl account."
    )

    # --- Start Command ---
    start_parser = subparsers.add_parser(
        "start",
        help="Recommended: Install as startup service & run scrobbler in background with tray icon."
    )

    # --- Tray Command ---
    tray_parser = subparsers.add_parser(
        "tray",
        help="Run scrobbler with tray icon (stops when terminal closes)."
    )
    # Hidden internal argument for detaching process
    tray_parser.add_argument("--detach", action="store_true", help=argparse.SUPPRESS)

    # --- Service Management Commands ---
    install_parser = subparsers.add_parser(
        "install-service",
        help="Install the scrobbler as a system service to run automatically on startup."
    )
    uninstall_parser = subparsers.add_parser(
        "uninstall-service",
        help="Uninstall the system startup service."
    )
    status_parser = subparsers.add_parser(
        "service-status",
        help="Check the status of the system startup service."
    )
    
    # --- Version Command ---
    version_parser = subparsers.add_parser(
        "version",
        help="Display version information about the application."
    )
    
    # --- Service Command (Potentially Deprecated) ---
    # service_parser = subparsers.add_parser(
    #     "service",
    #     help="Run scrobbler as background process without tray icon (use 'start' instead)."
    # )

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
    
    # Check for version flag directly
    if getattr(args, 'version', False):
        return version_command(args)
    
    # If no command provided, show help
    if not hasattr(args, 'command') or not args.command:
        parser.print_help()
        return 0

    # Map command strings to functions - organized by command category
    command_map = {
        # Setup commands
        "init": init_command,
        
        # Runtime commands
        "start": start_command,
        "tray": tray_command,
        
        # Service management commands
        "install-service": install_service_command,
        "uninstall-service": uninstall_service_command,
        "service-status": service_status_command,
        
        # Utility commands
        "version": version_command,
        
        # Deprecated/disabled commands
        # "service": service_command,
    }

    # Execute the selected command
    if args.command in command_map:
        try:
            logger.info(f"Executing command: {args.command}")
            exit_code = command_map[args.command](args)
            logger.info(f"Command '{args.command}' finished with exit code {exit_code}.")
            return exit_code
        except Exception as e:
            # Catch unexpected errors in command functions
            logger.exception(f"Unhandled exception during command '{args.command}': {e}")
            print(f"\n{Fore.RED}UNEXPECTED ERROR: An error occurred during the '{args.command}' command.{Style.RESET_ALL}", file=sys.stderr)
            print(f"{Fore.RED}Details: {e}{Style.RESET_ALL}", file=sys.stderr)
            print(f"{Fore.YELLOW}Please check the log file for more information: {APP_DATA_DIR / 'simkl_scrobbler.log'}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    else:
        # Should not happen if subparsers are required, but good practice
        logger.error(f"Unknown command received: {args.command}")
        parser.print_help()
        return 1

if __name__ == "__main__":
    # Ensure the script exits with the code returned by main()
    sys.exit(main())