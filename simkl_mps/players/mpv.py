"""
MPV player integration for Media Player Scrobbler for SIMKL.
Allows getting position and duration data from MPV via IPC.
"""

import os
import sys
import json
import time
import logging
import threading
import platform
import socket
from pathlib import Path
from queue import Queue

# Configure module logging
logger = logging.getLogger(__name__)

# Import OS-specific libraries
if os.name == 'posix':
    import select
elif os.name == 'nt':
    import win32event
    import win32file
    import win32pipe
    import win32api
    from win32file import INVALID_HANDLE_VALUE
    # Import Windows-specific error codes
    try:
        from winerror import (ERROR_BROKEN_PIPE, ERROR_MORE_DATA, ERROR_IO_PENDING,
                          ERROR_PIPE_BUSY)
    except ImportError:
        # Define error codes if winerror module isn't available
        ERROR_BROKEN_PIPE = 109
        ERROR_MORE_DATA = 234
        ERROR_IO_PENDING = 997
        ERROR_PIPE_BUSY = 231

class MPVIntegration:
    """Base class for MPV integration"""
    
    def __init__(self, ipc_path=None):
        """
        Initialize MPV integration.
        
        Args:
            ipc_path: Path to MPV IPC socket or named pipe
        """
        self.name = 'mpv'
        self.platform = platform.system().lower()
        
        # Set up IPC path
        self.ipc_path = ipc_path or self._auto_detect_ipc_path()
        if not self.ipc_path:
            logger.warning("No MPV IPC path found. MPV integration will not work.")
            
        # Initialize connection state
        self.is_running = False
        self.ipc_lock = threading.Lock()
        self.write_queue = Queue()
        self.buffer = b''
        self.command_counter = 1
        self.sent_commands = {}
        self.vars = {
            'pause': True,  # Initially assume paused (state = 1)
            'path': None,
            'duration': None,
            'time-pos': 0,
            'state': 1  # 0=stopped, 1=paused, 2=playing
        }
        
        # Timeouts
        self.read_timeout = 2    # seconds
        self.write_timeout = 60  # seconds
        
        # Properties to watch
        self.watched_props = ['pause', 'path', 'duration', 'time-pos']

    def _auto_detect_ipc_path(self):
        """Auto-detect MPV IPC path based on platform and typical locations"""
        if self.platform == 'windows':
            # Windows uses named pipes - check common locations and %TEMP%
            # Default to standard protocol with auto-detection of path
            pipe_name = r'\\.\pipe\mpv-pipe'
            
            # Check environment %TEMP% location
            temp_path = os.environ.get('TEMP')
            if temp_path:
                temp_pipe = os.path.join(temp_path, 'mpv-pipe')
                if os.path.exists(temp_pipe):
                    return temp_pipe
                    
            # Try home directory
            home_pipe = os.path.join(os.path.expanduser('~'), '.mpv-pipe')
            if os.path.exists(home_pipe):
                return home_pipe
                
            # Return default pipe
            return pipe_name
            
        else:
            # Unix uses socket files
            # Check common locations
            socket_paths = [
                os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'mpv.sock'),
                os.path.join(os.path.expanduser('~'), '.config', 'mpv', 'socket'),
                os.path.join('/tmp', 'mpv.sock')
            ]
            
            # Also check MPV_SOCKET environment variable 
            env_socket = os.environ.get('MPV_SOCKET')
            if env_socket:
                socket_paths.insert(0, env_socket)
                
            for path in socket_paths:
                if os.path.exists(path):
                    return path
                    
            # If not found, return first path as default
            logger.warning(f"MPV socket not found, using default path: {socket_paths[0]}")
            return socket_paths[0]

    def _parse_mpv_config(self):
        """Parse MPV config file for IPC path"""
        # Common config locations
        config_paths = []
        
        if self.platform == 'darwin':
            config_paths.append(os.path.join(os.path.expanduser('~'), '.config', 'mpv', 'mpv.conf'))
        elif self.platform == 'windows':
            # Windows locations
            appdata = os.environ.get('APPDATA')
            if appdata:
                config_paths.append(os.path.join(appdata, 'mpv', 'mpv.conf'))
        else:
            # Linux/Unix
            config_paths.append(os.path.join(os.path.expanduser('~'), '.config', 'mpv', 'mpv.conf'))
            
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_text = f.read()
                        # Look for input-ipc-server option
                        for line in config_text.splitlines():
                            if 'input-ipc-server=' in line and not line.strip().startswith('#'):
                                ipc_path = line.split('input-ipc-server=')[1].strip().strip('"\'')
                                return ipc_path
                except Exception as e:
                    logger.error(f"Error parsing MPV config: {e}")
                    
        return None

    def connect(self):
        """Connect to MPV player via IPC"""
        # Override in platform-specific subclasses
        pass

    def disconnect(self):
        """Disconnect from MPV player"""
        self.is_running = False

    def can_connect(self):
        """Check if we can connect to the IPC socket/pipe"""
        # Override in platform-specific subclasses
        return False

    def send_command(self, command):
        """Send command to MPV player"""
        if not self.is_running:
            return False

        with self.ipc_lock:
            cmd_obj = {'command': command, 'request_id': self.command_counter}
            self.sent_commands[self.command_counter] = command
            self.command_counter += 1
            self.write_queue.put(str.encode(json.dumps(cmd_obj) + '\n'))
            return True

    def update_vars(self):
        """Request updates for all watched properties"""
        for prop in self.watched_props:
            self.send_command(['get_property', prop])

    def handle_data(self, data):
        """Handle data received from MPV"""
        if not data:
            return

        self.buffer += data
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            self.handle_line(line)

    def handle_line(self, line):
        """Handle a single line of data from MPV"""
        try:
            line_str = line.decode('utf-8', errors='ignore')
            mpv_json = json.loads(line_str)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Invalid JSON received from MPV: {e}")
            logger.debug(f"Raw line: {line}")
            return

        if 'event' in mpv_json:
            self.handle_event(mpv_json['event'])
        elif 'request_id' in mpv_json:
            self.handle_response(mpv_json)

    def handle_event(self, event):
        """Handle MPV event"""
        if event == 'end-file':
            self.vars['state'] = 0  # Stopped
        elif event == 'pause':
            self.vars['state'] = 1  # Paused
            self.vars['pause'] = True
        elif event == 'unpause' or event == 'playback-restart':
            self.vars['state'] = 2  # Playing
            self.vars['pause'] = False
        # Request updates on state change
        self.update_vars()

    def handle_response(self, response):
        """Handle response to a command"""
        if 'request_id' not in response:
            return

        # Get the original command
        cmd_id = response['request_id']
        if cmd_id not in self.sent_commands:
            logger.warning(f"Got response for unknown command ID: {cmd_id}")
            return

        command = self.sent_commands.pop(cmd_id)
        
        # Error handling
        if response.get('error') != 'success':
            logger.error(f"MPV command error: {response.get('error')} for command {command}")
            return

        # Handle property responses
        if command[0] == 'get_property' and len(command) > 1:
            prop_name = command[1]
            if prop_name in self.watched_props:
                self.vars[prop_name] = response.get('data')
                
                # Update state based on pause property
                if prop_name == 'pause':
                    self.vars['state'] = 1 if response.get('data') else 2

    def get_position_duration(self, process_name=None):
        """
        Get current position and duration from MPV player.
        
        Args:
            process_name: Process name (ignored, used for consistency with other integrations)
            
        Returns:
            tuple: (position_seconds, duration_seconds) or (None, None) if unavailable
        """
        # First check if we're connected
        if not self.is_running and not self.start_connection():
            return None, None
        
        # Get current time position and duration
        position = self.vars.get('time-pos')
        duration = self.vars.get('duration')
        
        # Check if we have valid data
        if position is None or duration is None or not isinstance(position, (int, float)) or not isinstance(duration, (int, float)):
            return None, None
            
        return position, duration

    def start_connection(self):
        """Start connection to MPV in a separate thread"""
        if self.is_running:
            return True
            
        # Check if we can connect
        if not self.can_connect():
            return False
            
        # Start connection in separate thread
        threading.Thread(target=self.connect, daemon=True).start()
        
        # Give it some time to connect
        start_time = time.time()
        while not self.is_running and time.time() - start_time < 2:
            time.sleep(0.1)
            
        return self.is_running


