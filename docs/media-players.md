# 🎥 Supported Media Players

This guide lists compatible media players and explains how to configure them for best tracking.

## 🗂️ Compatibility Matrix

```mermaid
graph TD
    A[Media Players] --> B[Basic Support]
    A --> C[Advanced Tracking]
    B -->|Window Title Detection| D[Any Player with Visible Filename]
    C --> E[VLC]
    C --> F[MPV]
    C --> G[MPC-HC/BE]
    E -->|Web Interface| I[Position Tracking]
    F -->|IPC Socket| I
    G -->|Web Interface| I
    I --> J[Accurate Scrobbling]
    style A fill:#4285f4,stroke:#333,stroke-width:2px,color:#fff
    style C fill:#34a853,stroke:#333,stroke-width:2px,color:#fff
    style J fill:#fbbc05,stroke:#333,stroke-width:2px
```

---

## 🪟 Windows
| Player                | Basic | Advanced | Config Method         |
|-----------------------|:-----:|:--------:|----------------------|
| VLC                   | ✅    | ✅       | Web interface (8080) |
| MPC-HC/BE             | ✅    | ✅       | Web interface (13579)|
| MPV                   | ✅    | ✅       | IPC socket           |
| PotPlayer             | ✅    | ✅       | Web interface (8080) |
| Windows Media Player  | ✅    | ❌       | Window title only    |
| SMPlayer, KMPlayer... | ✅    | ❌       | Window title only    |

## 🍏 macOS
| Player         | Basic | Advanced | Config Method         |
|---------------|:-----:|:--------:|----------------------|
| VLC           | ✅    | ✅       | Web interface (8080) |
| MPV           | ✅    | ✅       | IPC socket           |
| QuickTime     | ✅    | ❌       | Window title only    |
| Elmedia, Movist| ✅   | ❌       | Window title only    |

## 🐧 Linux
| Player         | Basic | Advanced | Config Method         |
|---------------|:-----:|:--------:|----------------------|
| VLC           | ✅    | ✅       | Web interface (8080) |
| MPV           | ✅    | ✅       | IPC socket           |
| SMPlayer, Totem| ✅   | ❌       | Window title only    |
| Kaffeine       | ✅    | ❌       | Window title only    |

---

## 🧠 Tracking Methods

```mermaid
graph LR
    A[Tracking Methods] --> B[Basic Support]
    A --> C[Advanced Tracking]
    B -->|Window Title| D[Generic Detection]
    D --> E[Estimated Progress]
    C -->|Player API| F[Direct Connection]
    F --> G[Precise Position Data]
    E --> H[Less Accurate]
    G --> I[More Accurate]
    style A fill:#4285f4,stroke:#333,stroke-width:2px,color:#fff
    style B fill:#fbbc05,stroke:#333,stroke-width:2px
    style C fill:#34a853,stroke:#333,stroke-width:2px,color:#fff
```

- **Basic:** Works by window title, no config needed, less accurate
- **Advanced:** Uses player API for exact position, needs setup, more accurate

---

## ⚙️ Player Configuration Guides

<details>
<summary><b>VLC (All Platforms)</b></summary>
Enable web interface (port 8080), set password, restart VLC. See [Configuration](configuration.md).
</details>

<details>
<summary><b>MPV (All Platforms)</b></summary>
Set up IPC socket in `mpv.conf`. See [Configuration](configuration.md).
</details>

<details>
<summary><b>MPC-HC/BE (Windows)</b></summary>
Enable web interface (port 13579) in options. See [Configuration](configuration.md).
</details>

<details>
<summary><b>PotPlayer (Windows, Testing)</b></summary>
Enable web interface (port 8080) in preferences.
</details>

---

## 🏷️ Filename Best Practices

```mermaid
graph LR
    A[Optimal Filename Format] --> B[Movies]
    A --> C[TV Shows]
    B --> D["MovieTitle (Year).ext"]
    C --> E["ShowTitle SXXEXX.ext"]
    D --> F["Inception (2010).mkv"]
    E --> G["Breaking Bad S01E01.mp4"]
    style A fill:#4285f4,stroke:#333,stroke-width:2px,color:#fff
```
- Movies: `Inception (2010).mkv`
- TV: `Breaking Bad S01E01.mp4`

---

## 🛠️ Troubleshooting & Testing

| Problem                  | Solution                                  |
|--------------------------|-------------------------------------------|
| Can't connect to VLC     | Enable web interface, check password      |
| MPV socket not found     | Check socket path, permissions            |
| MPC web not responding   | Enable interface, check port              |
| Position not working     | Use supported player, verify config       |

**Test your setup:**
1. Start player with advanced tracking enabled
2. Run `simkl-mps tray --debug`
3. Play a media file
4. Check logs for connection and position data

If advanced tracking fails:
- Use window title detection
- Try a different player (VLC is most reliable)
- Use clear filenames for best results
