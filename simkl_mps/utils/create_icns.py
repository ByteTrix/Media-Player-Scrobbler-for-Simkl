#!/usr/bin/env python3
"""
Create macOS .icns file from PNG images for simkl-mps

This script converts PNG images of different sizes into a macOS .icns file
which is required for proper app bundling on macOS.

Requirements:
- PIL/Pillow library
- macOS (for iconutil) OR any OS with png2icns tool installed

Usage:
    python -m simkl_mps.utils.create_icns

The script looks for PNG files in the simkl_mps/assets folder with specific
sizes (16, 32, 64, 128, 256, 512, 1024) and creates an .icns file.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from PIL import Image

# Define required icon sizes for macOS
REQUIRED_SIZES = [16, 32, 64, 128, 256, 512, 1024]

def find_asset_folder():
    """Find the assets folder"""
    # Updated path logic since we're now in the utils directory
    script_dir = Path(__file__).resolve().parent.parent
    asset_folder = script_dir / "assets"
    
    if not asset_folder.exists():
        print(f"Error: Assets folder not found at {asset_folder}")
        sys.exit(1)
        
    return asset_folder

def find_source_icon(asset_folder):
    """Find the highest resolution source icon"""
    # Look for the highest resolution existing icon
    source_icon = None
    highest_resolution = 0
    
    # Check for existing png files
    for size in sorted(REQUIRED_SIZES, reverse=True):
        # Check specific size pattern
        icon_path = asset_folder / f"simkl-mps-{size}.png"
        if icon_path.exists():
            source_icon = icon_path
            highest_resolution = size
            break
    
    # If no size-specific icons found, try the base icon
    if source_icon is None:
        icon_path = asset_folder / "simkl-mps.png"
        if icon_path.exists():
            source_icon = icon_path
            # Open image to get its size
            with Image.open(icon_path) as img:
                highest_resolution = min(img.width, img.height)
        
    if source_icon is None:
        print("Error: Could not find any suitable source icon")
        sys.exit(1)
        
    print(f"Using source icon: {source_icon} ({highest_resolution}x{highest_resolution})")
    return source_icon, highest_resolution

def create_iconset_folder(asset_folder):
    """Create a temporary .iconset folder"""
    iconset_folder = asset_folder / "simkl-mps.iconset"
    
    # Clear the folder if it already exists
    if iconset_folder.exists():
        shutil.rmtree(iconset_folder)
        
    iconset_folder.mkdir(exist_ok=True)
    return iconset_folder

def generate_icns_mac(asset_folder, iconset_folder):
    """Generate .icns using macOS native iconutil tool"""
    try:
        subprocess.run([
            "iconutil", 
            "-c", "icns", 
            str(iconset_folder),
            "-o", str(asset_folder / "simkl-mps.icns")
        ], check=True)
        print(f"Successfully created simkl-mps.icns at {asset_folder}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running iconutil: {e}")
        return False
    except FileNotFoundError:
        print("iconutil command not found. Are you running on macOS?")
        return False

def convert_with_pillow(source_icon, iconset_folder):
    """Convert source icon to all required sizes using Pillow"""
    with Image.open(source_icon) as img:
        # Ensure the image is square
        width, height = img.size
        if width != height:
            # Crop to square using the smaller dimension
            size = min(width, height)
            left = (width - size) // 2
            top = (height - size) // 2
            right = left + size
            bottom = top + size
            img = img.crop((left, top, right, bottom))
            
        # Generate all required sizes
        for size in REQUIRED_SIZES:
            # For normal resolution
            resized_img = img.resize((size, size), Image.LANCZOS)
            normal_filename = f"icon_{size}x{size}.png"
            resized_img.save(iconset_folder / normal_filename)
            
            # For Retina display (2x)
            if size * 2 <= max(REQUIRED_SIZES):
                retina_size = size * 2
                retina_filename = f"icon_{size}x{size}@2x.png"
                retina_img = img.resize((retina_size, retina_size), Image.LANCZOS)
                retina_img.save(iconset_folder / retina_filename)

def main():
    # Find assets folder
    asset_folder = find_asset_folder()
    
    # Find source icon
    source_icon, highest_resolution = find_source_icon(asset_folder)
    
    # Create iconset folder
    iconset_folder = create_iconset_folder(asset_folder)
    
    # Convert source icon to all required sizes
    convert_with_pillow(source_icon, iconset_folder)
    
    # Try to generate icns using macOS native tool
    success = False
    if sys.platform == 'darwin':
        success = generate_icns_mac(asset_folder, iconset_folder)
    
    # If macOS tool failed or not available, try alternative methods
    if not success:
        try:
            # Try png2icns if available
            subprocess.run([
                "png2icns",
                str(asset_folder / "simkl-mps.icns"),
                *[str(iconset_folder / f"icon_{size}x{size}.png") for size in REQUIRED_SIZES]
            ], check=True)
            print(f"Successfully created simkl-mps.icns at {asset_folder} using png2icns")
            success = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("png2icns not available or failed")
            
    # Clean up
    if iconset_folder.exists():
        shutil.rmtree(iconset_folder)
    
    if not success:
        print("\nWarning: Could not create .icns file directly.")
        print("For macOS builds, you'll need to manually create the .icns file.")
        print("Consider running this script on a macOS system, or use a tool like:")
        print("- https://iconverticons.com/online/")
        print("- https://img2icnsapp.com/")
        sys.exit(1)
    
if __name__ == "__main__":
    main()