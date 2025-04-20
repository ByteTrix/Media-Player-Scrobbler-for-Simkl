#!/usr/bin/env python3
"""
Test runner for simkl-movie-tracker tests.

This script runs the unit tests for the simkl-movie-tracker application,
with special handling for OS-specific tests.

Usage:
    python run_tests.py [--all] [--windows] [--linux] [--macos]

Options:
    --all       Run all tests, including cross-platform tests
    --windows   Run only Windows-specific tests
    --linux     Run only Linux-specific tests
    --macos     Run only macOS-specific tests
"""

import unittest
import sys
import os
import platform
import argparse

# Add parent directory to path to allow importing modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_tests(os_filter=None):
    """
    Run tests with optional OS filtering.
    
    Args:
        os_filter: Optional string to filter tests by OS ('windows', 'linux', 'darwin')
    """
    # Discover all tests in the tests directory
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(start_dir, pattern="test_*.py")

    # If no filter, run all tests
    if not os_filter:
        print(f"Running all tests")
        unittest.TextTestRunner(verbosity=2).run(suite)
        return

    # Get current platform
    current_os = platform.system().lower()
    print(f"Current platform: {current_os}")
    
    # If we're filtering for a specific OS that doesn't match current OS,
    # warn the user that tests will be using mocks
    if os_filter != current_os:
        print(f"WARNING: Running {os_filter} tests on {current_os} platform.")
        print(f"Tests will use mocks to simulate {os_filter} behavior.")
    
    # Create a filtered test suite
    filtered_suite = unittest.TestSuite()
    
    # Helper function to check if a test matches our filter
    def should_include_test(test):
        test_name = test.id().lower()
        
        # Special case for TestPlatformDetection which should run on any platform
        if "testplatformdetection" in test_name:
            return True
            
        # Include platform-agnostic tests
        if "platformagnostic" in test_name:
            return True
            
        # If filtering for Windows
        if os_filter == 'windows' and "windows" in test_name:
            return True
            
        # If filtering for Linux
        if os_filter == 'linux' and "linux" in test_name:
            return True
            
        # If filtering for macOS
        if os_filter == 'darwin' and ("mac" in test_name or "darwin" in test_name):
            return True
            
        return False
    
    # Recursively add matching tests to our filtered suite
    for test_suite in suite:
        for test_case in test_suite:
            if isinstance(test_case, unittest.TestCase):
                if should_include_test(test_case):
                    filtered_suite.addTest(test_case)
            else:
                # Handle nested test suites
                for test in test_case:
                    if should_include_test(test):
                        filtered_suite.addTest(test)
    
    # Run the filtered suite
    print(f"Running {os_filter} tests")
    unittest.TextTestRunner(verbosity=2).run(filtered_suite)


def main():
    """Parse command line arguments and run tests."""
    parser = argparse.ArgumentParser(description="Run simkl-movie-tracker tests")
    
    # Add option to run all tests or specific OS tests
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--all", action="store_true", help="Run all tests")
    group.add_argument("--windows", action="store_true", help="Run Windows tests")
    group.add_argument("--linux", action="store_true", help="Run Linux tests")
    group.add_argument("--macos", action="store_true", help="Run macOS tests")
    
    args = parser.parse_args()
    
    # Determine which tests to run
    if args.windows:
        run_tests('windows')
    elif args.linux:
        run_tests('linux')
    elif args.macos:
        run_tests('darwin')
    else:
        # Default to all tests
        run_tests(None)


if __name__ == "__main__":
    main()