# 📥 Installation Guide

This guide covers detailed installation instructions for Simkl Scrobbler across different platforms.

## ✅ Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

## 🚀 Standard Installation

```bash
# Install using pip
pip install simkl-mps

# Initialize with your Simkl account
simkl-mps init
```

**After Installation Setup the Web Interface in Supported Players**

The initialization process will guide you through authentication with Simkl using a device code. Simply visit the provided URL and enter the code to link the application to your Simkl account.

## 💻 Platform-Specific Requirements

### Windows
No additional requirements.

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
poetry run simkl-mps init
poetry run simkl-mps start
```

## ⚙️ Running as a Service

### Installing as a Windows Service

```bash
simkl-mps install-service
```

This will install the application to run automatically at system startup.

### Installing as a Linux Service (systemd)

```bash
simkl-mps install-service
```

This creates and enables a systemd user service that starts automatically at login.

### Installing as a macOS Launch Agent

```bash
simkl-mps install-service
```

This creates and loads a LaunchAgent that runs the application at login.

## ✔️ Verifying Installation

After installation, verify that the application is properly installed:

```bash
simkl-mps --version
```

This should display the version number of the installed application.
