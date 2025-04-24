"""
Test the PyInstaller build to ensure executables are created correctly.

This script is used in CI/CD workflows to verify that PyInstaller successfully
created the application executables.
"""

import os
import sys
from pathlib import Path

def test_windows_build():
    """Test that Windows build produced the expected executables"""
    dist_dir = Path("dist")
    executables = ["MPSS.exe", "MPS for Simkl.exe"]
    
    print("Checking Windows build output...")
    missing = []
    
    for exe in executables:
        exe_path = dist_dir / exe
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"✅ Found {exe} ({size_mb:.2f} MB)")
        else:
            missing.append(exe)
            print(f"❌ Missing {exe}")
    
    if missing:
        print(f"Error: {len(missing)} executables are missing from the build")
        return False
    
    print("Windows build verification successful!")
    return True

def test_macos_build():
    """Test that macOS build produced the expected app bundles"""
    dist_dir = Path("dist")
    bundles = ["MPSS.app", "MPS for Simkl.app"]
    
    print("Checking macOS build output...")
    missing = []
    
    for bundle in bundles:
        bundle_path = dist_dir / bundle
        if bundle_path.exists() and bundle_path.is_dir():
            # Check for executable inside app bundle
            exe_path = bundle_path / "Contents" / "MacOS" / bundle.split('.')[0]
            if exe_path.exists():
                print(f"✅ Found {bundle} with executable")
            else:
                missing.append(f"{bundle} (missing executable)")
                print(f"❌ {bundle} exists but missing executable")
        else:
            missing.append(bundle)
            print(f"❌ Missing {bundle}")
    
    if missing:
        print(f"Error: {len(missing)} app bundles are missing or incomplete")
        return False
    
    print("macOS build verification successful!")
    return True

def test_linux_build():
    """Test that Linux build produced the expected executables"""
    dist_dir = Path("dist")
    executables = ["MPSS", "MPS for Simkl"]
    
    print("Checking Linux build output...")
    missing = []
    
    for exe in executables:
        exe_path = dist_dir / exe
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"✅ Found {exe} ({size_mb:.2f} MB)")
        else:
            missing.append(exe)
            print(f"❌ Missing {exe}")
    
    if missing:
        print(f"Error: {len(missing)} executables are missing from the build")
        return False
    
    print("Linux build verification successful!")
    return True

def main():
    """Main test function."""
    if len(sys.argv) < 2:
        print("Usage: python test_build.py [windows|macos|linux]")
        sys.exit(1)
    
    platform = sys.argv[1].lower()
    
    # List dist directory contents
    dist_dir = Path("dist")
    if dist_dir.exists():
        print(f"Contents of dist directory:")
        for item in dist_dir.iterdir():
            if item.is_file():
                size_mb = item.stat().st_size / (1024 * 1024)
                print(f"  - {item.name} ({size_mb:.2f} MB)")
            else:
                print(f"  - {item.name}/ (directory)")
    else:
        print("Error: dist directory not found!")
        sys.exit(1)
    
    # Run appropriate test function
    if platform == "windows":
        success = test_windows_build()
    elif platform == "macos":
        success = test_macos_build()
    elif platform == "linux":
        success = test_linux_build()
    else:
        print(f"Error: Unknown platform '{platform}'")
        sys.exit(1)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()