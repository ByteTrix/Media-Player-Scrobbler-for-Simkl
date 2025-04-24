# 🔧 Troubleshooting Guide

This document provides solutions for common issues with MPS for SIMKL and steps to diagnose and resolve problems.

## 🚨 Common Issues and Solutions

### 🔐 Authentication Problems

<details>
<summary><b>Authentication fails or token errors</b></summary>

| Issue | Solution |
|-------|----------|
| "Unable to authenticate" | Check your internet connection and try again |
| "Invalid PIN code" | Make sure you're entering the exact code shown |
| "Token expired" | Run `simkl-mps init` to get a new access token |
| "Client ID not valid" | If using a custom client ID, verify it in your Simkl developer settings |

**Quick fix command:**
```bash
simkl-mps init --force
```

This resets your authentication completely and starts a fresh authentication flow.
</details>

<details>
<summary><b>Multiple users/devices</b></summary>

MPS for SIMKL currently supports one Simkl account per installation. To switch accounts:

1. Run `simkl-mps init --force` to reset authentication
2. Complete the new authentication flow with your desired account

For multiple users on the same machine, consider using separate user accounts or custom data directories:
```bash
simkl-mps start --data-dir "/path/to/custom/location"
```
</details>

### 🔍 Detection Issues

<details>
<summary><b>Media not detected</b></summary>

If your media isn't being detected:

1. **Check window title:** Ensure your media player shows the filename in its window title
2. **File naming:** Use clear filenames with the movie/show title and year when possible
3. **Player support:** Verify your player is in the [supported list](media-players.md)
4. **Window detection:** Some players may hide or modify titles in fullscreen mode

**Debugging steps:**
```bash
# Run with debug logging to see what titles are being detected
simkl-mps tray --debug

# Look for lines containing "Window title detected" or "Parsing title"
```

When playing media, you should see log entries showing the detected window title and parsing attempts.
</details>

<details>
<summary><b>Wrong movie/show detected</b></summary>

If the wrong title is being matched:

1. **Improve filename:** Include the full title and year in parentheses: `Movie Title (2023).mp4`
2. **Check logs:** Run with `--debug` to see what title was extracted and what Simkl matched it to
3. **Manual handling:** For files that consistently mismatch, consider renaming them

**Advanced solution:**
You can modify the title parsing regex in your configuration:
```ini
# In .simkl_mps.env
SIMKL_TITLE_REGEX=(?i)(.+?)(?:\W\d{4}\W|\W\(\d{4}\)|\W\d{4}$|$)
```
</details>

<details>
<summary><b>No detection in some media players</b></summary>

Some media players may not expose the necessary information:

1. **Configure advanced tracking:** Set up the player's web interface or IPC connection (see [Media Players](media-players.md))
2. **Alternative view modes:** Some players expose title information in windowed mode but not fullscreen
3. **Window title format:** Check if your player has settings to customize the window title format

**Testing command:**
```bash
# This will show all window titles currently visible
simkl-mps windows
```
</details>

### 📊 Tracking Problems

<details>
<summary><b>Media never marked as watched</b></summary>

If media isn't being marked as watched:

1. **Completion threshold:** Verify you've watched enough of the media (default: 80%)
2. **Internet connection:** Check if you're online; offline tracking stores to backlog
3. **Advanced tracking:** Configure your player for position detection (see [Media Players](media-players.md))
4. **Process backlog:** Try `simkl-mps backlog process` to send pending updates

**Check progress tracking:**
```bash
# Run in debug mode to see progress updates
simkl-mps tray --debug

# Look for lines containing "Progress" or "position"
```

You should see periodic updates showing your current position and progress percentage.
</details>

<details>
<summary><b>Position tracking not working</b></summary>

If position isn't being detected:

1. **Player configuration:** Ensure your player's web interface or IPC is properly set up
2. **Port conflicts:** Check if the default ports are being used by other applications
3. **Firewall issues:** Ensure local connections to player ports aren't being blocked
4. **Player versions:** Some newer player versions may have changed their API

**Test player connections:**
```bash
# For VLC
curl http://localhost:8080/requests/status.xml

# For MPC-HC
curl http://localhost:13579/variables.html

# For MPV on Windows
# (requires special tools to test pipe connections)
```
</details>

### 💻 Platform-Specific Issues

<details>
<summary><b>Windows issues</b></summary>

| Issue | Solution |
|-------|----------|
| "Command not found" | Add Python Scripts directory to PATH or use `py -m simkl_mps` |
| Application won't start | Check Windows Event Viewer for Python errors |
| Tray icon missing | Verify you have system tray enabled in taskbar settings |
| Missing DLLs | Install Visual C++ Redistributable packages |
| Service won't install | Run Command Prompt as Administrator |

For advanced Windows troubleshooting:
```powershell
# Check if the process is running
Get-Process -Name "MPSS*" -ErrorAction SilentlyContinue

# View log file
Get-Content "$env:APPDATA\kavinthangavel\simkl-mps\simkl_mps.log" -Tail 50
```
</details>

<details>
<summary><b>macOS issues</b></summary>

