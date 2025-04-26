# 🛠️ Troubleshooting Guide

This comprehensive guide helps you solve common problems with Media Player Scrobbler for Simkl, with a focus on media player configuration, the Windows installer, and movie tracking issues.

## 🚩 Common Issues & Solutions

### 🔐 Authentication Problems

<details>
<summary><b>Can't authenticate with Simkl</b></summary>

- Run `simkl-mps init --force` to reset authentication
- Check your internet connection
- Use the exact code shown for device login
- If using a custom client ID, verify it in Simkl developer settings
- For Windows installer: Try restarting the application from the Start menu
</details>

<details>
<summary><b>Authentication token expired or invalid</b></summary>

- Your authentication token may have expired or been invalidated
- Run `simkl-mps init` to re-authenticate with Simkl
- For Windows installer: Try Starting Application in Start Menu
</details>

### 🔍 Movie Detection Issues

<details>
<summary><b>Movies not being detected</b></summary>

- Ensure your player shows the filename in the window title
- Use clear filenames with movie title and year: `Movie Title (Year).ext`
- Check if your player is supported (see [Media Players](media-players.md))
- Some players may hide titles in fullscreen mode
- Run with debug logging: `simkl-mps tray --debug` and look for "Window title detected"
- **Important**: TV shows are not yet supported (planned for future updates)
</details>

<details>
<summary><b>Wrong movie being identified</b></summary>

- Improve your filename format: `Movie Title (Year).ext`
- Example: `Inception (2010).mkv` instead of just `Inception.mkv`
- Remove extra text like quality info or release group names
- Check logs to see which title was extracted from your filename
</details>

### ⚙️ Media Player Configuration Issues

<details>
<summary><b>VLC configuration problems</b></summary>

**Symptoms**: No position tracking, movie not detected, or less accurate scrobbling

**Solutions**:
1. Verify web interface is enabled:
   - Tools → Preferences → Show settings: All
   - Interface → Main interfaces → Check "Web"
2. Check password configuration:
   - Interface → Main interfaces → Lua
   - Ensure "Lua HTTP Password" is set
3. Test connection:
   - Open `http://localhost:8080` in a browser
   - You should be prompted for a password
4. Port conflicts:
   - Try changing the VLC web interface port if 8080 is in use
   - Check Task Manager for other processes using port 8080
5. Restart VLC after making changes
</details>

<details>
<summary><b>MPV configuration problems</b></summary>

**Symptoms**: No position tracking or MPV not detected

**Solutions**:
1. Verify your `mpv.conf` file:
   - Windows: Located at `%APPDATA%\mpv\mpv.conf`
   - Should contain: `input-ipc-server=\\.\pipe\mpvsocket`
   - macOS/Linux: Should contain: `input-ipc-server=/tmp/mpvsocket`
2. Check for typos in the configuration line
3. Ensure MPV is restarted after configuration changes
4. Verify the socket is created when MPV is running
5. Try running MPV from command line to see any socket errors
</details>

<details>
<summary><b>MPC-HC/BE configuration problems</b></summary>

**Symptoms**: No position tracking or MPC not detected

**Solutions**:
1. Verify web interface is enabled:
   - View → Options → Player → Web Interface
   - Check "Listen on port:" and set to 13579
2. Test connection:
   - Open `http://localhost:13579` in a browser
   - You should see the web interface
3. Check firewall settings:
   - Ensure MPC is allowed in your firewall
4. Restart MPC after making changes
</details>

<details>
<summary><b>PotPlayer configuration problems</b></summary>

**Symptoms**: No position tracking or PotPlayer not detected

**Solutions**:
1. Verify HTTP control is enabled:
   - Preferences (F5) → Network → Remote Control
   - Enable "HTTP control" and set port to 8080
2. Check port conflicts:
   - Try a different port if 8080 is in use
3. Restart PotPlayer after making changes
</details>

### 🚫 Tracking & Scrobbling Problems

<details>
<summary><b>Movies not marked as watched</b></summary>

- Make sure you've watched enough of the movie (default threshold: 80%)
- Check your internet connection
- Configure your player for advanced tracking (see [Media Players](media-players.md))
- Run `simkl-mps backlog process` to send pending updates
- Run in debug mode to see progress updates: `simkl-mps tray --debug`
- Check if the movie was properly identified (look for "Identified movie:" in logs)
</details>

<details>
<summary><b>Position tracking not working</b></summary>

- Ensure player web interface or IPC socket is properly configured
- Check for port conflicts or firewall issues
- Some player versions may have different APIs or changed behavior
- Try a different media player to compare behavior
- For VLC: Make sure you're using the password you configured
</details>

