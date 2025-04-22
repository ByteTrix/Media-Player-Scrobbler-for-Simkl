"""
Command-Line Interface (CLI) for the Simkl Scrobbler application.

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

# Version information - will be replaced by dynamic detection
VERSION = "1.0.0"  # Default fallback version

# Function to get version dynamically - called early
def get_version():
    """Get version information dynamically, using modern approaches."""
    # Method 1: Use importlib.metadata (Python 3.8+) - most modern approach
    try:
        # Try both possible package names
        for pkg_name in ['simkl-mps', 'simkl_mps']:
            try:
                return importlib.metadata.version(pkg_name)
            except importlib.metadata.PackageNotFoundError:
                pass
    except (ImportError, AttributeError):
        pass
    
    # Method 2: Check if we're running from a Git repository
    try:
        import subprocess
        try:
            # Try to get version from git describe
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
    
    # Method 3: Check for __version__ in package __init__.py
    try:
        from simkl_mps import __version__
        return __version__
    except (ImportError, AttributeError):
        pass
    
    # Method 4: Check for a version file in the package
    try:
        # Determine the package directory
        import simkl_mps
        pkg_dir = Path(simkl_mps.__file__).parent
        version_file = pkg_dir / 'VERSION'
        if version_file.exists():
            return version_file.read_text().strip()
    except (ImportError, AttributeError, OSError):
        pass
    
    # Return the hardcoded version as last resort
    return VERSION

# Get version dynamically at startup
VERSION = get_version()

# Quick version check before importing all dependencies
# This prevents dependency errors when just checking version
if len(sys.argv) > 1 and sys.argv[1] in ["--version", "-v", "version"]:
    print(f"Simkl Scrobbler v{VERSION}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    sys.exit(0)

# Only import other modules when not just checking version
from simkl_mps.simkl_api import authenticate
from simkl_mps.credentials import get_credentials, get_env_file_path
from simkl_mps.main import SimklScrobbler, APP_DATA_DIR # Import APP_DATA_DIR for log path display
from simkl_mps.tray_app import run_tray_app
from simkl_mps.service_manager import install_service, uninstall_service, service_status

# Initialize colorama for colored terminal output
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
                env_file.write("# Simkl Access Token obtained via 'simkl-mps init'\n")
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
    print(f"{Fore.CYAN}=== Starting Simkl Scrobbler ==={Style.RESET_ALL}")
    logger.info("Executing start command.")
    # Try prerequisites, if missing access token, run init automatically
    if not _check_prerequisites():
        print(f"{Fore.YELLOW}[!] No access token found. Running initialization...{Style.RESET_ALL}")
        init_result = init_command(args)
        if init_result != 0:
            print(f"{Fore.RED}ERROR: Initialization failed. Cannot start application.{Style.RESET_ALL}", file=sys.stderr)
            return 1
        # After successful init, check prerequisites again
        if not _check_prerequisites():
            print(f"{Fore.RED}ERROR: Still missing credentials after initialization. Aborting start.{Style.RESET_ALL}", file=sys.stderr)
            return 1

    if os.environ.get("SIMKL_TRAY_SUBPROCESS") == "1":
        logger.info("Detected we're in the tray subprocess - running tray app directly")
        print("Running tray application directly...")
        from simkl_mps.tray_app import run_tray_app
        sys.exit(run_tray_app())


    # Attempt service installation and starting
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
            print(f"{Fore.YELLOW}WARNING: Failed to install startup service (non-critical).{Style.RESET_ALL}")
    except Exception as e:
        logger.exception(f"Error during startup service installation: {e}")
        print(f"{Fore.YELLOW}ERROR: Failed to install Windows service: {e}{Style.RESET_ALL}")

    # Launch tray app in background
    print("[*] Launching application with tray icon in background...")
    logger.info("Launching tray application in detached process.")
    try:
        # Determine command based on execution context (frozen/script)
        if getattr(sys, 'frozen', False):
            # Get the directory where the executable is located
            exe_dir = Path(sys.executable).parent
            # Use the dedicated tray executable we created in the build spec
            tray_exe = exe_dir / "simkl-mps-tray.exe"
            if tray_exe.exists():
                cmd = [str(tray_exe)]
                logger.debug(f"Launching dedicated tray executable: {tray_exe}")
            else:
                # Fallback to passing 'tray' as argument to main executable
                cmd = [sys.executable, "tray"]
                logger.debug("Launching frozen executable for tray (fallback method).")
        else:
            cmd = [sys.executable, "-m", "simkl_mps.tray_app"]
            logger.debug("Launching tray via python module.")

        # Platform-specific detached process creation
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Create environment with subprocess marker to prevent recursion
            env = os.environ.copy()
            env["SIMKL_TRAY_SUBPROCESS"] = "1"  # Mark this as a subprocess
            
            subprocess.Popen(
                cmd, 
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, 
                close_fds=True, 
                shell=False,
                startupinfo=startupinfo,
                env=env  # Pass the environment with our marker
            )
            logger.info("Launched detached process on Windows.")
        else: # Assume Unix-like
            # Create environment with subprocess marker
            env = os.environ.copy()
            env["SIMKL_TRAY_SUBPROCESS"] = "1"  # Mark this as a subprocess
            
            subprocess.Popen(
                cmd, 
                start_new_session=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL, 
                close_fds=True, 
                shell=False,
                env=env  # Pass the environment with our marker
            )
            logger.info("Launched detached process on Unix-like system.")

        print(f"{Fore.GREEN}[✓] Scrobbler launched successfully in background.{Style.RESET_ALL}")
        print(f"[*] Look for the Simkl Scrobbler icon in your system tray.")
        print(f"{Fore.GREEN}[✓] You can safely close this terminal window. All processes will continue running.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        logger.exception(f"Failed to launch detached tray process: {e}")
        print(f"{Fore.RED}ERROR: Failed to launch application in background: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def tray_command(args):
    """
    Handles the 'tray' command.

    Runs ONLY the tray application in a detached process.
    Does NOT install or start the background service.
    Closing terminal won't affect the tray app.
    """
    print(f"{Fore.CYAN}=== Starting Simkl Scrobbler (Tray Only Mode) ==={Style.RESET_ALL}")
    logger.info("Executing tray command.")
    if not _check_prerequisites(): return 1

    # CRITICAL CHECK: Prevent recursive launching
    # If we're already running in a detached process (a child process), just run the tray directly
    # This is identified by an environment variable we'll set
    if os.environ.get("SIMKL_TRAY_SUBPROCESS") == "1":
        logger.info("Detected we're in the tray subprocess - running tray app directly")
        print("Running tray application directly...")
        from simkl_mps.tray_app import run_tray_app
        sys.exit(run_tray_app())
    
    print("[*] Launching tray application in background (without service)...")
    try:
        # Determine command based on execution context (frozen/script)
        if getattr(sys, 'frozen', False):
            # Get the directory where the executable is located
            exe_dir = Path(sys.executable).parent
            # Use the dedicated tray executable we created in the build spec
            tray_exe = exe_dir / "simkl-mps-tray.exe"
            if tray_exe.exists():
                cmd = [str(tray_exe)]
                logger.debug(f"Launching dedicated tray executable: {tray_exe}")
            else:
                # Fallback to passing 'tray' as argument to main executable
                # BUT we need to set an environment variable to prevent recursion
                cmd = [sys.executable, "tray"]
                env = os.environ.copy()
                env["SIMKL_TRAY_SUBPROCESS"] = "1"  # Mark this as a subprocess
                logger.debug("Launching frozen executable for tray (fallback method).")
        else:
            cmd = [sys.executable, "-m", "simkl_mps.tray_app"]
            logger.debug("Launching tray via python module.")

        # Platform-specific detached process creation
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Create environment with subprocess marker
            env = os.environ.copy()
            env["SIMKL_TRAY_SUBPROCESS"] = "1"  # Mark this as a subprocess
            
            subprocess.Popen(
                cmd, 
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, 
                close_fds=True, 
                shell=False,
                startupinfo=startupinfo,
                env=env  # Pass the environment with our marker
            )
            logger.info("Launched detached tray process on Windows.")
        else: # Assume Unix-like
            # Create environment with subprocess marker
            env = os.environ.copy()
            env["SIMKL_TRAY_SUBPROCESS"] = "1"  # Mark this as a subprocess
            
            subprocess.Popen(
                cmd, 
                start_new_session=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL, 
                close_fds=True, 
                shell=False,
                env=env  # Pass the environment with our marker
            )
            logger.info("Launched detached tray process on Unix-like system.")

        print(f"{Fore.GREEN}[✓] Tray application launched successfully in background.{Style.RESET_ALL}")
        print(f"[*] Look for the Simkl Scrobbler icon in your system tray.")
        print(f"{Fore.YELLOW}[!] Note: Only the tray app is running. No background service was installed.{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[✓] You can safely close this terminal window. The tray app will continue running.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        logger.exception(f"Failed to launch detached tray process: {e}")
        print(f"{Fore.RED}ERROR: Failed to launch tray application: {e}{Style.RESET_ALL}", file=sys.stderr)
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
            start_args = [sys.executable, "-m", "simkl_mps.service_runner"]
            logger.debug("Launching service runner via python module.")

        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(start_args, creationflags=CREATE_NO_WINDOW, close_fds=True, shell=False)
            logger.info("Launched detached service process on Windows.")
        else:
            subprocess.Popen(start_args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
            logger.info("Launched detached service process on Unix-like system.")

        print(f"{Fore.GREEN}[✓] Background service process started successfully.{Style.RESET_ALL}")
        print(f"[*] Check logs for activity: {APP_DATA_DIR / 'simkl-mps.log'}")
        return 0
    except Exception as e:
        logger.exception(f"Failed to launch background service process: {e}")
        print(f"{Fore.RED}ERROR: Failed to start background service: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def install_service_command(args):
    """
    Handles the 'install-service' command.
    
    ONLY installs the background service - does not start the tray app.
    """
    print(f"{Fore.CYAN}=== Simkl Scrobbler Service Installation ==={Style.RESET_ALL}")
    logger.info("Executing install-service command.")
    # Check token prerequisite - service needs it to run later
    if not _check_prerequisites(check_token=True, check_client_id=False): return 1

    print("[*] Installing the application as a system startup service...")
    try:
        success = install_service()
        if success:
            logger.info("Startup service installed successfully.")
            print(f"{Fore.GREEN}[✓] Service installed successfully! It will run automatically on system startup.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[!] Note: This command only installed the service. Use 'simkl-mps start' to run the application now.{Style.RESET_ALL}")
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
    """
    Handles the 'uninstall-service' command.
    
    ONLY uninstalls the background service.
    """
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
             print(f"[*] Use 'simkl-mps install-service' to install it.")
        return 0
    except Exception as e:
        logger.exception(f"Error checking service status: {e}")
        print(f"{Fore.RED}ERROR: An unexpected error occurred while checking service status: {e}{Style.RESET_ALL}", file=sys.stderr)
        return 1

def version_command(args):
    """
    Displays version information about the application.
    
    Shows the current installed version of simkl-mps.
    """
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
        help="Run ALL components (background service + tray icon). Terminal can be closed."
    )

    # --- Tray Command ---
    tray_parser = subparsers.add_parser(
        "tray",
        help="Run ONLY tray icon (no background service). Terminal can be closed."
    )

    # --- Service Management Commands ---
    install_parser = subparsers.add_parser(
        "install-service",
        help="ONLY install the background service (no tray icon). Does not start anything."
    )
    uninstall_parser = subparsers.add_parser(
        "uninstall-service",
        help="ONLY uninstall the background service."
    )
    status_parser = subparsers.add_parser(
        "service-status",
        help="Check the status of the background service."
    )
    
    # --- Version Command ---
    version_parser = subparsers.add_parser(
        "version",
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
            print(f"{Fore.YELLOW}Please check the log file for more information: {APP_DATA_DIR / 'simkl-mps.log'}{Style.RESET_ALL}", file=sys.stderr)
            return 1
    else:
        # Should not happen if subparsers are required, but good practice
        logger.error(f"Unknown command received: {args.command}")
        parser.print_help()
        return 1

if __name__ == "__main__":
    # Ensure the script exits with the code returned by main()
    sys.exit(main())