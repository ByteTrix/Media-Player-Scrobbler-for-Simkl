# 🚀 Quick Start Guide

This concise guide provides essential information to quickly set up and use Media Player Scrobbler for Simkl.

> **Important**: Currently, the application supports **movie tracking only**. TV show support is planned for future updates.

## Installation Essentials

### Windows (Recommended)
1. [Download the installer](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/releases/latest)
2. Run the installer as Administrator
3. Select auto-start option (recommended)
4. Launch from Start menu or desktop shortcut
5. Authenticate with Simkl when prompted


### macOS/Linux ⚠️(Testing in Progress)
```bash
# macOS
pipx install "simkl-mps[macos]"

# Linux (Ubuntu/Debian example)
sudo apt install pipx wmctrl xdotool python3-gi python3-gi-cairo libnotify-bin
pipx install --system-site-packages "simkl-mps[linux]"

# Start the application
simkl-mps start
```

## ⚠️ ESSENTIAL: Media Player Configuration

For accurate tracking, configure your media player:

### VLC (Recommended)
1. Tools → Preferences → Show settings: All
2. Interface → Main interfaces → Check "Web"
3. Interface → Main interfaces → Lua → Set password
4. Save and restart VLC

### MPV
1. Edit `mpv.conf`:
   - Windows: `%APPDATA%\mpv\mpv.conf`
   - macOS/Linux: `~/.config/mpv/mpv.conf`
2. Add: `input-ipc-server=\\.\pipe\mpvsocket` (Windows)
   or `input-ipc-server=/tmp/mpvsocket` (macOS/Linux)
3. Save and restart MPV

### MPC-HC/BE (Windows)
1. View → Options → Player → Web Interface
2. Check "Listen on port:" (set to 13579)
3. Click OK and restart MPC

## 🎬 Filename Best Practices

For optimal movie identification, use:
```
Movie Title (Year).extension
```

Examples:
- `Inception (2010).mkv`
- `The Godfather (1972).mp4`

## 🖥️ Basic Operations

### System Tray Controls
- Right-click system tray icon for menu
- Check "Status" to verify the app is running
- Use "Tools" menu for logs and settings

### Command Line (All Platforms)
```bash
# Start tracking
simkl-mps start

# Check status
simkl-mps status

# Stop tracking
simkl-mps stop
```

## 💡 Troubleshooting Quick Fixes

| Issue | Solution |
|-------|----------|
| No movies detected | Configure player correctly & use clear filenames |
| Movies not marked as watched | Watch at least 80% & check internet connection |
| VLC not connecting | Enable web interface & set password |
| System tray icon missing | Check hidden icons or restart app |

## 📚 Full Documentation

- [Installation Guide](installation.md)
- [Windows Guide](windows-guide.md)
- [Media Players Configuration](media-players.md)
- [Usage Guide](usage.md)
- [Troubleshooting](troubleshooting.md)