### 🪟 Windows Installer & EXE Issues

<details>
<summary><b>Installation failures</b></summary>

- Run the installer as Administrator (right-click → Run as administrator)
- Check Windows Defender or antivirus settings (may block the installer)
- Verify you have sufficient disk space
- Try downloading the installer again (file may be corrupted)
- Ensure you have the latest Windows updates installed
</details>

<details>
<summary><b>Application doesn't start after installation</b></summary>

- Check Windows Event Viewer for application errors
- Verify .NET Framework is installed and up to date
- Try running the application as Administrator
- Check if the application appears in Task Manager (may be running but not visible)
- Look for error logs in `%APPDATA%\kavinthangavel\simkl-mps\simkl_mps.log`
</details>

<details>
<summary><b>System tray icon missing</b></summary>

- Check if the application is running in Task Manager
- Ensure your system tray is enabled and not hiding icons
- Click the up arrow in the system tray to check for hidden icons
- Try restarting the application from the Start menu
- In Windows 11, check notification area settings in Taskbar settings
</details>

<details>
<summary><b>Auto-update problems</b></summary>

- Check if you have internet access
- Try manually checking for updates (right-click tray icon → Check for Updates)
- Verify you have write permissions to the installation directory
- Run the application as Administrator
- Try reinstalling the latest version from the releases page
</details>

<details>
<summary><b>Windows service/auto-start issues</b></summary>

- Check if the application appears in Task Manager at startup
- Verify the startup entry exists in Task Manager → Startup
- Try adding a manual startup shortcut in `shell:startup`
- For service issues, try running `simkl-mps.exe --service-install` as Administrator
</details>

### 🖥️ Platform-Specific Issues

<details>
<summary><b>Windows</b></summary>

- Add Python Scripts to PATH or use `py -m simkl_mps` (for pip installations)
- Check Event Viewer for application errors
- Enable system tray in taskbar settings
- Install Visual C++ Redistributable if DLLs are missing
- Run as Administrator for service installation
- Check Windows Defender or antivirus exclusions if the app is being blocked
</details>

<details>
<summary><b>macOS</b></summary>

- Grant accessibility and notification permissions in System Preferences
- Install Python via Homebrew if not found (`brew install python`)
- Check logs in Console app
- For pip installations, ensure pip is installed with the correct Python version
- Use `simkl-mps[macos]` to install macOS-specific dependencies
</details>

<details>
<summary><b>Linux</b></summary>

- Install required dependencies: `wmctrl`, `xdotool`, `python3-gi`, `libnotify-bin`
- Ensure your desktop environment supports system trays
- Check D-Bus and window manager support
- Verify Python 3.9+ is installed
- For some distributions, you may need additional packages for GTK integration
</details>

<details>
<summary><b>Linux system tray icon missing</b></summary>

**For Ubuntu/GNOME users:**
- Install AppIndicator extension: `sudo apt install gnome-shell-extension-appindicator`
- Enable the extension via GNOME Extensions app or at https://extensions.gnome.org/extension/615/appindicator-support/
- Restart GNOME Shell: Press Alt+F2, type "r" and press Enter
- Run the diagnostic script: `python3 -m simkl_mps.utils.linux_tray_diagnostics`

**For KDE Plasma users:**
- Right-click on system tray → Configure System Tray
- Ensure "Legacy Tray" is enabled
- Try restarting the application: `simkl-mps exit` then `simkl-mps start`

**For Xfce, MATE, or Cinnamon users:**
- Right-click on panel → Panel settings/preferences
- Ensure "Notification Area" or "System Tray" is added to the panel
- Try running in foreground to see errors: `simkl-mps tray`

**Missing dependencies:**
```bash
# For Ubuntu/Debian
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1

# For Fedora
sudo dnf install python3-gobject gtk3 libappindicator-gtk3

# For Arch Linux
sudo pacman -S python-gobject gtk3 libappindicator-gtk3
```

See the full [Linux Guide](linux-guide.md) for more details.
</details>

<details>
<summary><b>Linux autostart configuration</b></summary>

**Setup autostart with a desktop entry (recommended):**
```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/simkl-mps.desktop << EOF
[Desktop Entry]
Type=Application
Name=Media Player Scrobbler for SIMKL
Exec=simkl-mps start
Icon=media-player
Comment=Automatically track media playback and scrobble to SIMKL
Categories=Utility;
Terminal=false
StartupNotify=false
EOF
chmod +x ~/.config/autostart/simkl-mps.desktop
```

**Desktop-specific methods:**

