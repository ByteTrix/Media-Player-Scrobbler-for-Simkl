# 🎬 Media Player Scrobbler for Simkl

[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg)]()
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ByteTrix/Media-Player-Scrobbler-for-Simkl)
<div align="center">
  <img src="simkl_mps/assets/simkl-mps.png" alt="SIMKL MPS Logo" width="120"/>
  <br/>
  <em>Automatic media tracking for all your media players</em>
</div>

## ✨ Features

- 🎮 **Supports Every Famous Media Player** (VLC, PotPlayer, MPV, MPC-HC and more)
- 🌐 **Cross-Platform** – Windows, macOS, Linux
- 🖥️ **Native Executable** – System tray, auto-update, and background service (Windows)
- 📈 **Accurate Position Tracking** – For supported players (configure via [Media Players Guide](docs/media-players.md))
- ⏱️ **Real-Time Scrobble & Watching Now** – Displays live watching/paused status on Simkl and saves unfinished progress
- 🔄 **Reverse Playback Resume** – Automatically resumes unfinished media in MPV and PotPlayer from your Simkl saved position
- ⏳ **Minimum Watch Time** – Configurable threshold before scrobbling to prevent accidental scrobbles
- 🔌 **Offline Support** – Queues updates when offline
- 🧠 **Smart Media Detection** – Intelligent filename parsing
- 🍿 **Media-Focused** – Optimized for every type of media (Movies,TV Shows and Anime)

## ⚡ Quick Start

- **Windows:** Use the [Windows Guide](docs/windows-guide.md) (EXE installer, tray app, no commands needed).
- **Linux:** Use the [Linux Guide](docs/linux-guide.md) (pipx recommended, tray app, setup command needed).
- **macOS:** Use the [Mac Guide](docs/mac-guide.md) (pip install, tray app, setup command needed, untested).

After installation, authenticate with SIMKL and **configure your media players** using the [Media Players Guide](docs/media-players.md) (this step is critical for accurate tracking).


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

Just a little reminder! If you enjoy what I create, you can support me at https://ko-fi.com/itskavin


## 🙏 Acknowledgments

- [Simkl](https://simkl.com) – API platform
- [guessit](https://github.com/guessit-io/guessit) – Filename parsing
- [iamkroot's Trakt Scrobbler](https://github.com/iamkroot/trakt-scrobbler/) – Inspiration
- [Masyk](https://github.com/masyk), [Ichika](https://github.com/ekleop) – Logo and technical guidance (SIMKL Devs)

## 🛠️ Related Tools

These tools can help organize and rename media files automatically, which can improve the accuracy and ease of scrobbling.

- [FileBot](https://www.filebot.net/) - Media File Renaming
- TVRename - TV File Data Automation (Optional)
- Shoko - Anime File Data Automation (Optional)
---

<div align="center">
  <p>Made with ❤️ by <a href="https://github.com/itskavin">kavin</a></p>
  <p>
    <a href="https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/stargazers">⭐ Star us on GitHub</a> •
    <a href="https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/issues">🐞 Report Bug</a> •
    <a href="https://github.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/issues">✨ Request Feature</a>
  </p>
</div>

