#!/usr/bin/env python3
"""
build_windows_installer.py

Automates the complete Windows build and packaging process:
1. Injects Simkl Client ID and Secret (from .env or env vars) into simkl_mps/credentials.py.
2. Compiles standalone executables using PyInstaller (simkl-mps.spec).
3. Safely restores simkl_mps/credentials.py placeholders (keeping Git clean).
4. Verifies the executables with test_build.py.
5. Compiles the installer using Inno Setup (ISCC.exe).
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent
CREDENTIALS_FILE = PROJECT_ROOT / "simkl_mps" / "credentials.py"
SPEC_FILE = PROJECT_ROOT / "simkl-mps.spec"
SETUP_ISS = PROJECT_ROOT / "setup.iss"
ENV_FILE = PROJECT_ROOT / ".env"

ISCC_SEARCH_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def find_iscc() -> Path:
    """Find the Inno Setup compiler executable."""
    which_iscc = shutil.which("ISCC")
    if which_iscc:
        return Path(which_iscc)

    for p in ISCC_SEARCH_PATHS:
        if p.is_file():
            return p

    raise FileNotFoundError(
        "Inno Setup 6 (ISCC.exe) not found. Please install it or add it to PATH."
    )


def load_credentials() -> tuple[str, str]:
    """Load client credentials from .env or environment variables."""
    client_id = os.environ.get("SIMKL_CLIENT_ID")
    client_secret = os.environ.get("SIMKL_CLIENT_SECRET")

    if not client_id or not client_secret:
        if ENV_FILE.exists():
            cfg = dotenv_values(ENV_FILE)
            client_id = client_id or cfg.get("SIMKL_CLIENT_ID")
            client_secret = client_secret or cfg.get("SIMKL_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("[!] WARNING: SIMKL_CLIENT_ID or SIMKL_CLIENT_SECRET not found.")
        print("[!] Build will proceed with placeholders (credentials must be provided at runtime).")
        return "", ""

    return client_id, client_secret


def main():
    print("=" * 60)
    print("   MPS for Simkl - Windows Installer Build Pipeline")
    print("=" * 60)

    iscc_path = find_iscc()
    print(f"[*] Inno Setup Compiler found: {iscc_path}")

    client_id, client_secret = load_credentials()
    if client_id and client_secret:
        print(f"[*] Simkl API credentials found (Client ID prefix: {client_id[:8]}...)")

    orig_content = CREDENTIALS_FILE.read_text(encoding="utf-8")
    injected = False

    try:
        if client_id and client_secret:
            print("[*] Temporarily injecting credentials into simkl_mps/credentials.py...")
            modified_content = orig_content.replace(
                'CLIENT_ID_PLACEHOLDER = "SIMKL_CLIENT_ID_PLACEHOLDER"',
                f'CLIENT_ID_PLACEHOLDER = "{client_id}"'
            ).replace(
                'CLIENT_SECRET_PLACEHOLDER = "SIMKL_CLIENT_SECRET_PLACEHOLDER"',
                f'CLIENT_SECRET_PLACEHOLDER = "{client_secret}"'
            ).replace(
                'SIMKL_CLIENT_ID = CLIENT_ID_PLACEHOLDER',
                f'SIMKL_CLIENT_ID = "{client_id}"'
            ).replace(
                'SIMKL_CLIENT_SECRET = CLIENT_SECRET_PLACEHOLDER',
                f'SIMKL_CLIENT_SECRET = "{client_secret}"'
            )
            CREDENTIALS_FILE.write_text(modified_content, encoding="utf-8")
            injected = True

        # 1. Run PyInstaller
        print("\n[1/3] Running PyInstaller build...")
        python_exe = sys.executable
        pyinstaller_cmd = [python_exe, "-m", "PyInstaller", "--clean", str(SPEC_FILE)]
        res = subprocess.run(pyinstaller_cmd, cwd=PROJECT_ROOT)
        if res.returncode != 0:
            sys.exit(f"[!] PyInstaller build failed with exit code {res.returncode}")

    finally:
        if injected:
            print("\n[*] Restoring original simkl_mps/credentials.py (cleaning up secrets from git)...")
            CREDENTIALS_FILE.write_text(orig_content, encoding="utf-8")
            print("[+] simkl_mps/credentials.py restored.")

    # 2. Verify build
    print("\n[2/3] Verifying executables with test_build.py...")
    verify_cmd = [sys.executable, "test_build.py", "windows"]
    res = subprocess.run(verify_cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        sys.exit(f"[!] Executable verification failed with exit code {res.returncode}")

    # 3. Inno Setup compilation
    print(f"\n[3/3] Compiling installer with Inno Setup ({iscc_path})...")
    iscc_cmd = [str(iscc_path), str(SETUP_ISS)]
    res = subprocess.run(iscc_cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        sys.exit(f"[!] Inno Setup compilation failed with exit code {res.returncode}")

    print("\n" + "=" * 60)
    print("   BUILD SUCCESSFUL!")
    print("=" * 60)
    installer_dir = PROJECT_ROOT / "dist" / "installer"
    if installer_dir.exists():
        for item in installer_dir.glob("*.exe"):
            mb = item.stat().st_size / (1024 * 1024)
            print(f"[+] Output Installer: {item}")
            print(f"[+] File Size:        {mb:.2f} MB ({item.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
