# 🍏 Mac Guide (Experimental)

> **Note:** Mac support is experimental and not fully tested. Some features may not work as expected.

## 🏁 Installation

- Requires Python 3.9+ and pip.
- Recommended: Use a virtual environment or pipx.

```bash
pip install "simkl-mps[macos]"
# or with pipx
pipx install "simkl-mps[macos]"
```

## 🚀 First Run

1. Start the app:
   ```bash
   simkl-mps tray
   # or
   simkl-mps start
   ```
2. Authenticate with SIMKL when prompted.
3. The app runs in the system tray (menu bar).

## 🎛️ Media Player Configuration
- **Critical:** Configure your media players for accurate tracking.
- See the [Media Players Guide](media-players.md) for setup steps for VLC, MPV, and others.

## 🛠️ Tray & Usage
- Use the tray icon in the menu bar for status and controls.
- No command line needed for daily use after setup.

## 🐞 Troubleshooting
- Grant accessibility and notification permissions in System Preferences if tray or notifications do not work.
- For issues, see the [Troubleshooting Guide](troubleshooting.md).

## ⚠️ Limitations
- Some features may not be fully supported on macOS.
- If you encounter issues, please report them on GitHub.
