# --- Compatibility patch for collections module (Python 3.10+) ---
# This needs to run before imports like guessit/babelfish
import collections.abc, collections
for abc_class in ['MutableMapping', 'Mapping', 'Sequence', 'MutableSequence', 'Set', 'MutableSet']:
    if not hasattr(collections, abc_class):
        setattr(collections, abc_class, getattr(collections.abc, abc_class))
print('Applied compatibility patches for collections module directly in spec')
# --- End compatibility patch ---
import sys
from pathlib import Path
import guessit
import babelfish # Added import
import os
import time
import subprocess
import shutil

# Get the directory containing this spec file
spec_dir = Path(SPECPATH)

assets_path = spec_dir / 'simkl_mps' / 'assets'

assets_dest = 'simkl_mps/assets'

# Add pre-build cleanup to handle locked files
def cleanup_build_artifacts():
    """Attempt to clean up previous build artifacts that might be locked"""
    print("Performing pre-build cleanup...")
    dist_dir = os.path.join(spec_dir, 'dist')
    
    try:
        # Try to terminate any running instances that might lock files
        if sys.platform == 'win32':
            # Windows-specific process termination
            try:
                subprocess.run(['taskkill', '/F', '/IM', 'MPS for Simkl.exe'], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['taskkill', '/F', '/IM', 'MPSS.exe'], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Give Windows time to release file handles
                time.sleep(1)
            except Exception as e:
                print(f"Warning: Could not terminate processes: {e}")
        
        # Check for locked executables and handle them
        problematic_files = [
            os.path.join(dist_dir, 'MPS for Simkl.exe'),
            os.path.join(dist_dir, 'MPSS.exe')
        ]
        
        for file_path in problematic_files:
            if os.path.exists(file_path):
                try:
                    # First try: Normal deletion
                    os.remove(file_path)
                    print(f"Successfully removed {file_path}")
                except PermissionError:
                    # Second try: Rename then delete
                    try:
                        temp_name = file_path + ".old"
                        os.rename(file_path, temp_name)
                        os.remove(temp_name)
                        print(f"Renamed and removed {file_path}")
                    except Exception as e:
                        print(f"Warning: Could not remove {file_path}: {e}")
                        # Final attempt - create new build directory
                        if os.path.dirname(file_path) == dist_dir:
                            new_dist = dist_dir + "_new"
                            if os.path.exists(new_dist):
                                shutil.rmtree(new_dist, ignore_errors=True)
                            os.makedirs(new_dist, exist_ok=True)
                            os.environ['DISTPATH'] = new_dist
                            print(f"Using alternative dist directory: {new_dist}")
                except Exception as e:
                    print(f"Warning: Could not remove {file_path}: {e}")
    except Exception as e:
        print(f"Pre-build cleanup warning: {e}")

# Run cleanup before build starts
cleanup_build_artifacts()

# --- Find guessit data path ---
try:
    guessit_base_path = os.path.dirname(guessit.__file__)
    guessit_data_path = os.path.join(guessit_base_path, 'data') # Common location for data
    if not os.path.isdir(guessit_data_path):
         # Fallback or alternative check if needed
         guessit_data_path = os.path.join(guessit.__path__[0], 'data')
    print(f"Found guessit data path: {guessit_data_path}") # For verification during build
except Exception as e:
    print(f"Warning: Could not automatically find guessit data path: {e}")
    guessit_data_path = None # Handle error case if needed
# --- End find guessit data path ---

# --- Find guessit config path ---
try:
    # guessit_base_path is already defined above
    guessit_config_path = os.path.join(guessit_base_path, 'config')
    if not os.path.isdir(guessit_config_path):
         guessit_config_path = os.path.join(guessit.__path__[0], 'config')
    print(f"Found guessit config path: {guessit_config_path}") # For verification
except Exception as e:
    print(f"Warning: Could not automatically find guessit config path: {e}")
    guessit_config_path = None
# --- End find guessit config path ---

# --- Find babelfish data path ---
try:
    babelfish_base_path = os.path.dirname(babelfish.__file__)
    babelfish_data_path = os.path.join(babelfish_base_path, 'data')
    if not os.path.isdir(babelfish_data_path):
         babelfish_data_path = os.path.join(babelfish.__path__[0], 'data')
    print(f"Found babelfish data path: {babelfish_data_path}") # For verification
except Exception as e:
    print(f"Warning: Could not automatically find babelfish data path: {e}")
    babelfish_data_path = None
# --- End find babelfish data path ---

block_cipher = None

# Define platform-specific hidden imports
hidden_imports = [
    'babelfish.language',
    'babelfish.converters',
    'babelfish.converters.alpha2',
    'babelfish.converters.alpha3b',
    'babelfish.converters.alpha3t',
    'babelfish.converters.countryname',
    'babelfish.converters.name', 
    'babelfish.country',
    'babelfish.script',
    'babelfish.converters.opensubtitles',
    'babelfish.converters.scope',
    'babelfish.converters.terminator',
]

# Add platform-specific imports
if sys.platform == 'win32':
    hidden_imports.extend([
        'plyer.platforms.win.notification',
        'win32api', 'win32con', 'win32gui',
        'tkinter', 'tkinter.ttk',  # Add tkinter for dialogs
        'threading',  # Ensure threading is included
    ])
elif sys.platform == 'darwin':
    hidden_imports.extend([
        'plyer.platforms.macosx.notification',
        'pystray._darwin',
        'Foundation', 'AppKit', 'Cocoa',
        'PyObjC',
        'tkinter', 'tkinter.ttk',  # Add tkinter for dialogs
        'threading',  # Ensure threading is included
    ])
elif sys.platform.startswith('linux'):
    hidden_imports.extend([
        'plyer.platforms.linux.notification',
        'pystray._xorg',
        'PIL._tkinter_finder',
        'gi', 'gi.repository.Gtk', 'gi.repository.GdkPixbuf', 
        'gi.repository.GLib', 'gi.repository.Gio',
        'tkinter', 'tkinter.ttk',  # Add tkinter for dialogs
        'threading',  # Ensure threading is included
    ])

# Main application analysis
a = Analysis(
    ['simkl_mps/cli.py'],
    pathex=[],
    binaries=[],
    datas=[
        (str(assets_path), assets_dest), # Your existing assets line
        # Add the following line:
        (guessit_data_path, 'guessit/data') if guessit_data_path and os.path.isdir(guessit_data_path) else None,
        # Add babelfish data
        (babelfish_data_path, 'babelfish/data') if babelfish_data_path and os.path.isdir(babelfish_data_path) else None,
        # Add guessit config
        (guessit_config_path, 'guessit/config') if guessit_config_path and os.path.isdir(guessit_config_path) else None
    ],
    hiddenimports=hidden_imports,
    excludes=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    private_asss=False,
    cipher=block_cipher,
    noarchive=False,
)
# Filter None entries from datas, if any
a.datas = [d for d in a.datas if d is not None]

# Include updater scripts in the distribution
a.datas += [
    ('utils/updater.ps1', 'simkl_mps/utils/updater.ps1', 'DATA'),
    ('utils/updater.sh', 'simkl_mps/utils/updater.sh', 'DATA'),
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Determine icon path based on platform
if sys.platform == 'win32':
    icon_path = str(assets_path / 'simkl-mps.ico')
elif sys.platform == 'darwin':
    icon_path = str(assets_path / 'simkl-mps.icns')  # Make sure this file exists in assets
else:  # Linux and others
    icon_path = str(assets_path / 'simkl-mps.png')

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MPSS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for a GUI-only app (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False if sys.platform != 'darwin' else True,  # Enable argv emulation for macOS
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

# Tray application analysis
tray_a = Analysis(
    ['simkl_mps/tray_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        (str(assets_path), assets_dest),
        (guessit_data_path, 'guessit/data') if guessit_data_path and os.path.isdir(guessit_data_path) else None,
        (babelfish_data_path, 'babelfish/data') if babelfish_data_path and os.path.isdir(babelfish_data_path) else None,
        (guessit_config_path, 'guessit/config') if guessit_config_path and os.path.isdir(guessit_config_path) else None
    ],
    hiddenimports=hidden_imports,
    excludes=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    private_asss=False,
    cipher=block_cipher,
    noarchive=False,
)
# Filter None entries from datas, if any
tray_a.datas = [d for d in tray_a.datas if d is not None]

# Include updater scripts in the distribution
tray_a.datas += [
    ('utils/updater.ps1', 'simkl_mps/utils/updater.ps1', 'DATA'),
    ('utils/updater.sh', 'simkl_mps/utils/updater.sh', 'DATA'),
]

tray_pyz = PYZ(tray_a.pure, tray_a.zipped_data, cipher=block_cipher)

tray_exe = EXE(
    tray_pyz,
    tray_a.scripts,
    tray_a.binaries,
    tray_a.zipfiles,
    tray_a.datas,
    [],
    name='MPS for Simkl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console for tray app
    disable_windowed_traceback=False,
    argv_emulation=False if sys.platform != 'darwin' else True,  # Enable argv emulation for macOS
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)

# For macOS, create application bundles
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='MPSS.app',
        icon=str(assets_path / 'simkl-mps.icns'),  # macOS icon format
        bundle_identifier='com.simkl.mpss',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'False',
            'CFBundleDisplayName': 'Media Player Scrobbler for SIMKL',
            'CFBundleShortVersionString': '${VERSION}',
            'NSRequiresAquaSystemAppearance': 'False',
            'LSUIElement': '0',  # Not a background-only app
        },
    )
    
    tray_app = BUNDLE(
        tray_exe,
        name='MPS for Simkl.app',
        icon=str(assets_path / 'simkl-mps.icns'),
        bundle_identifier='com.simkl.mpss.tray',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly': 'True',  # Background app for tray
            'CFBundleDisplayName': 'MPSS Tray',
            'CFBundleShortVersionString': '${VERSION}',
            'NSRequiresAquaSystemAppearance': 'False',
            'LSUIElement': '1',  # Background-only app
        },
    )

# For Linux, create a collect directory
elif sys.platform.startswith('linux'):
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='simkl-mps',
    )
    
    tray_coll = COLLECT(
        tray_exe,
        tray_a.binaries,
        tray_a.zipfiles,
        tray_a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='simkl-mps-tray',
    )