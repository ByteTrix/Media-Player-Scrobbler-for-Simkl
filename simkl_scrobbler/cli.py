import argparse
import os
import sys
import pathlib
import colorama
import subprocess
from colorama import Fore, Style
from dotenv import load_dotenv
from .simkl_api import authenticate, DEFAULT_CLIENT_ID
from .main import APP_DATA_DIR, SimklScrobbler
from .tray_app import run_tray_app
from .service_manager import install_service, uninstall_service, service_status
import logging

# Initialize colorama for cross-platform colored terminal output
colorama.init()

logger = logging.getLogger(__name__)

def init_command(args):
    """Initialize the SIMKL Scrobbler with user configuration."""
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Initialization ==={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}This will set up SIMKL Scrobbler on your system.{Style.RESET_ALL}\n")
    
    # DEFAULT_CLIENT_ID imported at top

    # Define env path
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
    client_id = None
    access_token = None

    # Check if .env file exists and load it
    if env_path.exists():
        print(f"{Fore.YELLOW}Found existing configuration file: {env_path}{Style.RESET_ALL}")
        load_dotenv(env_path)
        client_id = os.getenv("SIMKL_CLIENT_ID")
        access_token = os.getenv("SIMKL_ACCESS_TOKEN")

    # Check if credentials are valid
    if client_id and access_token:
        print(f"{Fore.GREEN}✓ Existing credentials loaded successfully.{Style.RESET_ALL}")
        # Optionally add a check here to verify token validity with Simkl API if needed
        # For now, assume they are valid if present.
        print(f"{Fore.YELLOW}Skipping authentication as credentials already exist.{Style.RESET_ALL}")
        # Use existing credentials
    else:
        if env_path.exists():
            print(f"{Fore.YELLOW}Existing configuration file is incomplete or invalid.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}No existing configuration file found.{Style.RESET_ALL}")

        # Use the embedded client ID by default for new authentication
        client_id = DEFAULT_CLIENT_ID
        print(f"\n{Fore.CYAN}Using application client ID: {client_id[:8]}...{client_id[-8:]}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}You'll need to authenticate with your Simkl account.{Style.RESET_ALL}")
        print("This will allow the application to track your watched movies.")
        print()

        # Authenticate with SIMKL using the embedded client ID
        print(f"\n{Fore.CYAN}Authenticating with SIMKL...{Style.RESET_ALL}")
        access_token = authenticate(client_id)

        if not access_token:
            print(f"{Fore.RED}Authentication failed. Please try again.{Style.RESET_ALL}")
            return 1

        # Save the newly obtained credentials
        print(f"\n{Fore.CYAN}Saving new credentials...{Style.RESET_ALL}")
        # Ensure the directory exists (though main.py should also do this)
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Write credentials to the correct path, specifying encoding
        with open(env_path, "w", encoding='utf-8') as env_file:
            env_file.write(f"SIMKL_CLIENT_ID={client_id}\n")
            env_file.write(f"SIMKL_ACCESS_TOKEN={access_token}\n")
        print(f"{Fore.GREEN}Successfully saved credentials to {env_path}{Style.RESET_ALL}")

    # --- Verification Step (remains the same) ---
    
    # Initialize the main scrobbler class to verify configuration properly
    print(f"\n{Fore.CYAN}Verifying configuration...{Style.RESET_ALL}")
    # Use the main SimklScrobbler class which handles loading config from the correct path
    # It will use the credentials loaded/saved above
    verifier_scrobbler = SimklScrobbler()
    if not verifier_scrobbler.initialize():
         print(f"{Fore.RED}Configuration verification failed. Check logs for details.{Style.RESET_ALL}")
         # If verification fails with existing token, maybe prompt to re-init?
         print(f"{Fore.YELLOW}Hint: If the token expired, run 'simkl-scrobbler init' again to re-authenticate.{Style.RESET_ALL}")
         return 1
    
    print(f"\n{Fore.GREEN}✓ SIMKL Scrobbler has been successfully configured!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}✓ Your personal Simkl account is now connected!{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}Supported media players:{Style.RESET_ALL}")
    print("- VLC Media Player")
    print("- MPC-HC")
    print("- Windows Media Player")
    print("- MPV")
    print("- And other popular media players")
    
    print(f"\n{Fore.CYAN}To start scrobbling your movies, run:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}simkl-scrobbler start{Style.RESET_ALL}")
    
    return 0

