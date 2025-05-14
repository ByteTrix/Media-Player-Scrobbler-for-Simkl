# 🎬 Media Player Scrobbler for Simkl

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg)]()

<div align="center">
  <img src="simkl_mps/assets/simkl-mps.png" alt="SIMKL MPS Logo" width="120"/>
  <br/>
  <em>Automatic media tracking for all your media players</em>
</div>

## ✨ Features

- 🎮 **Universal Media Player Support** (VLC, MPV, MPC-HC and more)
- 🌐 **Cross-Platform** – Windows, macOS, Linux
- 🖥️ **Native Executable** – System tray, auto-update, and background service (Windows)
- 📈 **Accurate Position Tracking** – For supported players (configure via [Media Players Guide](docs/media-players.md))
- 🔌 **Offline Support** – Queues updates when offline
- 🧠 **Smart Media Detection** – Intelligent filename parsing
- 🍿 **Media-Focused** – Optimized for every type of media (Movies,TV Shows and Anime)

## ⚡ Quick Start

- **Windows:** Use the [Windows Guide](docs/windows-guide.md) (EXE installer, tray app, no commands needed).
- **Linux:** Use the [Linux Guide](docs/linux-guide.md) (pipx recommended, tray app, setup command needed).
- **macOS:** Use the [Mac Guide](docs/mac-guide.md) (pip install, tray app, setup command needed, untested).

After installation, authenticate with SIMKL and **configure your media players** using the [Media Players Guide](docs/media-players.md) (this step is critical for accurate tracking).

## 📚 Documentation

- [Windows Guide](docs/windows-guide.md)
- [Linux Guide](docs/linux-guide.md)
- [Mac Guide](docs/mac-guide.md)
- [Supported Media Players](docs/media-players.md)
- [Usage Guide](docs/usage.md)
- [Local Watch History](docs/watch-history.md)
- [Advanced & Developer Guide](docs/configuration.md)
- [Troubleshooting Guide](docs/troubleshooting.md)
- [Todo List](docs/todo.md)

## 🔍 How It Works

```mermaid
graph LR
    A[Media Player] -->|Player Title| B[Simkl Scrobbler]
    B -->|Parse Title| C[Media Identification]
    C -->|Track Progress| D[Simkl API]
    D -->|Mark as Watched| E[Simkl Profile]
    
    style A fill:#d5f5e3,stroke:#333,stroke-width:2px
    style E fill:#d5f5e3,stroke:#333,stroke-width:2px
```

## 🚦 Performance Notes

**Online:**
- Player Detection: ~4.2 sec
- Media Info Scrobble: ~3.7 sec
- Notification: ~1.5 sec
- Completion Detection Delay: ~5.2 sec
- Completion Sync: ~13.3 sec
- Completion Notification: ~1.5 sec

**Offline:**
- Media Scrobble: ~1.2 sec
- Notification: ~0.5 sec
- Completion Save: ~3 sec
- Completion Notification: ~0.5 sec

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
- [masyk](https://github.com/masyk) – Logo and technical guidance (SIMKL Dev)

## 🛠️ Related Tools

These tools can help organize and rename media files automatically, which can improve the accuracy and ease of scrobbling.

- [FileBot](https://www.filebot.net/) - Media File Renaming
- TVRename - TV File Data Automation (Optional)
- Shoko - Anime File Data Automation (Optional)
---

<div align="center">
  <p>Made with ❤️ by <a href="https://github.com/kavinthangavel">kavinthangavel</a></p>
  <p>
    <a href="https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/stargazers">⭐ Star us on GitHub</a> •
    <a href="https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/issues">🐞 Report Bug</a> •
    <a href="https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/issues">✨ Request Feature</a>
  </p>
</div>