class MPVPosixIntegration(MPVIntegration):
    """MPV integration for POSIX systems (Unix, Linux, macOS)"""

    def __init__(self, ipc_path=None):
        super().__init__(ipc_path)
        self.socket = None

    def can_connect(self):
        """Check if we can connect to the IPC socket"""
        if not self.ipc_path or not os.path.exists(self.ipc_path):
            return False
            
        sock = socket.socket(socket.AF_UNIX)
        try:
            errno = sock.connect_ex(self.ipc_path)
            sock.close()
            return errno == 0
        except:
            sock.close()
            return False

    def connect(self):
        """Connect to MPV player via Unix socket"""
        if self.is_running:
            return

        if not self.ipc_path or not os.path.exists(self.ipc_path):
            logger.warning(f"MPV socket not found: {self.ipc_path}")
            return

        # Create socket
        self.socket = socket.socket(socket.AF_UNIX)
        try:
            self.socket.connect(self.ipc_path)
        except ConnectionRefusedError:
            logger.warning("MPV connection refused")
            return
        except Exception as e:
            logger.error(f"MPV socket error: {e}")
            return

        self.is_running = True
        logger.info(f"Connected to MPV via socket: {self.ipc_path}")

        # Immediately request property updates
        self.update_vars()

        # Main communication loop
        sock_list = [self.socket]
        while self.is_running:
            try:
                # Check for data to read
                r, w, _ = select.select(sock_list, [], [], self.read_timeout)
                if r:  # Socket has data to read
                    try:
                        data = self.socket.recv(4096)
                        if not data:  # EOF reached
                            self.is_running = False
                            break
                        self.handle_data(data)
                    except ConnectionResetError:
                        self.is_running = False
                        break

                # Check for data to write
                while not self.write_queue.empty() and self.is_running:
                    _, w, _ = select.select([], sock_list, [], self.write_timeout)
                    if not w:
                        logger.warning("MPV socket write timeout")
                        self.is_running = False
                        break
                    try:
                        self.socket.sendall(self.write_queue.get_nowait())
                        self.write_queue.task_done()
                    except BrokenPipeError:
                        self.is_running = False
                        break
            except Exception as e:
                logger.error(f"MPV socket error in main loop: {e}")
                self.is_running = False
                break

        # Cleanup
        if self.socket:
            self.socket.close()
            self.socket = None
        while not self.write_queue.empty():
            self.write_queue.get_nowait()
            self.write_queue.task_done()
        logger.info("Disconnected from MPV socket")


