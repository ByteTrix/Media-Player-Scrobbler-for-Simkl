"""
Test the dependency installation and compatibility for the project.

This script verifies that all dependencies can be correctly installed
and that the project functions properly with the installed dependencies.
It's particularly useful for pre-validating dependency updates before
they're committed in CI/CD workflows like dependencies.yml.
"""

import os
import sys
import subprocess
import tempfile
import shutil
import json
import platform
from pathlib import Path
import importlib.metadata
import importlib.util
from typing import List, Dict, Tuple, Optional, Any


class DependencyTester:
    """Manages dependency testing for the project."""

    def __init__(self, project_root: Path = None, verbose: bool = True):
        """
        Initialize the dependency tester.
        
        Args:
            project_root: Path to the project root. Defaults to current directory.
            verbose: Whether to print detailed output during testing.
        """
        self.project_root = project_root or Path.cwd()
        self.verbose = verbose
        self.pyproject_path = self.project_root / "pyproject.toml"
        self.poetry_lock_path = self.project_root / "poetry.lock"
        self.venv_path = self.project_root / ".venv"
        self.system_platform = platform.system().lower()
        
        # Ensure we're in a poetry project
        if not self.pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found in {self.project_root}")

    def log(self, message: str) -> None:
        """Print a message if verbose mode is enabled."""
        if self.verbose:
            print(message)

    def run_command(self, cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
        """
        Run a shell command and return exit code, stdout, and stderr.
        
        Args:
            cmd: Command to run as list of strings
            cwd: Working directory to run command in
            env: Environment variables for the command
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
            
        self.log(f"Running: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=process_env,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode != 0 and self.verbose:
            self.log(f"Command failed with exit code {process.returncode}")
            if stdout.strip():
                self.log(f"STDOUT:\n{stdout.strip()}")
            if stderr.strip():
                self.log(f"STDERR:\n{stderr.strip()}")
                
        return process.returncode, stdout, stderr

    def check_poetry_installed(self) -> bool:
        """Check if Poetry is installed and available."""
        self.log("Checking Poetry installation...")
        exit_code, stdout, _ = self.run_command(["poetry", "--version"])
        if exit_code == 0:
            self.log(f"Poetry is installed: {stdout.strip()}")
            return True
        else:
            self.log("Poetry is not installed. Please install it first.")
            return False

    def get_required_dependencies(self) -> List[str]:
        """Get a list of required production dependencies from pyproject.toml."""
        try:
            # Get dependencies directly from pyproject.toml instead of poetry show
            if not self.pyproject_path.exists():
                self.log("pyproject.toml not found")
                return []
                
            # Run poetry show to get all top-level dependencies
            exit_code, stdout, _ = self.run_command(["poetry", "show", "--only", "main"], cwd=self.project_root)
            if exit_code != 0:
                self.log("Failed to get dependencies from Poetry")
                return []
                
            # Parse the output to get root-level dependencies
            dependencies = []
            for line in stdout.splitlines():
                parts = line.split(" ", 1)
                if len(parts) > 0 and parts[0]:
                    # Skip any formatting characters
                    if not (parts[0].startswith('|') or parts[0].startswith('`')):
                        dependencies.append(parts[0])
                        
            return dependencies
        except Exception as e:
            self.log(f"Error getting dependencies: {e}")
            return []

    def test_dependency_installation(self, use_venv: bool = True) -> bool:
        """
        Test that all dependencies can be installed correctly.
        
        Args:
            use_venv: Whether to create and use a virtual environment
            
        Returns:
            True if all dependencies installed successfully, False otherwise
        """
        self.log(f"Testing dependency installation (venv: {use_venv})...")

        # Remember the original directory
        original_dir = Path.cwd()

        try:
            # Create a temporary directory for testing
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Copy pyproject.toml and poetry.lock to the temporary directory
                shutil.copy2(self.pyproject_path, temp_path / "pyproject.toml")
                if self.poetry_lock_path.exists():
                    shutil.copy2(self.poetry_lock_path, temp_path / "poetry.lock")
                
                # Create a dummy README.md file if needed (for poetry install)
                readme_path = self.project_root / "README.md"
                if readme_path.exists():
                    shutil.copy2(readme_path, temp_path / "README.md")
                else:
                    with open(temp_path / "README.md", "w") as f:
                        f.write("# Test README\nThis is a temporary README for testing.")
                
                # Choose the right command based on venv setting
                cmd = ["poetry", "install", "--no-interaction", "--no-root"]
                install_env = None
                if use_venv:
                    # Force a clean, isolated venv inside temp_dir even if called via `poetry run`
                    install_env = {
                        k: v for k, v in os.environ.items()
                        if k not in ("VIRTUAL_ENV", "POETRY_ACTIVE")
                    }
                    install_env["POETRY_VIRTUALENVS_CREATE"] = "true"
                    install_env["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"

                # Run the installation command
                process = subprocess.Popen(
                    cmd,
                    cwd=str(temp_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=install_env,
                    text=True
                )
                stdout, stderr = process.communicate()
                exit_code = process.returncode
                if exit_code != 0 and self.verbose:
                    self.log(f"Command failed with exit code {exit_code}")
                    if stdout.strip():
                        self.log(f"STDOUT:\n{stdout.strip()}")
                    if stderr.strip():
                        self.log(f"STDERR:\n{stderr.strip()}")
                
                if exit_code == 0:
                    self.log("✅ Dependencies installed successfully!")
                    return True
                else:
                    self.log("❌ Failed to install dependencies!")
                    return False
                    
        except Exception as e:
            self.log(f"Error during dependency installation test: {e}")
            return False
        finally:
            # Make sure we return to the original directory
            os.chdir(original_dir)

    def test_import_dependencies(self) -> Tuple[bool, List[str]]:
        """
        Test importing all required dependencies.
        
        Returns:
            Tuple of (success, list of failed imports)
        """
        self.log("Testing imports for all dependencies...")
        dependencies = self.get_required_dependencies()
        failed_imports = []

        import_name_map = {
            "python-dotenv": "dotenv",
            "pygetwindow": "pygetwindow",
            "pywin32": "win32api",
            "python-xlib": "Xlib",
            "pyobjc": "objc",
            "pygobject": "gi",
            "pycairo": "cairo",
            "pillow": "PIL",
            "charset-normalizer": "charset_normalizer",
            "python-dateutil": "dateutil",
        }
        platform_only = {
            "pywin32": "windows",
            "pygetwindow": "windows",
            "winotify": "windows",
            "pyobjc": "darwin",
            "pygobject": "linux",
            "pycairo": "linux",
            "python-xlib": "linux",
        }
        optional_extras = {"pygobject", "pycairo", "pyobjc", "python-xlib"}
        
        for dep in dependencies:
            dep_lower = dep.lower()

            required_platform = platform_only.get(dep_lower)
            if required_platform and self.system_platform != required_platform:
                continue

            if dep_lower in optional_extras:
                try:
                    importlib.metadata.version(dep)
                except importlib.metadata.PackageNotFoundError:
                    self.log(f"⏭️ Skipping optional dependency {dep} (not installed)")
                    continue

            import_name = import_name_map.get(dep_lower, dep.replace("-", "_"))
                
            try:
                if importlib.util.find_spec(import_name):
                    self.log(f"✅ Successfully imported {dep}")
                else:
                    self.log(f"❌ Failed to find module {dep} (import name: {import_name})")
                    failed_imports.append(dep)
            except ImportError:
                self.log(f"❌ Failed to import {dep} (import name: {import_name})")
                failed_imports.append(dep)
                
        success = len(failed_imports) == 0
        if success:
            self.log("All dependencies can be imported successfully!")
        else:
            self.log(f"Failed to import {len(failed_imports)} dependencies: {', '.join(failed_imports)}")
            
        return success, failed_imports

    def test_dependency_security(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Check for known security vulnerabilities in dependencies.
        
        Returns:
            Tuple of (is_secure, list of vulnerability reports)
        """
        self.log("Checking dependencies for security vulnerabilities...")
        
        # Run safety only if already available; never mutate the locked environment via pip install
        if not shutil.which("safety"):
            self.log("ℹ️ 'safety' is not installed; skipping local vulnerability scan (handled by CI dependency review).")
            return True, []
        
        # Run safety check on the project
        exit_code, stdout, _ = self.run_command(
            ["safety", "check", "--json"], 
            cwd=self.project_root
        )
        
        # Parse results
        vulnerabilities = []
        try:
            if stdout.strip():
                results = json.loads(stdout)
                vulnerabilities = results.get("vulnerabilities", [])
        except json.JSONDecodeError:
            self.log("Failed to parse safety output")
        
        is_secure = len(vulnerabilities) == 0
        
        if is_secure:
            self.log("✅ No known security vulnerabilities found!")
        else:
            self.log(f"❌ Found {len(vulnerabilities)} security vulnerabilities!")
            for vuln in vulnerabilities:
                self.log(f"- {vuln.get('package_name', 'Unknown')}: {vuln.get('vulnerability_id', 'Unknown')}")
                
        return is_secure, vulnerabilities

    def test_basic_application_run(self) -> bool:
        """
        Test that the application can be imported and run in basic mode.
        
        Returns:
            True if application imports and initializes correctly
        """
        self.log("Testing basic application functionality...")
        
        try:
            # Avoid Xlib DisplayNameError when running headless on Linux (e.g., CI)
            if self.system_platform == "linux" and not os.environ.get("DISPLAY") and not os.environ.get("PYSTRAY_BACKEND"):
                os.environ["PYSTRAY_BACKEND"] = "dummy"

            # Try to import key modules
            import simkl_mps
            self.log("✅ Successfully imported the simkl_mps package")
            
            # Try to import core modules
            from simkl_mps import config_manager, simkl_api
            self.log("✅ Successfully imported core modules")
            
            return True
        except ImportError as e:
            self.log(f"❌ Failed to import application modules: {e}")
            return False
        except Exception as e:
            self.log(f"❌ Error during application import test: {e}")
            return False

    def run_all_tests(self) -> bool:
        """
        Run all dependency tests.
        
        Returns:
            True if all tests pass, False otherwise
        """
        self.log("=== Starting Dependency Testing ===")
        
        # Check if Poetry is installed
        if not self.check_poetry_installed():
            return False
            
        # Test dependency installation
        install_success = self.test_dependency_installation(use_venv=True)
        if not install_success:
            return False
            
        # Test importing dependencies
        import_success, _ = self.test_import_dependencies()
        if not import_success:
            return False
            
        # Test basic application functionality
        app_success = self.test_basic_application_run()
        if not app_success:
            return False
            
        # Test security (non-blocking)
        security_success, _ = self.test_dependency_security()
        
        overall_success = install_success and import_success and app_success
        
        if overall_success:
            self.log("\n✅ All dependency tests passed successfully!")
            if not security_success:
                self.log("⚠️ Warning: Security vulnerabilities were found. Check the logs for details.")
        else:
            self.log("\n❌ Some dependency tests failed. Check the logs for details.")
            
        return overall_success


def main():
    """Main function to run the dependency tests."""
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Test project dependencies")
    parser.add_argument("--quiet", "-q", action="store_true", help="Run in quiet mode")
    parser.add_argument("--ci", action="store_true", help="Run in CI mode (stricter checks)")
    args = parser.parse_args()
    
    try:
        # Create and run the tester
        tester = DependencyTester(verbose=not args.quiet)
        success = tester.run_all_tests()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error running dependency tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()