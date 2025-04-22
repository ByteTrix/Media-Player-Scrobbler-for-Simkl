"""
Service manager for SIMKL Scrobbler.
Provides functionality to install and manage the scrobbler as a system service.
"""

import os
import sys
import platform
import logging
import shutil
import pathlib
import textwrap
import subprocess
from string import Template

logger = logging.getLogger(__name__)

# Detect platform
PLATFORM = platform.system().lower()

# Templates for service files
SYSTEMD_SERVICE_TEMPLATE = Template("""
[Unit]
Description=SIMKL Scrobbler Service
After=network.target

[Service]
Type=simple
User=$user
ExecStart=$python_path -m simkl_mps.service_runner
WorkingDirectory=$working_dir
Restart=on-failure
RestartSec=5s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
""")

LAUNCHD_PLIST_TEMPLATE = Template("""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kavinthangavel.simklscrobbler</string>
    <key>ProgramArguments</key>
    <array>
        <string>$python_path</string>
        <string>-m</string>
        <string>simkl_mps.service_runner</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$working_dir</string>
    <key>StandardErrorPath</key>
    <string>$log_dir/simkl-mps.err</string>
    <key>StandardOutPath</key>
    <string>$log_dir/simkl-mps.out</string>
</dict>
</plist>
""")

WINDOWS_SERVICE_BATCH_TEMPLATE = Template("""@echo off
"%PYTHONPATH%" -m simkl_mps.service_runner
""")

