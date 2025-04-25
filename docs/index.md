# 🎬 MPS for SIMKL

[![GitHub License](https://img.shields.io/github/license/kavinthangavel/media-player-scrobbler-for-simkl)](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/blob/main/LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/simkl-mps)](https://pypi.org/project/simkl-mps/)
[![Python Versions](https://img.shields.io/pypi/pyversions/simkl-mps)](https://pypi.org/project/simkl-mps/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg)]()

<div align="center">
  <img src="../simkl_mps/assets/simkl-mps.png" alt="SIMKL MPS Logo" width="120"/>
  <br/>
  <em>Automatic movie tracking for all your media players</em>
</div>

## What is MPS for SIMKL?

MPS for SIMKL (Media Player Scrobbler) is a cross-platform app that automatically tracks your movie watching in popular media players and syncs your progress to your SIMKL account. It runs in the background or system tray, requires minimal setup, and supports Windows, macOS, and Linux.

## ⚡ Quick Start

- **Windows:** [Download the installer](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/releases/latest) and follow the setup wizard.

- **macOS/Linux:** [Testing in Progress]
  ```bash
  pip install simkl-mps
  simkl-mps start
  ```
- Authenticate with SIMKL when prompted.

See the [Installation Guide](installation.md) for full details.

## 📚 Documentation

- [Installation Guide](installation.md)
- [Usage Guide](usage.md)
- [Supported Media Players](media-players.md)
- [Configuration](configuration.md)
- [Troubleshooting](troubleshooting.md)
- [Development Guide](development.md)
- [Todo List](todo.md)

## 🔍 How It Works

```mermaid
graph TD
    A[Media Player] -->|Active Window| B[MPS for SIMKL]
    B -->|Extract Information| C[Parse Media Title]
    C -->|Search| D[SIMKL API]
    D -->|Metadata| E[Track Progress]
    E -->|>80% Complete| F[Mark as Watched]
    F -->|Update| G[SIMKL Profile]
    style A fill:#d5f5e3,stroke:#333,stroke-width:2px
    style G fill:#d5f5e3,stroke:#333,stroke-width:2px
```

1. **Detection:** Monitors active windows to detect media players
2. **Identification:** Extracts and matches media titles against SIMKL
3. **Tracking:** Monitors playback position
4. **Completion:** Marks as watched when threshold is reached
5. **Sync:** Updates your SIMKL profile automatically

## 🚦 Performance Notes

- **Movie identification:** 15–30 seconds (typical)
- **Mark as watched (online):** 2–8 seconds (best connection)
- **Offline scrobble:** 4–10 seconds to process title, 1–3 seconds to add to backlog after threshold

## 📝 License

MPS for SIMKL is licensed under the GNU GPL v3 License. See the [LICENSE](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/blob/main/LICENSE) file for details.

---

<div align="center">
  <p>Made with ❤️ by <a href="https://github.com/kavinthangavel">kavinthangavel</a></p>
  <p>
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/stargazers">⭐ Star us on GitHub</a> •
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues">🐞 Report Bug</a> •
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues">✨ Request Feature</a>
  </p>
</div>