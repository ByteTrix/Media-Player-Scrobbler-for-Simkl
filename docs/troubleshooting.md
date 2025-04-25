# 🛠️ Troubleshooting Guide

This guide helps you solve common problems with MPS for SIMKL.

## 🚩 Common Issues & Solutions

<details>
<summary><b>Authentication Problems</b></summary>
- Run `simkl-mps init --force` to reset authentication
- Check your internet connection
- Use the exact code shown for device login
- If using a custom client ID, verify it in Simkl developer settings
</details>

<details>
<summary><b>Detection Issues</b></summary>
- Ensure your player shows the filename in the window title
- Use clear filenames with title and year
- Check if your player is supported ([see list](media-players.md))
- Some players may hide titles in fullscreen
- Run `simkl-mps tray --debug` and look for "Window title detected"
</details>

<details>
<summary><b>Tracking Problems</b></summary>
- Make sure you've watched enough (default: 80%)
- Check your internet connection
- Configure your player for advanced tracking ([see guide](media-players.md))
- Run `simkl-mps backlog process` to send pending updates
- Run in debug mode to see progress updates
</details>

<details>
<summary><b>Position Tracking Not Working</b></summary>
- Ensure player web interface or IPC is set up
- Check for port conflicts or firewall issues
- Some player versions may change their API
- Test player connection (see below)
</details>

<details>
<summary><b>Platform-Specific Issues</b></summary>

**Windows:**
- Add Python Scripts to PATH or use `py -m simkl_mps`
- Check Event Viewer for errors
- Enable system tray in taskbar settings
- Install Visual C++ Redistributable if DLLs missing
- Run as Administrator for service install

**macOS:**
- Grant accessibility and notification permissions
- Install Python via Homebrew if not found
- Check logs in Console app

**Linux:**
- Install `wmctrl`, `xdotool`, `python3-gi`, `libnotify-bin`
- Ensure your desktop supports system trays
- Check D-Bus and window manager support
</details>

---

## 🧑‍💻 Advanced Diagnostics

<details>
<summary><b>Debug Logging</b></summary>
- Run with debug logging: `simkl-mps tray --log-level DEBUG`
- Set persistent debug: add `SIMKL_LOG_LEVEL=DEBUG` to your config file
- Look for INFO, WARNING, ERROR, CRITICAL in logs
</details>

<details>
<summary><b>Network Diagnostics</b></summary>
- Test SIMKL API: `curl -I https://api.simkl.com/`
- Test VLC: `curl -I http://localhost:8080/`
- Test MPC: `curl -I http://localhost:13579/`
- Check for processes on ports: `netstat -ano | findstr "8080 13579"` (Windows)
</details>

<details>
<summary><b>System Resource Usage</b></summary>
- Windows: `Get-Process -Name "MPSS*" | Select-Object Name, CPU, WS`
- macOS/Linux: `ps aux | grep -i simkl`
- App should use <1% CPU and <50MB RAM when idle
</details>

---

## 🔄 Reset & Recovery

<details>
<summary><b>Full Reset</b></summary>
1. Stop all instances: `simkl-mps stop`
2. Delete app data directory:
   - Windows: `%APPDATA%\kavinthangavel\simkl-mps`
   - macOS: `~/Library/Application Support/kavinthangavel/simkl-mps`
   - Linux: `~/.local/share/kavinthangavel/simkl-mps`
3. Reinstall: `pip install --force-reinstall simkl-mps`
4. Run `simkl-mps init`
</details>

<details>
<summary><b>Recovering from Crashes</b></summary>
1. Stop any running instances: `simkl-mps stop --force`
2. Backup and check logs
3. Try running in safe mode: `simkl-mps start --safe-mode`
</details>

---

## 🖥️ Troubleshooting the Windows Executable (MPS for Simkl.exe)

The Windows installer provides a native executable (`MPS for Simkl.exe`) with tray icon and auto-update. Here are some tips for troubleshooting the EXE version:

### Authentication Issues
- If authentication fails or you get stuck, try closing and reopening **MPS for Simkl.exe** from the Start menu or desktop shortcut. This can reset the authentication flow and prompt you again.
- Make sure only one instance is running (check the system tray for the icon).


### Update or Installation Errors
- If an update fails or you see an installation error, try restarting your computer and running **MPS for Simkl.exe** again from the Start menu or desktop.
- Make sure you have the latest installer from the [Releases Page](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/releases/latest).
- If the tray icon does not appear after updating, try reinstalling the application.
- Always check the log file for details: `%APPDATA%\kavinthangavel\simkl-mps\simkl_mps.log`
- If you encounter persistent update or install issues, please report them in the [GitHub Discussions or Issues](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues) and mention you are using the EXE version.

### Basic EXE Troubleshooting
- Double-click the desktop or Start menu shortcut to launch the app. If nothing happens, check the Task Manager for any running `MPS for Simkl.exe` or `MPSS.exe` processes and end them before trying again.
- If the tray icon is missing, ensure your Windows system tray is enabled and not hiding the icon.
- If you see errors about missing DLLs, install the latest [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170).
- For auto-start issues, check that the shortcut exists in your Startup folder (`shell:startup` in Run dialog).
- If you get repeated errors or crashes, try running the EXE as Administrator (right-click → Run as administrator).
- For update problems, you can manually run the updater script: right-click `updater.ps1` in the install directory and select "Run with PowerShell".

### Need More Help?
- For real-time help, you can join the official [Simkl Discord server](https://discord.gg/simkl) and ask in the [MPSS Post](https://discord.com/channels/322804221688938516/1363974113429032960). Mention you are using the Windows EXE/tray version.
- Always include your OS version, app version, and any error messages or log excerpts when asking for help.

---

## 🆘 Getting Help

- Check [GitHub Issues](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues)
- Collect diagnostics: `simkl-mps diagnose > simkl-diagnostic-report.txt`
- Open a new issue with:
  - OS and version
  - MPS version (`simkl-mps --version`)
  - Log excerpts (redact sensitive info)
  - Steps to reproduce
  - Diagnostic report file