def safe_file_operations(func):
    """Decorator to safely handle file operations with retries and proper cleanup"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_delay = 1.0
        last_exception = None
        
        # Try to kill any processes that might be locking files
        kill_existing_processes()
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except (PermissionError, OSError) as e:
                last_exception = e
                logger.warning(f"Permission error on attempt {attempt+1}/{max_retries}: {e}")
                
                # Force terminate any processes that might be locking files
                kill_existing_processes(force=True)
                
                # Small delay before retry
                import time
                time.sleep(retry_delay)
                
                # Try to reset file permissions
                if PLATFORM == "windows" and len(args) > 0 and isinstance(args[0], (str, pathlib.Path)):
                    try:
                        path = str(args[0])
                        if os.path.exists(path):
                            subprocess.run(["attrib", "-r", "-s", "-h", path], shell=True, check=False)
                    except Exception:
                        pass
        
        # If all retries failed, log and re-raise the last exception
        logger.error(f"Operation failed after {max_retries} attempts: {last_exception}")
        raise last_exception
    
    return wrapper

def service_exists():
    """Check if the service is already installed"""
    if (PLATFORM == "windows"):
        return check_windows_service_exists()
    elif (PLATFORM == "linux"):
        return check_linux_service_exists()
    elif (PLATFORM == "darwin"):  # macOS
        return check_macos_service_exists()
    else:
        logger.error(f"Unsupported platform: {PLATFORM}")
        return False

def check_windows_service_exists():
    """Check if the Windows service already exists"""
    # Check registry
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, "SimklScrobbler")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
    except ImportError:
        pass
    
    # Check startup folder
    startup_dir = pathlib.Path(os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"))
    startup_link = startup_dir / "SimklScrobbler.bat"
    if startup_link.exists():
        return True
    
    # Check service directory
    from .main import APP_DATA_DIR
    batch_path = APP_DATA_DIR / "service" / "simkl-mps_service.bat"
    if batch_path.exists():
        return True
    
    return False

def check_linux_service_exists():
    """Check if the Linux service already exists"""
    user_service_path = pathlib.Path.home() / ".config/systemd/user/simkl-mps.service"
    system_service_path = pathlib.Path("/etc/systemd/system/simkl-mps.service")
    
    return user_service_path.exists() or system_service_path.exists()

def check_macos_service_exists():
    """Check if the macOS service already exists"""
    plist_path = pathlib.Path.home() / "Library/LaunchAgents/com.kavinthangavel.simklscrobbler.plist"
    return plist_path.exists()

def install_service():
    """Install SIMKL Scrobbler as a system service that starts at boot"""
    logger.info(f"Installing service on {PLATFORM} platform")
    
    # Check for env file
    from .main import APP_DATA_DIR
    env_path = APP_DATA_DIR / ".simkl-mps.env"
    if not env_path.exists():
        logger.error("Cannot install service: No credentials found")
        return False
    
    # Check if service already exists and remove it
    if service_exists():
        logger.info("Service already exists. Removing before reinstallation.")
        uninstall_service()
    
    if PLATFORM == "windows":
        return install_windows_service()
    elif PLATFORM == "linux":
        return install_linux_service()
    elif PLATFORM == "darwin":  # macOS
        return install_macos_service()
    else:
        logger.error(f"Unsupported platform: {PLATFORM}")
        return False

def install_windows_service():
    """Install as a Windows service or startup item"""
    try:
        # Get necessary paths
        python_path = sys.executable
        from .main import APP_DATA_DIR
        
        # Create service directory if needed
        service_dir = APP_DATA_DIR / "service"
        os.makedirs(service_dir, exist_ok=True)
        
        # Create batch file for the service
        batch_path = service_dir / "simkl-mps_service.bat"
        
        # Make sure we can write to the file by removing it first if it exists
        if batch_path.exists():
            safe_remove_file(batch_path)
        
        # Create with safer method
        batch_content = WINDOWS_SERVICE_BATCH_TEMPLATE.substitute(
            PYTHONPATH=python_path
        )
        
        # Write with explicit file close to prevent lock issues
        try:
            with open(batch_path, "w") as f:
                f.write(batch_content)
        except (PermissionError, OSError) as e:
            logger.error(f"Cannot write to batch file (permissions issue): {e}")
            # Try with a different approach
            with open(batch_path, "w", opener=lambda path, flags: os.open(path, flags | os.O_CREAT | os.O_WRONLY)) as f:
                f.write(batch_content)
        
        # Make batch file executable with better error handling
        if PLATFORM == "windows":
            try:
                # Use shell=True to better handle Windows paths
                subprocess.run(["attrib", "-r", "+a", str(batch_path)], check=False, shell=True)
            except Exception as e:
                logger.warning(f"Could not set file attributes, but continuing: {e}")
        else:
            try:
                os.chmod(batch_path, 0o755)
            except Exception as e:
                logger.warning(f"Could not set file permissions, but continuing: {e}")
        
        # Add to Windows startup via registry with better error handling
        startup_success = False
        try:
            import winreg
            # Open Windows registry key for startup programs
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            
            # Add our service to startup
            winreg.SetValueEx(
                key, 
                "SimklScrobbler",
                0, 
                winreg.REG_SZ, 
                str(batch_path)
            )
            winreg.CloseKey(key)
            logger.info("Added service to Windows startup via registry")
            startup_success = True
        except (ImportError, OSError, PermissionError) as e:
            logger.warning(f"Could not add to registry: {e}")
            
            # If registry method failed, try alternative
            if not startup_success:
                try:
                    startup_dir = pathlib.Path(os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"))
                    startup_link = startup_dir / "SimklScrobbler.bat"
                    
                    # Remove existing file first
                    if startup_link.exists():
                        safe_remove_file(startup_link)
                    
                    # Create shortcut to the batch file
                    shutil.copy(str(batch_path), str(startup_link))
                    logger.info(f"Added service to Windows startup folder: {startup_link}")
                    startup_success = True
                except Exception as e:
                    logger.error(f"Failed to add to startup folder: {e}")
        
        if not startup_success:
            logger.warning("Could not set up automatic startup, but batch file was created")
        
        # Start the service right away with better error handling
        try:
            # Make sure any existing processes are terminated
            kill_existing_processes()
            
            # Use different approach with better error handling
            startupinfo = None
            if hasattr(subprocess, 'STARTUPINFO'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            subprocess.Popen(
                [str(batch_path)],
                shell=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                close_fds=True
            )
            logger.info("Service started successfully")
        except Exception as e:
            logger.error(f"Error starting service: {e}")
            # Continue since installation succeeded
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to install Windows service: {e}")
        return False

def kill_existing_processes(force=False):
    """Kill any existing media player scrobbler for simkl service processes"""
    try:
        import psutil
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any('simkl_mps.service_runner' in cmd for cmd in cmdline):
                    logger.info(f"Terminating existing process: {proc.pid}")
                    if force:
                        proc.kill()  # Force kill
                    else:
                        proc.terminate()  # Graceful termination
                    
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        if not force:
                            logger.warning(f"Process {proc.pid} didn't terminate in time, force killing")
                            proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
    except ImportError:
        logger.warning("psutil not available, can't terminate existing processes")

@safe_file_operations
def safe_remove_file(file_path):
    """Safely remove a file with proper error handling"""
    path = pathlib.Path(file_path)
    if path.exists():
        # On Windows, make sure file is not read-only before deletion
        if PLATFORM == "windows":
            try:
                subprocess.run(["attrib", "-r", str(path)], shell=True, check=False)
            except Exception as e:
                logger.debug(f"Failed to reset file attributes: {e}")
        
        try:
            os.unlink(path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {path}: {e}")
            raise
    return True  # File didn't exist, which is fine

def install_linux_service():
    """Install as a systemd service on Linux"""
    try:
        # Get current user and Python path
        current_user = os.getlogin()
        python_path = sys.executable
        from .main import APP_DATA_DIR
        
        # Determine service file location (user or system)
        user_systemd_dir = pathlib.Path.home() / ".config/systemd/user"
        system_service_dir = pathlib.Path("/etc/systemd/system")
        
        # Check if we can write to system directory (requires root)
        if os.access(system_service_dir, os.W_OK):
            service_dir = system_service_dir
            user_mode = False
        else:
            # Use user systemd directory
            service_dir = user_systemd_dir
            user_systemd_dir.mkdir(parents=True, exist_ok=True)
            user_mode = True
        
        # Create service file content
        service_path = service_dir / "simkl-mps.service"
        service_content = SYSTEMD_SERVICE_TEMPLATE.substitute(
            user=current_user,
            python_path=python_path,
            working_dir=str(pathlib.Path.home())
        )
        
        # Write systemd service file
        with open(service_path, "w") as f:
            f.write(service_content.strip())
        
        # Set permissions
        os.chmod(service_path, 0o644)
        
        # Enable and start the service
        if user_mode:
            # User mode systemd commands
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "simkl-mps.service"], check=True)
            subprocess.run(["systemctl", "--user", "start", "simkl-mps.service"], check=True)
            logger.info("User systemd service installed successfully")
        else:
            # System mode systemd commands
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "enable", "simkl-mps.service"], check=True)
            subprocess.run(["systemctl", "start", "simkl-mps.service"], check=True)
            logger.info("System systemd service installed successfully")
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to install Linux service: {e}")
        return False

def install_macos_service():
    """Install as a LaunchAgent on macOS"""
    try:
        # Create LaunchAgent directory if it doesn't exist
        launch_agents_dir = pathlib.Path.home() / "Library/LaunchAgents"
        launch_agents_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log directory
        from .main import APP_DATA_DIR
        log_dir = APP_DATA_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create plist file
        plist_path = launch_agents_dir / "com.kavinthangavel.simklscrobbler.plist"
        plist_content = LAUNCHD_PLIST_TEMPLATE.substitute(
            python_path=sys.executable,
            working_dir=str(pathlib.Path.home()),
            log_dir=str(log_dir)
        )
        
        # Write the plist file
        with open(plist_path, "w") as f:
            f.write(plist_content.strip())
        
        # Set correct permissions
        os.chmod(plist_path, 0o644)
        
        # Load the launch agent
        try:
            # Unload first in case it's already loaded
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            # Load the agent
            subprocess.run(["launchctl", "load", "-w", str(plist_path)], check=True)
            logger.info("macOS LaunchAgent installed and loaded successfully")
        except subprocess.SubprocessError as e:
            logger.error(f"Error loading LaunchAgent: {e}")
            # Continue since file was created successfully
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to install macOS service: {e}")
        return False

def uninstall_service():
    """Uninstall the service based on platform"""
    if PLATFORM == "windows":
        return uninstall_windows_service()
    elif PLATFORM == "linux":
        return uninstall_linux_service()
    elif PLATFORM == "darwin":  # macOS
        return uninstall_macos_service()
    else:
        logger.error(f"Unsupported platform: {PLATFORM}")
        return False

def uninstall_windows_service():
    """Uninstall from Windows startup"""
    try:
        # Make sure any existing processes are terminated
        kill_existing_processes()
        
        # Remove from registry
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            try:
                winreg.DeleteValue(key, "SimklScrobbler")
            except FileNotFoundError:
                # Key doesn't exist, which is fine
                pass
            winreg.CloseKey(key)
        except ImportError:
            pass
        
        # Also try to remove from startup folder with better error handling
        try:
            startup_dir = pathlib.Path(os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"))
            startup_link = startup_dir / "SimklScrobbler.bat"
            if startup_link.exists():
                safe_remove_file(startup_link)
        except Exception as e:
            logger.warning(f"Failed to remove startup shortcut: {e}")
        
        # Clean up service directory with better error handling
        try:
            from .main import APP_DATA_DIR
            service_dir = APP_DATA_DIR / "service"
            batch_path = service_dir / "simkl-mps_service.bat"
            if batch_path.exists():
                safe_remove_file(batch_path)
        except Exception as e:
            logger.warning(f"Failed to remove batch file: {e}")
        
        logger.info("Windows service uninstalled successfully")
        return True
    
    except Exception as e:
        logger.error(f"Failed to uninstall Windows service: {e}")
        return False

def uninstall_linux_service():
    """Uninstall Linux systemd service"""
    try:
        # Check user service first
        user_service_path = pathlib.Path.home() / ".config/systemd/user/simkl-mps.service"
        if user_service_path.exists():
            # Stop and disable user service
            subprocess.run(["systemctl", "--user", "stop", "simkl-mps.service"], check=False)
            subprocess.run(["systemctl", "--user", "disable", "simkl-mps.service"], check=False)
            os.unlink(user_service_path)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        else:
            # Try system service
            system_service_path = pathlib.Path("/etc/systemd/system/simkl-mps.service")
            if os.access(system_service_path, os.W_OK):
                subprocess.run(["systemctl", "stop", "simkl-mps.service"], check=False)
                subprocess.run(["systemctl", "disable", "simkl-mps.service"], check=False)
                os.unlink(system_service_path)
                subprocess.run(["systemctl", "daemon-reload"], check=True)
        
        logger.info("Linux service uninstalled successfully")
        return True
    
    except Exception as e:
        logger.error(f"Failed to uninstall Linux service: {e}")
        return False

def uninstall_macos_service():
    """Uninstall macOS LaunchAgent"""
    try:
        plist_path = pathlib.Path.home() / "Library/LaunchAgents/com.kavinthangavel.simklscrobbler.plist"
        if plist_path.exists():
            # Unload and remove the agent
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            os.unlink(plist_path)
            logger.info("macOS LaunchAgent uninstalled successfully")
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to uninstall macOS service: {e}")
        return False

def service_status():
    """Check the status of the service"""
    if PLATFORM == "windows":
        return check_windows_service_status()
    elif PLATFORM == "linux":
        return check_linux_service_status()
    elif PLATFORM == "darwin":
        return check_macos_service_status()
    else:
        logger.error(f"Unsupported platform: {PLATFORM}")
        return False

def check_windows_service_status():
    """Check if the Windows service is running"""
    try:
        # Get current running processes
        import psutil
        
        # Check if our service process is running
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any('simkl_mps.service_runner' in cmd for cmd in cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return False
    except ImportError:
        # Fallback method if psutil is not available
        try:
            # Check registry if service is in startup
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run", 
                0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, "SimklScrobbler")
                winreg.CloseKey(key)
                # Registry key exists, but we can't tell if it's running
                return "CONFIGURED"  # Special status
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except ImportError:
            # Very basic fallback - just check if batch file exists
            from .main import APP_DATA_DIR
            batch_path = APP_DATA_DIR / "service" / "simkl-mps_service.bat"
            return batch_path.exists()

def check_linux_service_status():
    """Check if the Linux service is running"""
    try:
        # Check user service first
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "simkl-mps.service"],
            capture_output=True, text=True, check=False
        )
        if "active" in result.stdout:
            return True
        
        # Then check system service
        result = subprocess.run(
            ["systemctl", "is-active", "simkl-mps.service"],
            capture_output=True, text=True, check=False
        )
        return "active" in result.stdout
    
    except Exception:
        # Fallback - check for process
        try:
            import psutil
            for proc in psutil.process_iter(['cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any('simkl_mps.service_runner' in cmd for cmd in cmdline):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return False
        except ImportError:
            # If we can't check properly, return unknown
            return False

def check_macos_service_status():
    """Check if the macOS service is running"""
    try:
        # Check if the service is loaded
        result = subprocess.run(
            ["launchctl", "list", "com.kavinthangavel.simklscrobbler"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            # Service is loaded, but we should check if it's actually running
            try:
                import psutil
                for proc in psutil.process_iter(['cmdline']):
                    try:
                        cmdline = proc.info['cmdline']
                        if cmdline and any('simkl_mps.service_runner' in cmd for cmd in cmdline):
                            return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                # LaunchAgent is loaded but process isn't running (might be in error state)
                return "LOADED"  # Special status
            except ImportError:
                # Can't check process, so just report that it's loaded
                return True
        return False
    
    except Exception:
        # Fallback - check for plist file existence
        plist_path = pathlib.Path.home() / "Library/LaunchAgents/com.kavinthangavel.simklscrobbler.plist"
        if plist_path.exists():
            return "CONFIGURED"  # It's configured but we can't determine running status
        return False