| Issue | Solution |
|-------|----------|
| Missing permissions | Grant accessibility permissions in System Preferences > Security & Privacy > Privacy > Accessibility |
| Python not found | Install Python properly via Homebrew: `brew install python` |
| Notification issues | Grant notification permissions in System Preferences |
| App not starting | Check console logs: `console` application, filter for Python |

For advanced macOS troubleshooting:
```bash
# Check process status
ps aux | grep -i simkl

# View log file
tail -n 50 ~/Library/Application\ Support/kavinthangavel/simkl-mps/simkl_mps.log
```
</details>

<details>
<summary><b>Linux issues</b></summary>

| Issue | Solution |
|-------|----------|
| Window detection fails | Install required packages: `sudo apt install wmctrl xdotool` (or equivalent) |
| Missing dependencies | Install GTK and notification libraries: `sudo apt install python3-gi gir1.2-gtk-3.0 libnotify-bin` |
| Tray icon issues | Ensure your desktop environment supports system trays/indicators |
| D-Bus errors | Verify you're running in a standard desktop environment with D-Bus |

For advanced Linux troubleshooting:
```bash
# Check process status
ps aux | grep -i simkl

# View log file
tail -n 50 ~/.local/share/kavinthangavel/simkl-mps/simkl_mps.log

# Check if your window manager is supported
echo $XDG_CURRENT_DESKTOP

# Debug window detection
wmctrl -l
```
</details>

## 🔬 Advanced Diagnostics

<details>
<summary><b>Debug logging</b></summary>

Enable verbose logging to diagnose issues:

```bash
# Run with debug logging in terminal mode
simkl-mps tray --log-level DEBUG

# Set persistent debug logging
echo "SIMKL_LOG_LEVEL=DEBUG" >> ~/.local/share/kavinthangavel/simkl-mps/.simkl_mps.env
```

Key logging indicators:
- **INFO:** Normal operation events
- **WARNING:** Minor issues that don't prevent functionality
- **ERROR:** Problems that prevent specific operations
- **CRITICAL:** Severe issues that prevent the application from running

Important log sections to check:
1. **Authentication issues:** Look for "auth," "token," or "Simkl API" messages
2. **Detection issues:** Look for "window," "title," or "parsing" messages
3. **Playback issues:** Look for "position," "duration," or "progress" messages
4. **Scrobbling issues:** Look for "marked as watched" or "scrobble" messages
</details>

<details>
<summary><b>Network diagnostics</b></summary>

Test connections to SIMKL API and media player interfaces:

```bash
# Test SIMKL API connectivity
curl -I https://api.simkl.com/

# Test VLC web interface (if configured)
curl -I http://localhost:8080/

# Test MPC web interface (if configured)
curl -I http://localhost:13579/

# Check for processes listening on media player ports
# Windows (PowerShell):
netstat -ano | findstr "8080 13579"

# macOS/Linux:
netstat -tuln | grep -E "8080|13579"
```

Network-related issues are often indicated by timeout errors or connection refused messages in the logs.
</details>

<details>
<summary><b>System resource usage</b></summary>

If you're experiencing performance issues:

```bash
# Check CPU and memory usage
# Windows (PowerShell):
Get-Process -Name "MPSS*" | Select-Object Name, CPU, WS

# macOS/Linux:
ps aux | grep -i simkl
```

The application should use minimal resources (typically <1% CPU and <50MB RAM) when idle.
</details>

## 🧹 Reset and Recovery

<details>
<summary><b>Complete application reset</b></summary>

To reset everything and start fresh:

1. Stop all instances of the application:
   ```bash
   simkl-mps stop
   ```

2. Delete the application data directory:
   - Windows: `%APPDATA%\kavinthangavel\simkl-mps`
   - macOS: `~/Library/Application Support/kavinthangavel/simkl-mps`
   - Linux: `~/.local/share/kavinthangavel/simkl-mps`

3. Reinstall the application:
   ```bash
   pip install --force-reinstall simkl-mps
   ```

4. Initialize again:
   ```bash
   simkl-mps init
   ```
</details>

<details>
<summary><b>Recovering from crashes</b></summary>

If the application is crashing or freezing:

1. Stop any running instances:
   ```bash
   simkl-mps stop --force
   ```

2. Backup and examine logs:
   ```bash
   # Windows (PowerShell):
   Copy-Item "$env:APPDATA\kavinthangavel\simkl-mps\simkl_mps.log" "$env:USERPROFILE\Desktop\simkl_backup.log"

   # macOS/Linux:
   cp ~/.local/share/kavinthangavel/simkl-mps/simkl_mps.log ~/simkl_backup.log
   ```

3. Try running in safe mode (disables advanced features):
   ```bash
   simkl-mps start --safe-mode
   ```
</details>

## 🆘 Getting Help

If you've tried everything above and still have issues:

1. Check the [GitHub Issues](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues) to see if your problem is already known
2. Collect diagnostic information:
   ```bash
   simkl-mps diagnose > simkl-diagnostic-report.txt
   ```
3. [Open a new issue](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues/new) with:
   - Your operating system and version
   - MPS for SIMKL version (`simkl-mps --version`)
   - Relevant log excerpts (with sensitive information redacted)
   - Steps to reproduce the problem
   - The diagnostic report file
   
Include as much detail as possible to help the developers identify and fix the issue quickly.
