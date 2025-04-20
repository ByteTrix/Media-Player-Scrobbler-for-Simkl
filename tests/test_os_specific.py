"""
OS-Specific tests for SIMKL Scrobbler.

These tests check platform-specific functionality across different operating systems:
- Windows
- Linux
- macOS

Some tests use mocking to simulate different platforms without requiring actual
multi-platform testing environments.
"""

import unittest
import os
import sys
import tempfile
import platform
import pathlib
from unittest import mock
from unittest.mock import patch, MagicMock

# Add parent directory to path to allow importing the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import modules to test
from simkl_scrobbler.service_manager import (
    install_service, uninstall_service, service_status,
    install_windows_service, install_linux_service, install_macos_service,
    uninstall_windows_service, uninstall_linux_service, uninstall_macos_service,
    check_windows_service_status, check_linux_service_status, check_macos_service_status,
    PLATFORM
)


class TestPlatformDetection(unittest.TestCase):
    """Test that platform detection works correctly."""

    def test_platform_detection(self):
        """Test that the platform is detected correctly."""
        actual_platform = platform.system().lower()
        self.assertEqual(PLATFORM, actual_platform)
        
        # Ensure it's one of the supported platforms
        self.assertIn(PLATFORM, ['windows', 'linux', 'darwin'])


class MockPlatformTestCase(unittest.TestCase):
    """Base class for tests that mock different platforms."""
    
    def setUp(self):
        """Set up mock environment for tests."""
        # Create a temporary directory to simulate APP_DATA_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app_data_dir = pathlib.Path(self.temp_dir.name)
        
        # Create mock env file
        self.env_path = self.app_data_dir / ".simkl_scrobbler.env"
        with open(self.env_path, "w") as f:
            f.write("SIMKL_CLIENT_ID=test_client_id\n")
            f.write("SIMKL_ACCESS_TOKEN=test_access_token\n")
            
        # Mock patchers
        self.platform_patcher = None
        self.app_data_patcher = None
        self.subprocess_patcher = None
        
    def tearDown(self):
        """Clean up after tests."""
        # Stop all patchers
        if self.platform_patcher:
            self.platform_patcher.stop()
        if self.app_data_patcher:
            self.app_data_patcher.stop()
        if self.subprocess_patcher:
            self.subprocess_patcher.stop()
            
        # Clean up temp directory
        self.temp_dir.cleanup()


class TestWindowsService(MockPlatformTestCase):
    """Test Windows-specific service functionality."""
    
    def setUp(self):
        """Set up Windows-specific mocks."""
        super().setUp()
        
        # Mock platform as Windows
        self.platform_patcher = patch('simkl_scrobbler.service_manager.PLATFORM', 'windows')
        self.mock_platform = self.platform_patcher.start()
        
        # Mock APP_DATA_DIR
        self.app_data_patcher = patch('simkl_scrobbler.service_manager.APP_DATA_DIR', self.app_data_dir)
        self.mock_app_data = self.app_data_patcher.start()
        
        # Mock subprocess
        self.subprocess_patcher = patch('simkl_scrobbler.service_manager.subprocess')
        self.mock_subprocess = self.subprocess_patcher.start()
        
        # Create service directory
        self.service_dir = self.app_data_dir / "service"
        self.service_dir.mkdir(exist_ok=True)
        
        # Mock winreg
        self.winreg_patcher = patch('simkl_scrobbler.service_manager.winreg')
        self.mock_winreg = self.winreg_patcher.start()
        
        # Mock os functions
        self.os_chmod_patcher = patch('simkl_scrobbler.service_manager.os.chmod')
        self.mock_os_chmod = self.os_chmod_patcher.start()
        
    def tearDown(self):
        """Clean up Windows-specific mocks."""
        self.winreg_patcher.stop()
        self.os_chmod_patcher.stop()
        super().tearDown()
        
    def test_install_windows_service(self):
        """Test installing the service on Windows."""
        # Mock Windows registry operations
        mock_key = MagicMock()
        self.mock_winreg.OpenKey.return_value = mock_key
        self.mock_winreg.SetValueEx = MagicMock()
        
        # Mock subprocess.Popen
        self.mock_subprocess.CREATE_NO_WINDOW = 0x08000000
        self.mock_subprocess.Popen.return_value = MagicMock()
        
        # Call the function
        result = install_windows_service()
        
        # Verify the result
        self.assertTrue(result)
        
        # Check batch file creation
        batch_path = self.service_dir / "simkl_scrobbler_service.bat"
        self.assertTrue(batch_path.exists())
        
        # Check registry operations
        self.mock_winreg.OpenKey.assert_called_once()
        self.mock_winreg.SetValueEx.assert_called_once()
        
        # Check service start
        self.mock_subprocess.Popen.assert_called_once()
        
    def test_uninstall_windows_service(self):
        """Test uninstalling the service on Windows."""
        # Create batch file to be uninstalled
        batch_path = self.service_dir / "simkl_scrobbler_service.bat"
        with open(batch_path, "w") as f:
            f.write("@echo off\n")
        
        # Mock Windows registry operations
        mock_key = MagicMock()
        self.mock_winreg.OpenKey.return_value = mock_key
        self.mock_winreg.DeleteValue = MagicMock()
        
        # Call the function
        result = uninstall_windows_service()
        
        # Verify the result
        self.assertTrue(result)
        
        # Check registry operations
        self.mock_winreg.OpenKey.assert_called_once()
        self.mock_winreg.DeleteValue.assert_called_once()
        
        # Check batch file removal
        self.assertFalse(batch_path.exists())
        
    def test_windows_service_status(self):
        """Test checking Windows service status."""
        # Create batch file to simulate installed service
        batch_path = self.service_dir / "simkl_scrobbler_service.bat"
        with open(batch_path, "w") as f:
            f.write("@echo off\n")
            
        # Mock psutil import to fail so it uses the registry check
        with patch('simkl_scrobbler.service_manager.psutil', None):
            # Mock registry to indicate service is installed
            mock_key = MagicMock()
            self.mock_winreg.OpenKey.return_value = mock_key
            self.mock_winreg.QueryValueEx.return_value = ("path", 1)
            
            status = check_windows_service_status()
            self.assertEqual(status, "CONFIGURED")


