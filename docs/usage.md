# 🎮 Usage Guide

This guide explains how to use MPS for SIMKL to track your movies and sync with your SIMKL profile.

- For installation, see the [Windows Guide](windows-guide.md), [Linux Guide](linux-guide.md), or [Mac Guide](mac-guide.md).
- For player setup, see the [Media Players Guide](media-players.md).

## 🏁 Getting Started

1. Install the app for your platform (see guides above).
2. Authenticate with SIMKL on first run.
3. **Configure your media players** (see [Media Players Guide](media-players.md)).
4. Play movies in your configured player. The app tracks and syncs progress automatically.

## 🖥️ Windows (EXE)
- Just install and launch. The app runs in the tray —no commands needed.
- Use the tray icon for status and controls.

## 🐧 Linux (pipx)
- Install with pipx (see [Linux Guide](linux-guide.md)).
- Start with `simkl-mps tray` or `simkl-mps start`.
- Tray icon provides controls and status.

## 🍏 Mac (pip, untested)
- Install with pip (see [Mac Guide](mac-guide.md)).
- Start with `simkl-mps tray` or `simkl-mps start`.
- Tray icon provides controls and status.
- 
> Note: Mac support is experimental and untested.

## 🔔 Tray Status Icons

MPS for SIMKL uses the system tray/notification area to show its current status across all platforms:

| Icon | Status | Description |
|------|--------|-------------|
| ![Running](../simkl_mps/assets/simkl-mps-running.png) | **Running** | App is actively monitoring and ready to track media playback |
| ![Paused](../simkl_mps/assets/simkl-mps-paused.png) | **Paused** | Tracking is temporarily paused, no new media will be scrobbled |
| ![Stopped](../simkl_mps/assets/simkl-mps-stopped.png) | **Stopped** | App is inactive and not tracking (but still running in tray) |
| ![Error](../simkl_mps/assets/simkl-mps-error.png) | **Error** | There's an issue with the app (authentication, API, etc.) |

Right-click the tray icon to access the app menu with options to:
- Start/stop/pause monitoring
- View currently detected media
- Access settings
- Exit the application

## 🛠️ Common Operations

- **Tray:** Right-click for menu, status, and tools.
- **CLI:**
  ```bash
  simkl-mps start        # Start in background
  simkl-mps tray         # Start with tray UI
  simkl-mps status       # Check status
  simkl-mps stop         # Stop the app
  simkl-mps --help       # Help
  ```

## 📝 Tips
- Always configure your media players for best results ([Media Players Guide](media-players.md)).
- Use clear filenames: `Movie Title (Year).ext`.
- For troubleshooting, see the [Troubleshooting Guide](troubleshooting.md).
- For advanced options, see [Advanced & Developer Guide](configuration.md).
- For planned features, see the [Todo List](todo.md).
