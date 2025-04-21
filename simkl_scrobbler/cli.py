import argparse
import sys
import colorama
import subprocess
from colorama import Fore, Style
from .simkl_api import authenticate
from .credentials import get_credentials, get_env_file_path
from .main import SimklScrobbler, APP_DATA_DIR # Import APP_DATA_DIR for log path display
from .tray_app import run_tray_app
from .service_manager import install_service, uninstall_service, service_status
import logging
import time # Needed for sleep in run_foreground_scrobbler if kept

colorama.init()
logger = logging.getLogger(__name__)


def init_command(args):
    print(f"{Fore.CYAN}=== SIMKL Scrobbler Initialization ==={Style.RESET_ALL}")
    env_path = get_env_file_path()
    print(f"{Fore.CYAN}Using configuration file for Access Token: {env_path}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Loading credentials...{Style.RESET_ALL}")
    creds = get_credentials()
    client_id = creds.get("client_id")
    access_token = creds.get("access_token")

    if not client_id or not creds.get("client_secret"):
        print(f"{Fore.RED}Error: Client ID or Secret not found (build issue?).{Style.RESET_ALL}")
        return 1
    else:
        print(f"{Fore.GREEN}✓ Client ID/Secret loaded (from build).{Style.RESET_ALL}")

    if access_token:
        print(f"{Fore.GREEN}✓ Access Token found in {env_path}.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Skipping authentication.{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}Access Token not found. Starting authentication...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Using Client ID: {client_id[:8]}...{client_id[-8:]}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Authenticate with Simkl account to allow tracking.{Style.RESET_ALL}\n")
        new_access_token = authenticate(client_id)

        if not new_access_token:
            print(f"{Fore.RED}Authentication failed.{Style.RESET_ALL}")
            return 1

        print(f"\n{Fore.CYAN}Saving new access token to {env_path}...{Style.RESET_ALL}")
        try:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            with open(env_path, "w", encoding='utf-8') as env_file:
                env_file.write(f"SIMKL_ACCESS_TOKEN={new_access_token}\n")
            print(f"{Fore.GREEN}Successfully saved access token.{Style.RESET_ALL}")
            access_token = new_access_token
        except IOError as e:
            print(f"{Fore.RED}Error saving access token: {e}{Style.RESET_ALL}")
            return 1

    print(f"\n{Fore.CYAN}Verifying configuration...{Style.RESET_ALL}")
    verifier_scrobbler = SimklScrobbler()
    if not verifier_scrobbler.initialize():
         print(f"{Fore.RED}Configuration verification failed.{Style.RESET_ALL}")
         print(f"{Fore.YELLOW}Hint: If token expired, run 'init' again.{Style.RESET_ALL}")
         return 1

    print(f"\n{Fore.GREEN}✓ Configuration successful!{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}To start scrobbling, run:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}simkl-scrobbler start{Style.RESET_ALL}")
    return 0

def start_command(args):
    env_path = get_env_file_path()
    creds = get_credentials()
    if not creds.get("access_token"):
        print(f"{Fore.RED}Access Token missing ({env_path}). Run 'init' first.{Style.RESET_ALL}")
        return 1
    if not creds.get("client_id"):
         print(f"{Fore.RED}Client ID missing (build issue?). Reinstall.{Style.RESET_ALL}")
         return 1

    print(f"{Fore.CYAN}Starting SIMKL Scrobbler...{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Attempting to install as a startup service...{Style.RESET_ALL}")
    try:
        success = install_service()
        if success: print(f"{Fore.GREEN}Startup service installed/verified.{Style.RESET_ALL}")
        else: print(f"{Fore.YELLOW}Warning: Failed to install startup service.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Error installing startup service: {e}{Style.RESET_ALL}")

    print(f"{Fore.CYAN}Launching tray icon in background...{Style.RESET_ALL}")
    try:
        if getattr(sys, 'frozen', False): cmd = [sys.executable, "tray"]
        else: cmd = [sys.executable, "-m", "simkl_scrobbler.tray_app"]

        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True, shell=False)
        else:
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
        print(f"{Fore.GREEN}Scrobbler launched in background. Look for tray icon.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error launching background process: {e}{Style.RESET_ALL}")
        # Fallback removed as per request to minimize code
        # print(f"{Fore.YELLOW}Try running 'simkl-scrobbler tray' directly.{Style.RESET_ALL}")
        return 1

# run_foreground_scrobbler function removed