def start_command(args):
    """Start the SIMKL scrobbler as a persistent process with tray that survives terminal close."""
    # Check if credentials exist
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
    if not env_path.exists():
        print(f"{Fore.RED}No credentials found. Please run 'simkl-scrobbler init' first.{Style.RESET_ALL}")
        return 1
    
    print(f"{Fore.CYAN}Starting SIMKL Scrobbler...{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Installing as a background service that runs at system startup...{Style.RESET_ALL}")
    
    # First, install the service for automatic startup
    try:
        from .service_manager import install_service
        success = install_service()
        if success:
            print(f"{Fore.GREEN}Successfully installed SIMKL Scrobbler as a startup service!{Style.RESET_ALL}")
            print(f"{Fore.GREEN}The service will automatically start when you boot your computer.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}Warning: Failed to install as a startup service. The application will still run but won't start automatically at boot.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Error installing startup service: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}The application will still run but won't start automatically at boot.{Style.RESET_ALL}")

    # Launch the tray application in a detached process
    print(f"{Fore.CYAN}Launching SIMKL Scrobbler with tray icon in a persistent background process...{Style.RESET_ALL}")
    print(f"{Fore.GREEN}The application will continue running even after closing this terminal.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Look for the SIMKL icon in your system tray.{Style.RESET_ALL}")
    
    try:
        # Get current script path and arguments to launch tray app in a separate process
        if getattr(sys, 'frozen', False):
            # If bundled with PyInstaller
            cmd = [sys.executable, "tray"]
        else:
            # If running as a Python module
            cmd = [sys.executable, "-m", "simkl_scrobbler.tray_app"]
        
        # Launch the process in a way that it survives the terminal closing
        if sys.platform == "win32":
            # Windows - use CREATE_NO_WINDOW flag to hide console window and DETACHED_PROCESS to detach
            import subprocess
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            process = subprocess.Popen(
                cmd,
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                close_fds=True,
                shell=False
            )
        else:
            # Unix-like systems
            import subprocess
            process = subprocess.Popen(
                cmd,
                start_new_session=True,  # Detach from the terminal
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                shell=False
            )
        
        print(f"{Fore.GREEN}Scrobbler launched successfully in background mode.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}You can close this terminal and the application will continue running.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error launching detached process: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Falling back to foreground mode (will not survive terminal close).{Style.RESET_ALL}")
        try:
            # Run the tray application directly as fallback
            from .tray_app import run_tray_app
            run_tray_app()
            return 0
        except Exception as tray_error:
            print(f"{Fore.RED}Error starting tray application: {tray_error}{Style.RESET_ALL}")
            return 1

def run_foreground_scrobbler():
    """Run the scrobbler in foreground mode (fallback for start command)"""
    print(f"{Fore.YELLOW}Running scrobbler in foreground mode. Press Ctrl+C to stop.{Style.RESET_ALL}")
    
    scrobbler = SimklScrobbler()
    if scrobbler.initialize():
        if scrobbler.start():
            try:
                print(f"{Fore.GREEN}Scrobbler is now running. Press Ctrl+C to stop.{Style.RESET_ALL}")
                # Keep the main thread running until interrupted
                while scrobbler.running:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Stopping scrobbler...{Style.RESET_ALL}")
                scrobbler.stop()
                print(f"{Fore.GREEN}Scrobbler stopped.{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Failed to start scrobbler. See logs for details.{Style.RESET_ALL}")
            return 1
    else:
        print(f"{Fore.RED}Failed to initialize scrobbler. Please run 'simkl-scrobbler init' first.{Style.RESET_ALL}")
        return 1
    
    return 0

def tray_command(args):
    """Start the SIMKL scrobbler in system tray mode (without startup service)."""
    # Check if credentials exist - use the same path as in init_command
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
    if not env_path.exists():
        print(f"{Fore.RED}No credentials found. Please run 'simkl-scrobbler init' first.{Style.RESET_ALL}")
        return 1
    
    # Check if --detach flag is provided
    detached_mode = hasattr(args, 'detach') and args.detach
    
    if not detached_mode:
        print(f"{Fore.GREEN}Starting SIMKL Scrobbler in system tray mode...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Warning: Closing this terminal will stop the application.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Use 'simkl-scrobbler start' to run in permanent background mode.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Look for the SIMKL icon in your system tray.{Style.RESET_ALL}")
    
    try:
        # Run the tray application
        run_tray_app()
        return 0
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}SIMKL Scrobbler tray application interrupted.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error starting tray application: {e}{Style.RESET_ALL}")
        return 1

