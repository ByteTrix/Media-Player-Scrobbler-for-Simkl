import argparse
import os
import sys
import colorama
from colorama import Fore, Style
from .simkl_api import authenticate
from .media_tracker import MonitorAwareScrobbler
import logging

# Initialize colorama for cross-platform colored terminal output
colorama.init()

logger = logging.getLogger(__name__)

def init_command(args):
    """Initialize the SIMKL Scrobbler with user configuration."""
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Initialization ==={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}This will set up SIMKL Scrobbler on your system.{Style.RESET_ALL}\n")
    
    # Import the default client ID from simkl_api module
    from .simkl_api import DEFAULT_CLIENT_ID
    
    # Use the embedded client ID by default
    client_id = DEFAULT_CLIENT_ID
    
    print(f"{Fore.CYAN}Using application client ID: {client_id[:8]}...{client_id[-8:]}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}You'll need to authenticate with your own Simkl account.{Style.RESET_ALL}")
    print("This will allow the application to track your watched movies.")
    print()
    
    # Authenticate with SIMKL using the embedded client ID
    print(f"\n{Fore.CYAN}Authenticating with SIMKL...{Style.RESET_ALL}")
    
    access_token = authenticate(client_id)
    
    if not access_token:
        print(f"{Fore.RED}Authentication failed. Please try again.{Style.RESET_ALL}")
        return 1
    
    # Create/update .env file with credentials
    env_path = os.path.join(os.path.expanduser("~"), ".simkl_scrobbler.env")
    
    with open(env_path, "w") as env_file:
        env_file.write(f"SIMKL_CLIENT_ID={client_id}\n")
        env_file.write(f"SIMKL_ACCESS_TOKEN={access_token}\n")
    
    print(f"\n{Fore.GREEN}Successfully saved credentials to {env_path}{Style.RESET_ALL}")
    
    # Initialize the scrobbler to verify configuration
    print(f"\n{Fore.CYAN}Verifying configuration...{Style.RESET_ALL}")
    scrobbler = MonitorAwareScrobbler()
    scrobbler.set_credentials(client_id, access_token)
    
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
    from .main import SimklScrobbler
    
    print(f"{Fore.CYAN}Starting SIMKL Scrobbler...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}The scrobbler will run in the foreground. Press Ctrl+C to stop.{Style.RESET_ALL}\n")
    
    scrobbler = SimklScrobbler()
    if scrobbler.initialize():
        scrobbler.start()
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