def tray_command(args):
    env_path = get_env_file_path()
    creds = get_credentials()
    if not creds.get("access_token"):
        print(f"{Fore.RED}Access Token missing ({env_path}). Run 'init' first.{Style.RESET_ALL}")
        return 1
    if not creds.get("client_id"):
         print(f"{Fore.RED}Client ID missing (build issue?). Reinstall.{Style.RESET_ALL}")
         return 1

    detached_mode = hasattr(args, 'detach') and args.detach
    if not detached_mode:
        print(f"{Fore.GREEN}Starting tray mode...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Warning: Closing terminal stops app. Use 'start' for background.{Style.RESET_ALL}")

    try:
        run_tray_app()
        return 0
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Tray application interrupted.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error starting tray application: {e}{Style.RESET_ALL}")
        return 1

def service_command(args):
    # This command might be redundant now if 'start' handles service installation/launch
    # Keeping it minimal for now, but consider removing if unused.
    env_path = get_env_file_path()
    creds = get_credentials()
    if not creds.get("access_token"):
        print(f"{Fore.RED}Access Token missing ({env_path}). Run 'init' first.{Style.RESET_ALL}")
        return 1
    if not creds.get("client_id"):
         print(f"{Fore.RED}Client ID missing (build issue?). Reinstall.{Style.RESET_ALL}")
         return 1

    print(f"{Fore.CYAN}Starting background service (no tray)...{Style.RESET_ALL}")
    try:
        if getattr(sys, 'frozen', False): start_args = [sys.executable, "service-run"]
        else: start_args = [sys.executable, "-m", "simkl_scrobbler.service_runner"]

        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(start_args, creationflags=CREATE_NO_WINDOW, close_fds=True, shell=False)
        else:
            subprocess.Popen(start_args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
        print(f"{Fore.GREEN}Service started in background.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Logs: {APP_DATA_DIR / 'simkl_scrobbler.log'}{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error starting background service: {e}{Style.RESET_ALL}")
        return 1

def install_service_command(args):
    env_path = get_env_file_path()
    creds = get_credentials()
    if not creds.get("access_token"):
        print(f"{Fore.RED}Access Token missing ({env_path}). Run 'init' first.{Style.RESET_ALL}")
        return 1
    if not creds.get("client_id"):
         print(f"{Fore.RED}Client ID missing (build issue?). Reinstall.{Style.RESET_ALL}")
         return 1

    print(f"{Fore.CYAN}=== Service Installation ==={Style.RESET_ALL}")
    try:
        success = install_service()
        if success: print(f"{Fore.GREEN}Service installed successfully!{Style.RESET_ALL}")
        else: print(f"{Fore.RED}Failed to install service.{Style.RESET_ALL}"); return 1
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error installing service: {e}{Style.RESET_ALL}")
        return 1

def uninstall_service_command(args):
    print(f"{Fore.CYAN}=== Service Uninstallation ==={Style.RESET_ALL}")
    try:
        success = uninstall_service()
        if success: print(f"{Fore.GREEN}Service uninstalled successfully!{Style.RESET_ALL}")
        else: print(f"{Fore.RED}Failed to uninstall service.{Style.RESET_ALL}"); return 1
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error uninstalling service: {e}{Style.RESET_ALL}")
        return 1

def service_status_command(args):
    print(f"{Fore.CYAN}=== Service Status ==={Style.RESET_ALL}")
    try:
        status = service_status()
        if status is True: print(f"{Fore.GREEN}Service is running and configured for startup.{Style.RESET_ALL}")
        elif status == "CONFIGURED" or status == "LOADED": print(f"{Fore.YELLOW}Service configured for startup but not running.{Style.RESET_ALL}")
        else: print(f"{Fore.YELLOW}Service is not running or installed.{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print(f"{Fore.RED}Error checking service status: {e}{Style.RESET_ALL}")
        return 1

def create_parser():
    parser = argparse.ArgumentParser(description="SIMKL Scrobbler")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    subparsers.add_parser("init", help="Initialize/Authenticate SIMKL Scrobbler")
    subparsers.add_parser("start", help="Install as startup service & run in background (tray icon)")
    tray_parser = subparsers.add_parser("tray", help="Run with tray icon (stops when terminal closes)")
    tray_parser.add_argument("--detach", action="store_true", help=argparse.SUPPRESS)
    # subparsers.add_parser("service", help="Run as background service (no tray icon)") # Potentially redundant
    subparsers.add_parser("install-service", help="Install as a startup service")
    subparsers.add_parser("uninstall-service", help="Uninstall the startup service")
    subparsers.add_parser("service-status", help="Check status of the startup service")
    return parser

def main():
    parser = create_parser()
    args = parser.parse_args()
    command_map = {
        "init": init_command,
        "start": start_command,
        "tray": tray_command,
        "service": service_command, # Keep for now, but might remove later
        "install-service": install_service_command,
        "uninstall-service": uninstall_service_command,
        "service-status": service_status_command,
    }
    if args.command in command_map:
        return command_map[args.command](args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())