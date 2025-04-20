import argparse
import os
import sys
import pathlib # Import pathlib
import colorama
from colorama import Fore, Style
from dotenv import load_dotenv # Import load_dotenv
from .simkl_api import authenticate, DEFAULT_CLIENT_ID # Moved DEFAULT_CLIENT_ID import here
# Import APP_DATA_DIR from main module
from .main import APP_DATA_DIR, SimklScrobbler # Import SimklScrobbler too for verification step
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
    """Start the SIMKL scrobbler."""
    # SimklScrobbler imported at top
    
    print(f"{Fore.CYAN}Starting SIMKL Scrobbler...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}The scrobbler will run in the foreground. Press Ctrl+C to stop.{Style.RESET_ALL}\n")
    
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

def install_service_command(args):
    """Install SIMKL scrobbler as a background service."""
    if sys.platform != 'win32':
        print(f"{Fore.RED}Service installation is only supported on Windows.{Style.RESET_ALL}")
        return 1
    
    try:
        import win32service
        import win32serviceutil
        import servicemanager
        import win32event
        import win32api
    except ImportError:
        print(f"{Fore.RED}Error: pywin32 module is required for service installation.{Style.RESET_ALL}")
        print("Please run: pip install pywin32")
        return 1
    
    # Get current script path
    script_path = os.path.abspath(sys.argv[0])
    
    # Instructions for manual service creation
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Service Installation ==={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}To install as a Windows service, run the following commands as administrator:{Style.RESET_ALL}\n")
    
    print(f"{Fore.WHITE}sc create SimklScrobbler binPath= \"{sys.executable} {script_path} service\" DisplayName= \"SIMKL Scrobbler\" start= auto{Style.RESET_ALL}")
    print(f"{Fore.WHITE}sc description SimklScrobbler \"Automatically scrobbles movies to SIMKL\"{Style.RESET_ALL}")
    print(f"{Fore.WHITE}sc start SimklScrobbler{Style.RESET_ALL}")
    
    print(f"\n{Fore.GREEN}After installation, the service will start automatically when you boot your computer.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Make sure to run 'simkl-scrobbler init' before starting the service.{Style.RESET_ALL}")
    
    return 0

def create_parser():
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="SIMKL Scrobbler - Automatically scrobble movies to SIMKL"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize SIMKL Scrobbler")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start SIMKL Scrobbler")
    
    # Service installation command
    service_parser = subparsers.add_parser("install-service", help="Install as a Windows service")
    
    return parser

def main():
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.command == "init":
        return init_command(args)
    elif args.command == "start":
        return start_command(args)
    elif args.command == "install-service":
        return install_service_command(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())