def service_command(args):
    """Run the SIMKL scrobbler as a background service without tray icon."""
    # Check if credentials exist
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"
    if not env_path.exists():
        print(f"{Fore.RED}No credentials found. Please run 'simkl-scrobbler init' first.{Style.RESET_ALL}")
        return 1
    
    print(f"{Fore.CYAN}Starting SIMKL Scrobbler as a background service...{Style.RESET_ALL}")
    print(f"{Fore.GREEN}The scrobbler will run in the background without a tray icon.{Style.RESET_ALL}")
    print(f"{Fore.GREEN}The service will continue running even after closing this terminal.{Style.RESET_ALL}")
    
    # Start in detached mode
    try:
        # Get current script path
        if getattr(sys, 'frozen', False):
            script_path = sys.executable
            start_args = [script_path, "service-run"]
        else:
            python_exe = sys.executable
            start_args = [python_exe, "-m", "simkl_scrobbler.service_runner"]
        
        # Create detached process
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            process = subprocess.Popen(
                start_args,
                creationflags=CREATE_NO_WINDOW,
                close_fds=True,
                shell=False
            )
        else:
            process = subprocess.Popen(
                start_args,
                start_new_session=True,  # Detach from the terminal
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                shell=False
            )
        
        print(f"{Fore.GREEN}Service started successfully in background.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}You'll receive notifications for scrobbled movies.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Check logs at: {APP_DATA_DIR / 'simkl_scrobbler.log'}{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error starting service in background: {e}{Style.RESET_ALL}")
        return 1

def install_service_command(args):
    """Install SIMKL scrobbler as a background service that runs at startup."""
    # Check if credentials exist
    env_path = APP_DATA_DIR / ".simkl_scrobbler.env"  # Fixed from .env to .simkl_scrobbler.env
    if not env_path.exists():
        print(f"{Fore.RED}No credentials found. Please run 'simkl-scrobbler init' first.{Style.RESET_ALL}")
        return 1
    
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Service Installation ==={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Installing SIMKL Scrobbler as a system service that runs at startup...{Style.RESET_ALL}")
    
    try:
        success = install_service()
        if success:
            print(f"{Fore.GREEN}Service installed successfully!{Style.RESET_ALL}")
            print(f"{Fore.CYAN}The service is now running and will start automatically when you boot your computer.{Style.RESET_ALL}")
            return 0
        else:
            print(f"{Fore.RED}Failed to install service.{Style.RESET_ALL}")
            return 1
    except Exception as e:
        print(f"{Fore.RED}Error installing service: {e}{Style.RESET_ALL}")
        return 1

def uninstall_service_command(args):
    """Uninstall SIMKL scrobbler background service."""
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Service Uninstallation ==={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Uninstalling SIMKL Scrobbler service...{Style.RESET_ALL}")
    
    try:
        success = uninstall_service()
        if success:
            print(f"{Fore.GREEN}Service uninstalled successfully!{Style.RESET_ALL}")
            return 0
        else:
            print(f"{Fore.RED}Failed to uninstall service.{Style.RESET_ALL}")
            return 1
    except Exception as e:
        print(f"{Fore.RED}Error uninstalling service: {e}{Style.RESET_ALL}")
        return 1

def service_status_command(args):
    """Check the status of the SIMKL scrobbler service."""
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Service Status ==={Style.RESET_ALL}")
    
    try:
        status = service_status()
        if status is True:
            print(f"{Fore.GREEN}SIMKL Scrobbler service is running and configured to start at boot.{Style.RESET_ALL}")
            return 0
        elif status == "CONFIGURED" or status == "LOADED":
            print(f"{Fore.YELLOW}SIMKL Scrobbler service is configured to start at boot but might not be running now.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Try restarting your computer or run 'simkl-scrobbler start' to start it again.{Style.RESET_ALL}")
            return 0
        else:
            print(f"{Fore.YELLOW}SIMKL Scrobbler service is not running.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Run 'simkl-scrobbler install-service' to install it as a system service.{Style.RESET_ALL}")
            return 0
    except Exception as e:
        print(f"{Fore.RED}Error checking service status: {e}{Style.RESET_ALL}")
        return 1

def create_parser():
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="SIMKL Scrobbler - Automatically scrobble movies to SIMKL"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize SIMKL Scrobbler")
    
    # Start command - now installs and runs as a startup service
    start_parser = subparsers.add_parser("start", help="Install and start SIMKL Scrobbler as a startup service")
    
    # Tray command - stays the same, but with warning about terminal closure
    tray_parser = subparsers.add_parser("tray", help="Start in system tray mode (stops when terminal closes)")
    tray_parser.add_argument("--detach", action="store_true", help=argparse.SUPPRESS)  # Hidden option, used internally
    
    # Service commands
    install_service_parser = subparsers.add_parser("install-service", help="Install as a startup service (runs at boot)")
    uninstall_service_parser = subparsers.add_parser("uninstall-service", help="Uninstall the startup service")
    service_status_parser = subparsers.add_parser("service-status", help="Check the status of the service")
    
    return parser

def main():
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.command == "init":
        return init_command(args)
    elif args.command == "start":
        return start_command(args)
    elif args.command == "tray":
        return tray_command(args)
    elif args.command == "service":
        return service_command(args)
    elif args.command == "install-service":
        return install_service_command(args)
    elif args.command == "uninstall-service":
        return uninstall_service_command(args)
    elif args.command == "service-status":
        return service_status_command(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())