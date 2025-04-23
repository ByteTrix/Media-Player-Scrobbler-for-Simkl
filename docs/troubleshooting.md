# 🔧 Troubleshooting Guide

This document provides solutions for common issues with Simkl Scrobbler.

## 🚨 Common Issues and Solutions

### 📥 Installation Problems

| Issue | Solution |
|-------|----------|
| "Command not found" after installation | Ensure Python scripts directory is in your PATH |
| Installation fails with permission error | Use `pip install --user simkl-mps` or create a virtual environment |
| Poetry installation fails | Ensure you have the latest version of Poetry (`poetry self update`) |

### 🔐 Authentication Issues

| Issue | Solution |
|-------|----------|
| Authentication fails | Check internet connection; verify correct PIN entry |
| "Invalid client ID" error | Your custom client ID might be incorrect; remove it from config |
| Token expired or invalid | Run `simkl-mps i` (or `init`) again to re-authenticate |

### 🔍 Movie Detection Problems

| Issue | Solution |
|-------|----------|
| Movies not detected | Ensure media player shows filename in window title |
| Incorrect movie matched | Include year in filename: "Movie.Title.2023.mp4" |
| No detection in fullscreen | Some players hide window title in fullscreen; use windowed mode |
| Multiple files show as one movie | Ensure filenames are clearly different |

### ⏯️ Playback Tracking Issues

| Issue | Solution |
|-------|----------|
| Position not tracking | Configure player web interface (see [Media Players](media-players.md)) |
| Movies not marked as watched | Check completion threshold setting; verify internet connection |
| Tracking stops unexpectedly | Check logs for errors; ensure player keeps window title visible |
| VLC position not detected | Verify web interface is enabled and accessible |

### 💻 Platform-Specific Issues

#### Windows

| Issue | Solution |
|-------|----------|
| Media player not recognized | Verify player is in the supported list |
| Application doesn't start | Run `simkl-mps t` (or `tray`) to see error messages |

#### macOS

| Issue | Solution |
|-------|----------|
| AppleScript permission errors | Grant accessibility permissions in System Preferences > Security & Privacy > Privacy > Accessibility |
| Window detection failures | Install optional dependencies: `pip install "simkl-mps[macos]"` |

#### Linux

| Issue | Solution |
|-------|----------|
| Window detection not working | Install required utilities: `sudo apt install xdotool wmctrl` |
| D-Bus connection errors | Ensure you're running in a standard desktop environment |

## 🔬 Diagnostic Commands

Use these commands to help diagnose problems:

```bash
# Check installation
pip show simkl-mps

# Check version information
simkl-mps -v       # or: --version
simkl-mps V        # or: version

# Run with debug logging in background
simkl-mps s --debug    # or: start --debug

# Run with debug logging in terminal
simkl-mps t --debug    # or: tray --debug

# Check logs (Windows)
type %APPDATA%\kavinthangavel\simkl-mps\simkl_mps.log

# Check logs (macOS/Linux)
cat ~/.local/share/kavinthangavel/simkl-mps/simkl_mps.log

# Test API connectivity (Windows PowerShell)
Invoke-WebRequest -Uri https://api.simkl.com/ -Method Head

# Test API connectivity (macOS/Linux)
curl -I https://api.simkl.com/
```

## 📊 Log Analysis

Common log messages and their meanings:

| Log Message | Meaning |
|-------------|---------|
| "No active video player window found" | Normal when no player is running |
| "Failed to connect to Simkl API" | Network or authentication issue |
| "Movie title not found in window title" | Player doesn't expose title or format is unrecognized |
| "Could not parse movie title" | Filename format couldn't be understood |
| "Movie marked as watched" | Success! Movie was scrobbled |
| "Added to backlog" | Will be marked as watched when internet connection is restored |

## 🔄 Resetting the Application

If you need a fresh start:

1. Close all instances of the application
2. Delete the application data directory:
   - Windows: `%APPDATA%\kavinthangavel\simkl-mps`
   - macOS: `~/Library/Application Support/kavinthangavel/simkl-mps`
   - Linux: `~/.local/share/kavinthangavel/simkl-mps`
3. Reinstall: `pip install --force-reinstall simkl-mps`
4. Reinitialize: `simkl-mps i` (or `init`)

## 🆘 Getting Help

If you've tried the solutions above and still have issues:

1. Run in debug mode to get detailed logs:
   ```bash
   simkl-mps t --debug    # or: tray --debug
   ```
2. Open a GitHub issue with:
   - Your operating system and version
   - The application version (`simkl-mps -v` or `--version`)
   - Relevant log excerpts
   - Steps to reproduce the problem