- **GNOME**: Open "Startup Applications" → Add → Command: `simkl-mps start`
- **KDE Plasma**: System Settings → Startup and Shutdown → Autostart → Add Program → Command: `simkl-mps start`
- **Xfce**: Settings → Session and Startup → Application Autostart → Add → Command: `simkl-mps start`

See the full [Linux Guide](linux-guide.md) for more details.
</details>

## 🧑‍💻 Advanced Diagnostics

### Debug Logging

For detailed logging that helps identify issues:

```bash
# Run with debug logging
simkl-mps tray --log-level DEBUG

# For Windows installer version
"C:\Program Files\Media Player Scrobbler for Simkl\simkl-mps.exe" --debug
```

Set persistent debug logging by adding to your config file:
```
SIMKL_LOG_LEVEL=DEBUG
```

### Key Log Locations

- **Windows**: `%APPDATA%\kavinthangavel\simkl-mps\simkl_mps.log`
- **macOS**: `~/Library/Application Support/kavinthangavel/simkl-mps/simkl_mps.log`
- **Linux**: `~/.local/share/kavinthangavel/simkl-mps/simkl_mps.log`

### Important Log Messages to Look For

- `Window title detected:` – Shows what is being monitored
- `Identified movie:` – Successful movie detection
- `Progress:` – Current playback position
- `Marked as watched:` – Successful scrobbling
- `ERROR:` – Problems requiring attention

### Network Diagnostics

Test connectivity to required services:

```bash
# Test SIMKL API
curl -I https://api.simkl.com/

# Test VLC web interface
curl -I http://localhost:8080/

# Test MPC web interface
curl -I http://localhost:13579/
```

Check for port conflicts:
- Windows: `netstat -ano | findstr "8080 13579"`
- macOS/Linux: `sudo lsof -i :8080` and `sudo lsof -i :13579`

### System Resource Usage

The application should use minimal resources:
- Windows: `Get-Process -Name "MPSS*" | Select-Object Name, CPU, WS`
- macOS/Linux: `ps aux | grep -i simkl`
- Expected usage: <1% CPU and <60MB RAM when idle

## 🔄 Reset & Recovery

### Full Reset Procedure

If you need to completely reset the application:

1. Stop all instances: `simkl-mps stop` or end process in Task Manager
2. Delete app data directory:
   - Windows: `%APPDATA%\kavinthangavel\simkl-mps`
   - macOS: `~/Library/Application Support/kavinthangavel/simkl-mps`
   - Linux: `~/.local/share/kavinthangavel/simkl-mps`
3. For pip installations: `pip install --force-reinstall simkl-mps`
4. For Windows installer: Uninstall via Settings → Apps, then reinstall
5. Run initial setup: `simkl-mps start`

### Recovering from Crashes

1. Stop any running instances: `simkl-mps stop --force` or use Task Manager
2. Backup and check logs for errors
3. Try running in safe mode: `simkl-mps start --safe-mode`
4. If using Windows installer and crashes persist, try the pip installation method

## 📊 Diagnostic Tests

### Media Player Connection Test

Testing if your media player is properly configured:

```bash
# Test VLC configuration (Windows Command Prompt)
curl -I http://localhost:8080/

# Test MPV socket (Windows PowerShell)
Test-Path -Path \\.\pipe\mpvsocket
```


## 🆘 Getting Help

If you still can't resolve your issue:

1. Check the [GitHub Issues](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues) for similar problems
2. Open a new issue with:
   - OS name and version
   - Media Player Scrobbler for Simkl version (`simkl-mps --version`)
   - Log excerpts (redact sensitive information)
   - Steps to reproduce the issue
   - Attach your diagnostic report file
   - Media player and version you're using

## 💡 Quick Reference: Common Problems and Fixes

| Problem | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| No movies detected | Media player not supported or configured | Configure player according to [Media Players](media-players.md) guide |
| Wrong movie identified | Poor filename | Rename to `Movie Title (Year).ext` format |
| VLC not connecting | Web interface not enabled | Enable web interface in VLC preferences |
| MPV not connecting | IPC socket not configured | Add socket path to mpv.conf |
| Movies not marked as watched | Not watched enough/threshold not met | Watch at least 80% of the movie |
| Offline scrobbles not syncing | Internet connection or backlog issue | Run `simkl-mps backlog process` manually |
| System tray icon missing | System tray settings or app crash | Check hidden icons or restart app |
| Windows installer fails | Admin rights or antivirus | Run as Administrator and check antivirus settings |
| High CPU usage | Debug logging or process conflict | Restart app or check for conflicting processes |
