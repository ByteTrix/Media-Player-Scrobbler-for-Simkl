import json
import logging
import os
import platform
import socket
import sys
import time
from configparser import ConfigParser, NoOptionError, NoSectionError
from pathlib import Path
from threading import Lock

# Conditional imports
if platform.system() == "Windows":
    try:
        import win32pipe
        import win32file
        import pywintypes
        WINDOWS_IMPORT_SUCCESS = True
    except ImportError:
        WINDOWS_IMPORT_SUCCESS = False
else:  # POSIX (Linux/macOS)
    import select
    WINDOWS_IMPORT_SUCCESS = False  # Not applicable

logger = logging.getLogger(__name__)

# Default MPV IPC path names
DEFAULT_IPC_PATH_POSIX = "/tmp/mpvsocket"
DEFAULT_IPC_PATH_WINDOWS = r"\\.\pipe\mpvsocket"

# Constants
MPV_TIMEOUT = 3.0  # Longer timeout for better reliability
MIN_READ_INTERVAL = 0.01  # Small interval between read attempts

class MPVError(Exception):
    """Custom exception for MPV integration errors."""
    pass

class MPVIntegration:
    """
    Class for interacting with MPV via its IPC interface.
    """
    name = 'mpv'

    def __init__(self):
        self.platform = platform.system()
        self.ipc_path = self._find_ipc_path()
        self.connection = None
        self.ipc_lock = Lock()  # Ensure only one command runs at a time
        self.request_id_counter = 1
        logger.info(f"MPV Integration initialized. IPC Path: {self.ipc_path}")

    def _find_mpv_config_path(self) -> Path | None:
        """Find the path to the mpv configuration file."""
        if self.platform == "Windows":
            # Standard location on Windows
            appdata = os.getenv('APPDATA')
            if appdata:
                conf_path = Path(appdata) / "mpv" / "mpv.conf"
                if conf_path.exists():
                    logger.debug(f"Found MPV config at: {conf_path}")
                    return conf_path
            # Portable config location
            exe_path = Path(sys.executable).parent
            portable_conf = exe_path / "portable_config" / "mpv.conf"
            if portable_conf.exists():
                logger.debug(f"Found portable MPV config at: {portable_conf}")
                return portable_conf
            portable_conf_alt = exe_path / "mpv.conf"
            if portable_conf_alt.exists():
                logger.debug(f"Found portable MPV config at: {portable_conf_alt}")
                return portable_conf_alt

        elif self.platform == "Darwin":  # macOS
            conf_path = Path.home() / ".config" / "mpv" / "mpv.conf"
            if conf_path.exists():
                logger.debug(f"Found MPV config at: {conf_path}")
                return conf_path
        else:  # Linux/Unix
            conf_path = Path.home() / ".config" / "mpv" / "mpv.conf"
            if conf_path.exists():
                logger.debug(f"Found MPV config at: {conf_path}")
                return conf_path
            # Check XDG_CONFIG_HOME
            xdg_config_home = os.getenv('XDG_CONFIG_HOME')
            if xdg_config_home:
                conf_path = Path(xdg_config_home) / "mpv" / "mpv.conf"
                if conf_path.exists():
                    logger.debug(f"Found MPV config at: {conf_path}")
                    return conf_path

        logger.debug("MPV config file not found in standard locations.")
        return None

    def _read_ipc_path(self) -> str | None:
        """Read the input-ipc-server path from mpv.conf."""
        conf_path = self._find_mpv_config_path()
        if not conf_path:
            return None

        try:
            content = conf_path.read_text(encoding='utf-8')
            
            # Simple line-by-line parsing for 'input-ipc-server' option
            for line in content.splitlines():
                line = line.strip()
                if line.startswith('#') or line.startswith(';'):
                    continue  # Skip comments
                
                if line.startswith('input-ipc-server='):
                    value = line.split('=', 1)[1].strip()
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    logger.debug(f"Found input-ipc-server={value} in {conf_path}")
                    return value

            logger.debug(f"'input-ipc-server' not found in {conf_path}")
            return None

        except Exception as e:
            logger.error(f"Error reading MPV config file {conf_path}: {e}", exc_info=True)
            return None

    def _find_ipc_path(self) -> str:
        """Determine the IPC path to use."""
        config_path = self._read_ipc_path()
        if config_path:
            return config_path

        # Fallback to defaults
        if self.platform == "Windows":
            logger.debug(f"Using default Windows IPC path: {DEFAULT_IPC_PATH_WINDOWS}")
            return DEFAULT_IPC_PATH_WINDOWS
        else:
            logger.debug(f"Using default POSIX IPC path: {DEFAULT_IPC_PATH_POSIX}")
            return DEFAULT_IPC_PATH_POSIX

    def _connect(self):
        """Establish connection to the MPV IPC interface."""
        if self.connection:
            return  # Already connected

        try:
            if self.platform == "Windows":
                if not WINDOWS_IMPORT_SUCCESS:
                    raise MPVError("Windows IPC requires pywin32. Please install it.")
                
                # Create file with timeout handling
                try:
                    handle = win32file.CreateFile(
                        self.ipc_path,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0, None, win32file.OPEN_EXISTING, 0, None
                    )
                except pywintypes.error as e:
                    if e.winerror == 2:  # ERROR_FILE_NOT_FOUND
                        raise MPVError(f"MPV pipe not found: {self.ipc_path}. Is MPV running with --input-ipc-server?")
                    elif e.winerror == 5:  # ERROR_ACCESS_DENIED
                        raise MPVError(f"Access denied to MPV pipe: {self.ipc_path}.")
                    else:
                        raise MPVError(f"Error connecting to MPV pipe: {e}")
                        
                if handle == win32file.INVALID_HANDLE_VALUE:
                    raise MPVError(f"Failed to open MPV pipe {self.ipc_path}.")

                self.connection = handle
                logger.debug(f"Connected to MPV pipe: {self.ipc_path}")

            else:  # POSIX (Linux/macOS)
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(2.0)  # 2 second timeout for connection
                try:
                    sock.connect(self.ipc_path)
                except (FileNotFoundError, ConnectionRefusedError) as e:
                    raise MPVError(f"MPV socket {self.ipc_path} not found or connection refused. Is MPV running?")
                except socket.timeout:
                    raise MPVError(f"Connection timed out for MPV IPC path: {self.ipc_path}.")
                
                self.connection = sock
                logger.debug(f"Connected to MPV socket: {self.ipc_path}")

        except Exception as e:
            if not isinstance(e, MPVError):
                raise MPVError(f"Failed to connect to MPV IPC {self.ipc_path}: {e}")
            raise

    def _disconnect(self):
        """Close the connection to the MPV IPC interface."""
        if not self.connection:
            return

        try:
            if self.platform == "Windows":
                if WINDOWS_IMPORT_SUCCESS:
                    win32file.CloseHandle(self.connection)
            else:
                self.connection.close()
            logger.debug("Disconnected from MPV IPC.")
        except Exception as e:
            logger.error(f"Error disconnecting from MPV IPC: {e}", exc_info=True)
        finally:
            self.connection = None

    def _send_command(self, command: list) -> int:
        """Send a JSON command to MPV."""
        if not self.connection:
            raise MPVError("Not connected to MPV.")

        request_id = self.request_id_counter
        self.request_id_counter += 1
        cmd_dict = {"command": command, "request_id": request_id}
        cmd_json = json.dumps(cmd_dict) + '\n'
        cmd_bytes = cmd_json.encode('utf-8')

        try:
            if self.platform == "Windows":
                if not WINDOWS_IMPORT_SUCCESS:
                    raise MPVError("Windows IPC requires pywin32.")
                
                try:
                    # Writing to named pipe with error handling
                    _, written = win32file.WriteFile(self.connection, cmd_bytes)
                    if written != len(cmd_bytes):
                        raise MPVError(f"Incomplete write to MPV pipe: {written}/{len(cmd_bytes)} bytes")
                except pywintypes.error as e:
                    if e.winerror == 109:  # ERROR_BROKEN_PIPE
                        raise MPVError("MPV pipe is broken or closed")
                    else:
                        raise MPVError(f"WriteFile error: {e}")
            else:
                # Writing to Unix socket
                self.connection.sendall(cmd_bytes)
                
            logger.debug(f"Sent command (ID {request_id}): {cmd_json.strip()}")
            return request_id
            
        except Exception as e:
            if not isinstance(e, MPVError):
                e = MPVError(f"Failed to send command to MPV: {e}")
            self._disconnect()  # Disconnect on error
            raise e

    def _receive_response_windows(self, timeout=MPV_TIMEOUT) -> dict | None:
        """Receive and parse a JSON response from MPV on Windows."""
        if not WINDOWS_IMPORT_SUCCESS:
            raise MPVError("Windows IPC requires pywin32.")
            
        response_data = b""
        start_time = time.monotonic()
        
        while time.monotonic() - start_time < timeout:
            try:
                # Check if pipe has any data
                try:
                    result = win32pipe.PeekNamedPipe(self.connection, 0)
                    bytes_available = result[2] if result and isinstance(result, tuple) and len(result) >= 3 else 0
                except pywintypes.error as e:
                    if e.winerror == 109:  # ERROR_BROKEN_PIPE
                        logger.debug("MPV pipe is broken or closed")
                        self._disconnect()
                        return None
                    raise
                    
                # Read data if available
                if bytes_available > 0:
                    try:
                        hr, data = win32file.ReadFile(self.connection, min(bytes_available, 4096))
                        if data:
                            response_data += data
                    except pywintypes.error as e:
                        if e.winerror == 109:  # ERROR_BROKEN_PIPE
                            self._disconnect()
                            return None
                        raise
                else:
                    # No data available, sleep briefly
                    time.sleep(MIN_READ_INTERVAL)
                    
                # Process any complete JSON lines in the response
                if b'\n' in response_data:
                    line, response_data = response_data.split(b'\n', 1)
                    try:
                        response_dict = json.loads(line.decode('utf-8', errors='ignore'))
                        # Only return command responses (with request_id), ignore events
                        if 'request_id' in response_dict:
                            return response_dict
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from MPV: {line[:100]}")
            
            except Exception as e:
                logger.error(f"Error reading from MPV pipe: {e}", exc_info=True)
                self._disconnect()
                return None
                
        # Timeout reached
        logger.warning(f"Timeout waiting for MPV response after {timeout}s")
        return None

    def _receive_response_posix(self, timeout=MPV_TIMEOUT) -> dict | None:
        """Receive and parse a JSON response from MPV on POSIX systems."""
        response_data = b""
        start_time = time.monotonic()
        
        # Set socket to non-blocking mode for select
        self.connection.setblocking(False)
        
        while time.monotonic() - start_time < timeout:
            try:
                # Use select to wait for data with timeout
                ready, _, _ = select.select([self.connection], [], [], MIN_READ_INTERVAL)
                if ready:
                    try:
                        chunk = self.connection.recv(4096)
                        if not chunk:  # Empty data means socket closed
                            logger.debug("MPV socket closed during read")
                            self._disconnect()
                            return None
                        response_data += chunk
                    except ConnectionError:
                        logger.debug("Connection error while reading from MPV socket")
                        self._disconnect()
                        return None
                    
                # Process any complete JSON lines in the response
                if b'\n' in response_data:
                    line, response_data = response_data.split(b'\n', 1)
                    try:
                        response_dict = json.loads(line.decode('utf-8', errors='ignore'))
                        # Only return command responses (with request_id), ignore events
                        if 'request_id' in response_dict:
                            return response_dict
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from MPV: {line[:100]}")
            
            except Exception as e:
                logger.error(f"Error reading from MPV socket: {e}", exc_info=True)
                self._disconnect()
                return None
                
        # Timeout reached
        logger.warning(f"Timeout waiting for MPV response after {timeout}s")
        return None

    def _receive_response(self, timeout=MPV_TIMEOUT) -> dict | None:
        """Receive and parse a JSON response from MPV."""
        if not self.connection:
            raise MPVError("Not connected to MPV.")
            
        if self.platform == "Windows":
            return self._receive_response_windows(timeout)
        else:
            return self._receive_response_posix(timeout)

    def get_property(self, prop: str) -> any:
        """Get a single property from MPV."""
        with self.ipc_lock:
            try:
                self._connect()
                req_id = self._send_command(['get_property', prop])
                response = self._receive_response()
                
                if response and response.get('request_id') == req_id:
                    if response.get('error') == 'success':
                        logger.debug(f"Got MPV property '{prop}': {response.get('data')}")
                        return response.get('data')
                    else:
                        error = response.get('error')
                        if error != 'property not found':  # Not an error for optional properties
                            logger.warning(f"MPV error getting property '{prop}': {error}")
                return None
            except MPVError as e:
                logger.warning(f"Failed to get MPV property '{prop}': {e}")
                return None
            finally:
                self._disconnect()

    def get_properties(self, properties: list[str]) -> dict:
        """Fetch multiple properties from MPV in a single connection."""
        results = {}
        
        if not properties:
            return results
            
        with self.ipc_lock:
            try:
                self._connect()
                
                # Send all commands first
                request_map = {}  # Map request_id to property name
                for prop in properties:
                    try:
                        req_id = self._send_command(['get_property', prop])
                        request_map[req_id] = prop
                    except MPVError as e:
                        logger.warning(f"Failed to send command for property '{prop}': {e}")
                
                # Wait for responses with a single overall timeout
                if request_map:
                    start_time = time.monotonic()
                    # Use a longer overall timeout based on number of properties
                    overall_timeout = min(MPV_TIMEOUT * 2, MPV_TIMEOUT * (len(properties) * 0.5))
                    
                    while request_map and time.monotonic() - start_time < overall_timeout:
                        response = self._receive_response(timeout=0.5)  # Longer individual timeout
                        
                        if response is None:
                            # No response received, check connection
                            if not self.connection:
                                break
                            continue
                            
                        req_id = response.get('request_id')
                        if req_id in request_map:
                            prop_name = request_map.pop(req_id)
                            if response.get('error') == 'success':
                                results[prop_name] = response.get('data')
                            # Don't log property not found errors for optional properties
                
            except MPVError as e:
                logger.warning(f"Failed to get MPV properties: {e}")
            finally:
                self._disconnect()
                
        return results

    def get_position_duration(self, process_name=None) -> tuple[float | None, float | None]:
        """Get current playback position and duration from MPV."""
        props = self.get_properties(['time-pos', 'duration'])
        
        try:
            position = props.get('time-pos')
            duration = props.get('duration')
            
            # Convert to proper number types
            pos = float(position) if position is not None else None
            dur = float(duration) if duration is not None else None
            
            if pos is not None and dur is not None and dur > 0:
                # Ensure position is within valid range
                pos = max(0.0, min(pos, dur))
                logger.debug(f"MPV playback: position={pos:.2f}s, duration={dur:.2f}s")
                return round(pos, 2), round(dur, 2)
            else:
                logger.debug(f"Invalid MPV position/duration: pos={position}, dur={duration}")
                return None, None
                
        except (TypeError, ValueError) as e:
            logger.debug(f"Error converting MPV position/duration: {e}")
            return None, None

    def get_current_filepath(self) -> str | None:
        """Get the filepath of the currently playing file in MPV."""
        props = self.get_properties(['path', 'working-directory'])
        
        fpath = props.get('path')
        working_dir = props.get('working-directory')
        
        if not fpath:
            return None
            
        # Build absolute path if needed
        try:
            path_obj = Path(fpath)
            
            # If path is relative and we have a working directory
            if not path_obj.is_absolute() and working_dir:
                full_path = Path(working_dir) / path_obj
                fpath = str(full_path.resolve())
            else:
                fpath = str(path_obj)
                
            # Handle file:// URIs
            if fpath.startswith('file://'):
                from urllib.parse import unquote
                fpath = unquote(fpath[7:])  # Remove file:// prefix
                # On Windows, also remove the leading '/'
                if self.platform == 'Windows' and fpath.startswith('/'):
                    fpath = fpath[1:]
                    
            logger.debug(f"MPV current file: {fpath}")
            return fpath
            
        except Exception as e:
            logger.warning(f"Error resolving MPV filepath: {e}")
            return fpath  # Return the original path as fallback

    def is_paused(self) -> bool | None:
        """Check if MPV playback is paused."""
        paused = self.get_property('pause')
        
        if paused is True:
            logger.debug("MPV state: paused")
            return True
        elif paused is False:
            logger.debug("MPV state: playing")
            return False
        else:
            logger.debug(f"Unknown MPV pause state: {paused}")
            return None