# 🎮 Usage Guide

This guide explains how to use MPS for SIMKL to automatically track your media watching.

## 📝 Quick Command Reference

| Command                | Shorthand      | Description                        |
|------------------------|---------------|------------------------------------|
| `simkl-mps init`       | `simkl-mps i` | Initial setup and authentication   |
| `simkl-mps start`      | `simkl-mps s` | Start tracking in background mode  |
| `simkl-mps tray`       | `simkl-mps t` | Launch with tray interface         |
| `simkl-mps stop`       | `simkl-mps x` | Stop the running application       |
| `simkl-mps status`     | `simkl-mps st`| Check if the app is running        |
| `simkl-mps version`    | `simkl-mps -v`| Show version information           |
| `simkl-mps clean`      | `simkl-mps c` | Clean old backlog entries          |
| `simkl-mps backlog`    | `simkl-mps b` | Manage offline backlog entries     |

---

## 🚦 Performance Notes

- **Movie identification:** 15–30 seconds (typical)
- **Mark as watched (online):** 2–8 seconds (best connection)
- **Offline scrobble:** 4–10 seconds to process title, 1–3 seconds to add to backlog after threshold

---

## 🚦 Getting Started

```mermaid
graph TD
    A[Install MPS for SIMKL] --> B[Run Initial Setup]
    B -->|simkl-mps init| C[Authenticate with SIMKL]
    C --> D[Choose Operation Mode]
    D -->|simkl-mps start| E[Background Mode]
    D -->|simkl-mps tray| F[Interactive Mode]
    D -->|simkl-mps daemon| G[Service Mode]
    E --> H[Play Media in Supported Player]
    F --> H
    G --> H
    H --> I[Automatic Tracking]
    I --> J[Progress Updates on SIMKL]
    style A fill:#4285f4,stroke:#333,stroke-width:2px,color:#fff
    style C fill:#fbbc05,stroke:#333,stroke-width:2px
    style H fill:#34a853,stroke:#333,stroke-width:2px,color:#fff
    style J fill:#ea4335,stroke:#333,stroke-width:2px,color:#fff
```

---

## 🔄 Operation Modes

### Background Mode (Recommended)
Runs in the background with a tray icon. Best for daily use.
```bash
simkl-mps start
```

### Interactive Tray Mode
Shows real-time output and tray icon. Good for setup and troubleshooting.
```bash
simkl-mps tray
```

### Service/Daemon Mode (Linux/macOS)
Run as a system service.
```bash
simkl-mps daemon install
simkl-mps daemon start
```

---

## 📈 Tracking Workflow

```mermaid
sequenceDiagram
    participant User
    participant MP as Media Player
    participant MPS as MPS for SIMKL
    participant SIMKL as SIMKL.com
    User->>MP: Open media file
    MP->>MPS: Window title detected
    MPS->>MPS: Parse media title
    MPS->>SIMKL: Search for media
    SIMKL->>MPS: Return metadata
    loop While media plays
        MPS->>MP: Check playback position
        MP->>MPS: Return current position
        MPS->>MPS: Calculate progress %
    end
    MPS->>MPS: Check if progress >= threshold
    MPS->>SIMKL: Mark as watched
    SIMKL->>MPS: Confirmation
    MPS->>User: Show notification
```

---

## 🖥️ System Tray Interface

The tray icon gives quick access to status and controls.

### Status Icons

| Icon | Status   | Description                  |
|------|----------|------------------------------|
| ![Running](../simkl_mps/assets/simkl-mps-running.png) | Running | Monitoring media players |
| ![Paused](../simkl_mps/assets/simkl-mps-paused.png)   | Paused  | Monitoring paused        |
| ![Stopped](../simkl_mps/assets/simkl-mps-stopped.png) | Stopped | Not monitoring          |
| ![Error](../simkl_mps/assets/simkl-mps-error.png)     | Error   | An error occurred       |

### Tray Menu Functions

```mermaid
flowchart TD
    A[Tray Icon] -->|Right-click| B[Menu]
    B --> C[Status Information]
    B --> D{Toggle Monitoring}
    D -->|If Running| E[Pause]
    D -->|If Paused/Stopped| F[Start]
    B --> G[Tools Submenu]
    G --> G1[Open Logs]
    G --> G2[Config Directory]
    G --> G3[Process Backlog]
    B --> H[SIMKL Online]
    H --> H1[SIMKL Website]
    H --> H2[Watch History]
    B --> I[Updates]
    I --> I1[Check for Updates]
    I --> I2[Install Update]
    B --> J[About/Help]
    B --> K[Exit]
    style A fill:#4285f4,stroke:#333,stroke-width:2px,color:#fff
    style F fill:#34a853,stroke:#333,stroke-width:2px,color:#fff
    style E fill:#fbbc05,stroke:#333,stroke-width:2px
    style K fill:#ea4335,stroke:#333,stroke-width:2px,color:#fff
```

---

## 🔔 Notifications

| Event              | Example                        |
|--------------------|--------------------------------|
| Authentication     | "Connected to SIMKL account"   |
| Media Detection    | "Now tracking: Movie Title"    |
| Progress Update    | "Movie Title: 45% complete"    |
| Scrobbling         | "Movie Title marked as watched"|
| Errors             | "Unable to connect to SIMKL"   |

---

## 🔁 Common Workflows

### First-Time Setup
```bash
simkl-mps init
simkl-mps tray
# Play media to verify detection
simkl-mps start
```

### Daily Usage
- Ensure MPS for SIMKL is running (auto-start or manual)
- Play media in any supported player
- The app will detect, track, and sync automatically

### Offline Usage
- Detection works offline
- Watched content is stored in backlog
- Backlog syncs when online
- Manual: `simkl-mps backlog process`

---

## 💡 Tips and Best Practices

1. Use clear filenames: `Movie Title (2023).mp4`
2. Configure [advanced tracking](media-players.md) for best accuracy
3. Increase poll interval for lower resource use
4. Enable auto-start for convenience
5. Run `simkl-mps clean` to remove old backlog

---

## 🪵 Log Analysis

Log file locations:
- Windows: `%APPDATA%\kavinthangavel\simkl-mps\simkl_mps.log`
- macOS: `~/Library/Application Support/kavinthangavel/simkl-mps/simkl_mps.log`
- Linux: `~/.local/share/kavinthangavel/simkl-mps/simkl_mps.log`

Look for:
- `Window title detected:` – What is being monitored
- `Identified movie:` – Successful detection
- `Progress:` – Playback position
- `Marked as watched:` – Scrobbling success
- `ERROR:` – Problems needing attention