class TestLinuxService(MockPlatformTestCase):
    """Test Linux-specific service functionality."""
    
    def setUp(self):
        """Set up Linux-specific mocks."""
        super().setUp()
        
        # Mock platform as Linux
        self.platform_patcher = patch('simkl_scrobbler.service_manager.PLATFORM', 'linux')
        self.mock_platform = self.platform_patcher.start()
        
        # Mock APP_DATA_DIR
        self.app_data_patcher = patch('simkl_scrobbler.service_manager.APP_DATA_DIR', self.app_data_dir)
        self.mock_app_data = self.app_data_patcher.start()
        
        # Mock subprocess
        self.subprocess_patcher = patch('simkl_scrobbler.service_manager.subprocess')
        self.mock_subprocess = self.subprocess_patcher.start()
        
        # Mock os functions
        self.os_chmod_patcher = patch('simkl_scrobbler.service_manager.os.chmod')
        self.mock_os_chmod = self.os_chmod_patcher.start()
        
        self.os_access_patcher = patch('simkl_scrobbler.service_manager.os.access')
        self.mock_os_access = self.os_access_patcher.start()
        self.mock_os_access.return_value = False  # Default to user service
        
        self.os_getlogin_patcher = patch('simkl_scrobbler.service_manager.os.getlogin')
        self.mock_os_getlogin = self.os_getlogin_patcher.start()
        self.mock_os_getlogin.return_value = "testuser"
        
        # Create user systemd directory
        self.user_systemd_dir = pathlib.Path.home() / ".config/systemd/user"
        self.user_systemd_dir.mkdir(parents=True, exist_ok=True)
        
    def tearDown(self):
        """Clean up Linux-specific mocks."""
        self.os_chmod_patcher.stop()
        self.os_access_patcher.stop()
        self.os_getlogin_patcher.stop()
        super().tearDown()
        
    def test_install_linux_user_service(self):
        """Test installing Linux user-level systemd service."""
        # Call the function
        with patch('simkl_scrobbler.service_manager.pathlib.Path.home') as mock_home:
            mock_home.return_value = self.app_data_dir
            
            result = install_linux_service()
            
            # Verify the result
            self.assertTrue(result)
            
            # Check service file creation
            service_path = self.app_data_dir / ".config/systemd/user/simkl-scrobbler.service"
            self.mock_os_chmod.assert_called_once()
            
            # Check systemd commands
            self.mock_subprocess.run.assert_any_call(
                ["systemctl", "--user", "daemon-reload"], check=True
            )
            self.mock_subprocess.run.assert_any_call(
                ["systemctl", "--user", "enable", "simkl-scrobbler.service"], check=True
            )
            self.mock_subprocess.run.assert_any_call(
                ["systemctl", "--user", "start", "simkl-scrobbler.service"], check=True
            )
            
    def test_install_linux_system_service(self):
        """Test installing Linux system-level systemd service."""
        # Set mock to allow system service
        self.mock_os_access.return_value = True
        
        # Call the function
        result = install_linux_service()
        
        # Verify the result
        self.assertTrue(result)
        
        # Check systemd commands for system service
        self.mock_subprocess.run.assert_any_call(
            ["systemctl", "daemon-reload"], check=True
        )
        self.mock_subprocess.run.assert_any_call(
            ["systemctl", "enable", "simkl-scrobbler.service"], check=True
        )
        self.mock_subprocess.run.assert_any_call(
            ["systemctl", "start", "simkl-scrobbler.service"], check=True
        )
        
    def test_uninstall_linux_service(self):
        """Test uninstalling Linux service."""
        # Mock user service file exists
        with patch('simkl_scrobbler.service_manager.pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            
            with patch('simkl_scrobbler.service_manager.os.unlink') as mock_unlink:
                with patch('simkl_scrobbler.service_manager.pathlib.Path.home') as mock_home:
                    mock_home.return_value = self.app_data_dir
                
                    result = uninstall_linux_service()
                    
                    # Verify the result
                    self.assertTrue(result)
                    
                    # Check service stoppage
                    self.mock_subprocess.run.assert_any_call(
                        ["systemctl", "--user", "stop", "simkl-scrobbler.service"], check=False
                    )
                    self.mock_subprocess.run.assert_any_call(
                        ["systemctl", "--user", "disable", "simkl-scrobbler.service"], check=False
                    )
                    
                    # Check service file removal
                    mock_unlink.assert_called_once()
    
    def test_linux_service_status(self):
        """Test checking Linux service status."""
        # Mock subprocess run for user service
        process_mock = MagicMock()
        process_mock.stdout = "active"
        process_mock.returncode = 0
        self.mock_subprocess.run.return_value = process_mock
        
        # Call the function
        status = check_linux_service_status()
        
        # Verify result
        self.assertTrue(status)
        
        # Check subprocess calls
        self.mock_subprocess.run.assert_called_with(
            ["systemctl", "--user", "is-active", "simkl-scrobbler.service"],
            capture_output=True, text=True, check=False
        )


class TestMacService(MockPlatformTestCase):
    """Test macOS-specific service functionality."""
    
    def setUp(self):
        """Set up macOS-specific mocks."""
        super().setUp()
        
        # Mock platform as Darwin (macOS)
        self.platform_patcher = patch('simkl_scrobbler.service_manager.PLATFORM', 'darwin')
        self.mock_platform = self.platform_patcher.start()
        
        # Mock APP_DATA_DIR
        self.app_data_patcher = patch('simkl_scrobbler.service_manager.APP_DATA_DIR', self.app_data_dir)
        self.mock_app_data = self.app_data_patcher.start()
        
        # Mock subprocess
        self.subprocess_patcher = patch('simkl_scrobbler.service_manager.subprocess')
        self.mock_subprocess = self.subprocess_patcher.start()
        
        # Mock os functions
        self.os_chmod_patcher = patch('simkl_scrobbler.service_manager.os.chmod')
        self.mock_os_chmod = self.os_chmod_patcher.start()
        
        # Create LaunchAgents directory
        self.launch_agents_dir = pathlib.Path.home() / "Library/LaunchAgents"
        self.launch_agents_dir.mkdir(parents=True, exist_ok=True)
        
    def tearDown(self):
        """Clean up macOS-specific mocks."""
        self.os_chmod_patcher.stop()
        super().tearDown()
        
    def test_install_macos_service(self):
        """Test installing macOS LaunchAgent service."""
        # Call the function
        with patch('simkl_scrobbler.service_manager.pathlib.Path.home') as mock_home:
            mock_home.return_value = self.app_data_dir
            
            result = install_macos_service()
            
            # Verify the result
            self.assertTrue(result)
            
            # Check plist file creation and permissions
            self.mock_os_chmod.assert_called_once()
            
            # Check launchctl commands
            self.mock_subprocess.run.assert_any_call(
                ["launchctl", "unload", mock.ANY], check=False
            )
            self.mock_subprocess.run.assert_any_call(
                ["launchctl", "load", "-w", mock.ANY], check=True
            )
            
    def test_uninstall_macos_service(self):
        """Test uninstalling macOS LaunchAgent service."""
        # Mock plist file exists
        with patch('simkl_scrobbler.service_manager.pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            
            with patch('simkl_scrobbler.service_manager.os.unlink') as mock_unlink:
                with patch('simkl_scrobbler.service_manager.pathlib.Path.home') as mock_home:
                    mock_home.return_value = self.app_data_dir
                
                    result = uninstall_macos_service()
                    
                    # Verify the result
                    self.assertTrue(result)
                    
                    # Check unload command
                    self.mock_subprocess.run.assert_called_with(
                        ["launchctl", "unload", mock.ANY], check=False
                    )
                    
                    # Check plist file removal
                    mock_unlink.assert_called_once()
                    
    def test_macos_service_status(self):
        """Test checking macOS service status."""
        # Mock subprocess run for launchctl
        process_mock = MagicMock()
        process_mock.returncode = 0
        self.mock_subprocess.run.return_value = process_mock
        
        # Call the function with psutil mock to fail
        with patch('simkl_scrobbler.service_manager.psutil', None):
            status = check_macos_service_status()
            
            # Verify result
            self.assertTrue(status)
            
            # Check subprocess calls
            self.mock_subprocess.run.assert_called_with(
                ["launchctl", "list", "com.kavinthangavel.simklscrobbler"],
                capture_output=True, text=True, check=False
            )


class TestPlatformAgnosticFunctions(unittest.TestCase):
    """Test functions that should work across all platforms."""
    
    def setUp(self):
        """Set up tests for platform-agnostic functions."""
        # Create temp directory
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app_data_dir = pathlib.Path(self.temp_dir.name)
        
        # Create mock env file
        self.env_path = self.app_data_dir / ".simkl_scrobbler.env"
        with open(self.env_path, "w") as f:
            f.write("SIMKL_CLIENT_ID=test_client_id\n")
            f.write("SIMKL_ACCESS_TOKEN=test_access_token\n")
        
        # Mock APP_DATA_DIR in main module
        self.app_data_patcher = patch('simkl_scrobbler.main.APP_DATA_DIR', self.app_data_dir)
        self.mock_app_data = self.app_data_patcher.start()
        
    def tearDown(self):
        """Clean up after tests."""
        self.app_data_patcher.stop()
        self.temp_dir.cleanup()
    
    @patch('simkl_scrobbler.service_manager.install_windows_service')
    @patch('simkl_scrobbler.service_manager.install_linux_service')
    @patch('simkl_scrobbler.service_manager.install_macos_service')
    def test_install_service_routing(self, mock_macos, mock_linux, mock_windows):
        """Test that install_service routes to correct platform-specific function."""
        # Test Windows route
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'windows'):
            mock_windows.return_value = True
            result = install_service()
            self.assertTrue(result)
            mock_windows.assert_called_once()
            mock_linux.assert_not_called()
            mock_macos.assert_not_called()
            
        # Reset mocks
        mock_windows.reset_mock()
        mock_linux.reset_mock()
        mock_macos.reset_mock()
        
        # Test Linux route
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'linux'):
            mock_linux.return_value = True
            result = install_service()
            self.assertTrue(result)
            mock_linux.assert_called_once()
            mock_windows.assert_not_called()
            mock_macos.assert_not_called()
            
        # Reset mocks
        mock_windows.reset_mock()
        mock_linux.reset_mock()
        mock_macos.reset_mock()
        
        # Test macOS route
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'darwin'):
            mock_macos.return_value = True
            result = install_service()
            self.assertTrue(result)
            mock_macos.assert_called_once()
            mock_windows.assert_not_called()
            mock_linux.assert_not_called()
            
        # Test unsupported platform
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'freebsd'):
            result = install_service()
            self.assertFalse(result)
    
    @patch('simkl_scrobbler.service_manager.uninstall_windows_service')
    @patch('simkl_scrobbler.service_manager.uninstall_linux_service')
    @patch('simkl_scrobbler.service_manager.uninstall_macos_service')
    def test_uninstall_service_routing(self, mock_macos, mock_linux, mock_windows):
        """Test that uninstall_service routes to correct platform-specific function."""
        # Test Windows route
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'windows'):
            mock_windows.return_value = True
            result = uninstall_service()
            self.assertTrue(result)
            mock_windows.assert_called_once()
            
        # Test Linux route
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'linux'):
            mock_linux.return_value = True
            result = uninstall_service()
            self.assertTrue(result)
            mock_linux.assert_called_once()
            
        # Test macOS route
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'darwin'):
            mock_macos.return_value = True
            result = uninstall_service()
            self.assertTrue(result)
            mock_macos.assert_called_once()
            
        # Test unsupported platform
        with patch('simkl_scrobbler.service_manager.PLATFORM', 'freebsd'):
            result = uninstall_service()
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()