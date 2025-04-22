# 🎬 Simkl Scrobbler

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A cross-platform automatic movie tracker that seamlessly integrates with [Simkl](https://simkl.com). It monitors your media players and automatically updates your watched history - no manual scrobbling required! ✨

<div align="center">
  <img src="https://eu.simkl.in/img_blog_2012/logo.png" alt="Simkl Logo" width="150"/>
  <br/>
  <em>Your movies, automatically tracked whenever you watch them</em>
</div>

## ✨ Features

- 🎮 **Universal Media Player Support** - Works with VLC, MPV, MPC-HC, PotPlayer, and many others
- 🚀 **Zero Configuration** - Smart detection works out of the box
- 🌍 **Cross-Platform** - Full support for Windows, macOS, and Linux
- 🔄 **Multiple Run Modes** - Foreground, system tray, or background service
- 📊 **Position Tracking** - Monitors actual playback position for supported players
- 🔌 **Offline Support** - Queues updates when you're not connected
- 🧠 **Smart Detection** - Intelligent movie recognition from filenames

## ⚡ Quick Start

```bash
# 📥 Install
pip install simkl-mps

# 🔑 Set up with your Simkl account
simkl-mps init

# 🚀 Start tracking your movies
simkl-mps start
```

## 📚 Documentation

For detailed instructions, please see the documentation:

- 📋 [Installation Guide](docs/installation.md)
- 🎮 [Usage Guide](docs/usage.md)
- 🎥 [Supported Media Players](docs/media-players.md)
- ⚙️ [Advanced Configuration](docs/configuration.md)
- 🔧 [Troubleshooting](docs/troubleshooting.md)
- 💻 [Development Guide](docs/development.md)
- 📝 [Todo List](docs/todo.md) - Completed and planned features

## 🔍 How It Works

The application monitors your active windows to detect media players, extracts the movie title, and uses the Simkl API to identify and track your watching progress. When you've watched enough of a movie (default: 80%), it's automatically marked as watched in your Simkl account! 🎉

```mermaid
graph LR
    A[Media Player] -->|Window Title| B[Simkl Scrobbler]
    B -->|Parse Title| C[Movie Identification]
    C -->|Track Progress| D[Simkl API]
    D -->|Mark as Watched| E[Simkl Profile]
    
    style A fill:#f9d5e5,stroke:#333,stroke-width:2px
    style E fill:#d5f5e3,stroke:#333,stroke-width:2px
```

## 📊 Supported Players

<div align="center">
  <table>
    <tr>
      <td align="center"><img src="https://upload.wikimedia.org/wikipedia/commons/3/38/VLC_icon.png" width="40px"/><br/>VLC</td>
      <td align="center"><img src="https://upload.wikimedia.org/wikipedia/commons/7/76/Media_Player_Classic_logo.png" width="40px"/><br/>MPC-HC</td>
      <td align="center"><img src="https://upload.wikimedia.org/wikipedia/commons/7/73/Mpv_logo_%28official%29.png" width="40px"/><br/>MPV</td>
      <td align="center">🎮<br/>Many More</td>
    </tr>
  </table>
</div>

## 📄 License

See the [LICENSE](LICENSE) file for details.

## 👥 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🙏 Acknowledgments

- [Simkl](https://simkl.com) for their excellent API
- [guessit](https://github.com/guessit-io/guessit) for powerful video filename parsing
- [iamkroot's Trakt Scrobbler](https://github.com/iamkroot/trakt-scrobbler/) for inspiration

---

<div align="center">
  <p>Made with ❤️ by <a href="https://github.com/kavinthangavel">kavinthangavel</a></p>
  <p>
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/stargazers">⭐ Star us on GitHub</a> •
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues">🐛 Report Bug</a> •
    <a href="https://github.com/kavinthangavel/media-player-scrobbler-for-simkl/issues">✨ Request Feature</a>
  </p>
</div>

