# 📥 Installation Guide

This guide covers detailed installation instructions for Media Player Scrobbler for SIMKL across different platforms.


## 🚀 Standard Installation


### Windows

1. Download this And Install
[Latest Release](https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/releases/latest) 
2. Follow the Terminal Instructions and Authenticate SIMKL
3. Look at the Tray For MSP for Simkl.exe
4. Setup Media Player for Best Accurate Scrobbling [Media Players Setup](https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/blob/main/docs/media-players.md#%EF%B8%8F-player-configuration-for-advanced-tracking)

## or

## ✅ Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

```bash
# Install using pip
pip install simkl-mps

# Initialize with your Simkl account
simkl-mps i    # or: simkl-mps init
```

**After Installation Setup the Web Interface in Supported Players**

The initialization process will guide you through authentication with Simkl using a device code. Simply visit the provided URL and enter the code to link the application to your Simkl account.

## 💻 Platform-Specific Requirements


### macOS
For full functionality:
```bash
# Install optional dependencies (recommended)
pip install "simkl-mps"
```

### Linux
For window detection and full functionality:
```bash
# Ubuntu/Debian
sudo apt install wmctrl xdotool plyer

# Fedora
sudo dnf install wmctrl xdotool plyer

# Arch Linux
sudo pacman -S wmctrl xdotool plyer

# Install optional dependencies
pip install "simkl-mps"
```

## 🔄 Alternative Installation Methods

### Using pipx (Isolated Environment)

[pipx](https://pypa.github.io/pipx/) installs packages in isolated environments while making their entry points globally available:

```bash
# Install pipx if not already installed
python -m pip install --user pipx
python -m pipx ensurepath  # Restart terminal after this

# Install simkl-mps
pipx install simkl-mps

# For macOS specific dependencies
pipx install simkl-mps --extras macos

# For Linux specific dependencies
pipx install simkl-mps --extras linux
```

### Development Installation (from source)

```bash
# Clone repository
git clone https://github.com/kavinthangavel/simkl-mps.git
cd simkl-mps

# Install with Poetry
poetry install

# Run commands
poetry run simkl-mps i    # or: init
poetry run simkl-mps s    # or: start
```

## ✔️ Verifying Installation

After installation, verify that the application is properly installed:

```bash
simkl-mps -v    # or: --version
simkl-mps V     # or: version
```

This will display version information about the installed application.

## 🚀 Starting the Application

There are two ways to run the application:

1. Background Mode (recommended for daily use):
```bash
simkl-mps s    # or: simkl-mps start
```
This runs the application detached in the background. You can safely close the terminal.

2. Interactive Mode (useful for debugging):
```bash
simkl-mps t    # or: simkl-mps tray
```
This runs the application attached to the terminal, showing logs. The application will stop when you close the terminal.