class MPVWindowsIntegration(MPVIntegration):
    """MPV integration for Windows systems using named pipes"""

    def __init__(self, ipc_path=None):
        super().__init__(ipc_path)
        self.pipe_handle = None
        self._read_buf = None
        self._read_all_buf = None
        
    def can_connect(self):
        """Check if the named pipe exists and is accessible"""
        try:
            if not self.ipc_path:
                return False
                
            # Check if pipe exists by trying to get its attributes
            attr = win32file.GetFileAttributes(self.ipc_path)
            # Different MPV pipe configurations might use different attributes
            return True
        except:
            return False

    def connect(self):
        """Connect to MPV player via named pipe"""
        if self.is_running:
            return

        if not self.ipc_path:
            logger.warning("No MPV pipe path specified")
            return

        # Allocate buffers for Windows pipe operations
        if not self._read_buf:
            self._read_buf = win32file.AllocateReadBuffer(4096)
        if not self._read_all_buf:
            self._read_all_buf = win32file.AllocateReadBuffer(4096)

        # Try to connect to the pipe
        for _ in range(5):  # Retry a few times in case of pipe busy
            try:
                self.pipe_handle = win32file.CreateFile(
                    self.ipc_path,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,  # No sharing
                    None,  # Default security
                    win32file.OPEN_EXISTING,
                    win32file.FILE_FLAG_OVERLAPPED,  # Overlapped I/O
                    None
                )
                break
            except win32file.error as e:
                if e.args[0] == ERROR_PIPE_BUSY:
                    # Pipe is busy, wait and retry
                    time.sleep(0.1)
                    continue
                logger.error(f"Failed to connect to MPV pipe: {e}")
                return
        else:
            logger.error("Failed to connect to MPV pipe after retry attempts")
            return

        # Check if connection succeeded
        if self.pipe_handle == INVALID_HANDLE_VALUE:
            error_code = win32api.GetLastError()
            logger.error(f"Invalid MPV pipe handle. Error code: {error_code}")
            self.pipe_handle = None
            return

        # Configure pipe for message-mode
        try:
            win32pipe.SetNamedPipeHandleState(
                self.pipe_handle, 
                win32pipe.PIPE_READMODE_MESSAGE, 
                None, 
                None
            )
        except win32file.error as e:
            logger.error(f"Failed to set MPV pipe mode: {e}")
            win32file.CloseHandle(self.pipe_handle)
            self.pipe_handle = None
            return

        # Set up overlapped I/O
        overlapped = win32file.OVERLAPPED()
        overlapped.hEvent = win32event.CreateEvent(None, 0, 0, None)

        self.is_running = True
        logger.info(f"Connected to MPV via pipe: {self.ipc_path}")

        # Immediately request property updates
        self.update_vars()

        # Main communication loop
        while self.is_running:
            try:
                # Check for data to read
                try:
                    hr, data = win32file.ReadFile(self.pipe_handle, self._read_buf, overlapped)
                    if hr != 0 and hr != ERROR_IO_PENDING:
                        logger.warning(f"MPV pipe read error: {hr}")
                        self.is_running = False
                        break

                    if hr == ERROR_IO_PENDING:
                        # Wait for read to complete
                        wait_result = win32event.WaitForSingleObject(
                            overlapped.hEvent, 
                            self.read_timeout * 1000  # Convert to milliseconds
                        )
                        if wait_result == win32event.WAIT_OBJECT_0:
                            # Read completed, get the data
                            _, bytes_read = win32file.GetOverlappedResult(
                                self.pipe_handle, 
                                overlapped, 
                                False
                            )
                            if bytes_read > 0:
                                buffer = bytes(self._read_buf[:bytes_read])
                                self.handle_data(buffer)
                except win32file.error as e:
                    if e.args[0] == ERROR_BROKEN_PIPE:
                        logger.warning("MPV pipe connection broken")
                        self.is_running = False
                        break
                    logger.error(f"MPV pipe read error: {e}")

                # Check for data to write
                while not self.write_queue.empty() and self.is_running:
                    try:
                        # Read any pending data before writing
                        try:
                            while True:
                                hr, data = win32file.ReadFile(
                                    self.pipe_handle, 
                                    self._read_all_buf, 
                                    overlapped
                                )
                                if hr != 0 and hr != ERROR_IO_PENDING:
                                    break
                                wait_result = win32event.WaitForSingleObject(
                                    overlapped.hEvent, 
                                    100  # Short timeout (milliseconds)
                                )
                                if wait_result != win32event.WAIT_OBJECT_0:
                                    break
                                _, bytes_read = win32file.GetOverlappedResult(
                                    self.pipe_handle, 
                                    overlapped, 
                                    False
                                )
                                if bytes_read > 0:
                                    buffer = bytes(self._read_all_buf[:bytes_read])
                                    self.handle_data(buffer)
                        except win32file.error:
                            pass

                        # Now write to the pipe
                        data_to_write = self.write_queue.get_nowait()
                        try:
                            # Cancel any pending reads
                            win32file.CancelIo(self.pipe_handle)
                            
                            # Write data
                            win32file.WriteFile(
                                self.pipe_handle,
                                data_to_write,
                                overlapped
                            )
                            wait_result = win32event.WaitForSingleObject(
                                overlapped.hEvent,
                                self.write_timeout * 1000  # Convert to milliseconds
                            )
                            if wait_result != win32event.WAIT_OBJECT_0:
                                logger.warning("MPV pipe write timeout")
                            self.write_queue.task_done()
                        except win32file.error as e:
                            if e.args[0] == ERROR_BROKEN_PIPE:
                                self.is_running = False
                                break
                            logger.error(f"MPV pipe write error: {e}")
                            self.write_queue.task_done()
                    except Exception as e:
                        logger.error(f"MPV pipe write loop error: {e}")
                        if not self.write_queue.empty():
                            self.write_queue.task_done()
                
                # Brief pause to avoid tight loop
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"MPV pipe error in main loop: {e}")
                self.is_running = False
                break

        # Cleanup
        if self.pipe_handle:
            win32file.CloseHandle(self.pipe_handle)
            self.pipe_handle = None
        while not self.write_queue.empty():
            self.write_queue.get_nowait()
            self.write_queue.task_done()
        logger.info("Disconnected from MPV pipe")


# Create the appropriate platform-specific implementation
def create_mpv_integration(ipc_path=None):
    """Factory function to create the appropriate MPV integration for the current platform"""
    if os.name == 'posix':
        return MPVPosixIntegration(ipc_path)
    elif os.name == 'nt':
        return MPVWindowsIntegration(ipc_path)
    else:
        logger.warning(f"Unsupported platform for MPV integration: {os.name}")
        # Return base class with limited functionality
        return MPVIntegration(ipc_path)