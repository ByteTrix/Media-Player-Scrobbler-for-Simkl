# 🎬 Media Player Scrobbler for Simkl

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg)]()

<div align="center">
  <img src="simkl_mps/assets/simkl-mps.png" alt="SIMKL MPS Logo" width="120"/>
  <br/>
  <em>Automatic movie tracking for all your media players</em>
</div>

## ✨ Features

- 🎮 **Universal Media Player Support** (VLC, MPV, MPC-HC, PotPlayer, and more)
- 🌐 **Cross-Platform** – Windows, (macOS, Linux)- Testing in Progress
- 🖥️ **Native Executable** – System tray, auto-update, and background service (Windows)
- 📈 **Accurate Position Tracking** – For supported players Need to Configure [Media Player](docs/media-players.md)
- 🔌 **Offline Support** – Queues updates when offline
- 🧠 **Smart Movie Detection** – Intelligent filename parsing
- 🍿 **Movie-Focused** – Currently optimized for movies (TV show tracking planned for future updates)

## 🖥️ Executable Overview

MPS for SIMKL provides a professional, cross-platform executable for Windows, macOS, and Linux. The EXE bundles all dependencies, offers a native system tray interface, and supports auto-start, auto-update, and seamless background operation.

- **Background Mode:** Runs silently, tracks media, and syncs with SIMKL
- **Tray Mode:** Interactive tray icon for status, controls, and updates
- **Service/Daemon Mode:** For advanced users and servers (Linux/macOS)
- **Auto-Update:** Built-in update checker and installer

## ⚡ Quick Start

Download the latest installer for Windows from the [Releases Page](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/releases/latest).

> Must Setup [Media Player](docs/media-player.md)
> Detailed Guide about [Windows installer](docs/windows-guide.md)

or

```bash
#mac/linux testing is still in progress
pip install simkl-mps
simkl-mps start
```


## 📚 Documentation

- [Installation Guide](docs/installation.md) - Platform-specific installation instructions
- [Windows Guide](docs/windows-guide.md) - Full Guide for Windows Installer
- [Usage Guide](docs/usage.md) - Getting started and day-to-day usage
- [Supported Media Players](docs/media-players.md) - Compatible players and configuration
- [Configuration](docs/configuration.md) - Advanced settings and options
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Development Guide](docs/development.md) - Contributing to the project
- [Todo List](docs/todo.md) - Upcoming features and improvements

## 🔍 How It Works

```mermaid
graph LR
    A[Media Player] -->|Window Title| B[simkl-mps]
    B -->|Parse Title| C[Movie Identification]
    C -->|Track Progress| D[Simkl API]
    D -->|Mark as Watched| E[Simkl Profile]
    style A fill:#d5f5e3,stroke:#333,stroke-width:2px
    style E fill:#d5f5e3,stroke:#333,stroke-width:2px
```

## 🚦 Performance Notes

- **Movie identification:** 15–25 seconds (typical)
- **Mark as watched (online):** 2–8 seconds (best connection)
- **Offline scrobble:** 4–10 seconds to process title, 1–3 seconds to add to backlog after threshold

## 📝 License

See the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.

## ☕ Support & Donate

If you find this project useful, consider supporting development:
[Donate via CoinDrop](https://coindrop.to/kavinthangavel)

## 🙏 Acknowledgments

- [Simkl](https://simkl.com) – API platform
- [guessit](https://github.com/guessit-io/guessit) – Filename parsing
- [iamkroot's Trakt Scrobbler](https://github.com/iamkroot/trakt-scrobbler/) – Inspiration
- [masyk](https://github.com/masyk) – Logo and technical guidance

---

<div align="center">
  <p>Made with ❤️ by <a href="https://github.com/kavinthangavel">kavinthangavel</a></p>
  <p>
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/stargazers">⭐ Star us on GitHub</a> •
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues">🐞 Report Bug</a> •
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues">✨ Request Feature</a>
  </p>
</div>

