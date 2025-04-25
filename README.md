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
- 🚀 **Zero Configuration** – Works out of the box
- 🌐 **Cross-Platform** – Windows, macOS, Linux
- 🖥️ **Native Executable** – System tray, auto-update, and background service
- 📈 **Accurate Position Tracking** – For supported players
- 🔌 **Offline Support** – Queues updates when offline
- 🧠 **Smart Detection** – Intelligent filename parsing

## 🖥️ Executable Overview

MPS for SIMKL provides a professional, cross-platform executable for Windows, macOS, and Linux. The EXE bundles all dependencies, offers a native system tray interface, and supports auto-start, auto-update, and seamless background operation.

- **Background Mode:** Runs silently, tracks media, and syncs with SIMKL
- **Tray Mode:** Interactive tray icon for status, controls, and updates
- **Service/Daemon Mode:** For advanced users and servers (Linux/macOS)
- **Auto-Update:** Built-in update checker and installer

## ⚡ Quick Start

```bash
pip install simkl-mps
simkl-mps start
```

Or download the latest installer for Windows from the [Releases Page](https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/releases/latest).

## 📚 Documentation

- [Installation Guide](docs/installation.md)
- [Usage Guide](docs/usage.md)
- [Supported Media Players](docs/media-players.md)
- [Configuration](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development Guide](docs/development.md)
- [Todo List](docs/todo.md)

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

## 📝 License

See the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.

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

