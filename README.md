# 🎬 Simkl Scrobbler

[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-cross--platform-blue.svg)](https://www.microsoft.com/windows)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Last Updated](https://img.shields.io/badge/last%20updated-April%202025-brightgreen.svg)]()

A powerful cross-platform automatic scrobbler for [Simkl](https://simkl.com) that seamlessly tracks your movie watching progress across multiple media players. Zero configuration required - it just works!

<div align="center">
  <img src="https://eu.simkl.in/img_blog_2012/logo.png" alt="Simkl Logo" width="200"/>
  <br/>
  <em>Inspired by <a href="https://github.com/iamkroot/trakt-scrobbler/">iamkroot's Trakt Scrobbler</a></em>
</div>

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Features](#-features)
- [Supported Media Players](#-supported-media-players)
- [Installation](#-installation)
- [Usage](#-usage)
- [Advanced Configuration](#️-advanced-configuration)
- [How It Works](#-how-it-works)
- [Testing](#-testing)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)

## ⚡ Quick Start

```bash
# Install with pip (standard)
pip install simkl-scrobbler

# Initialize the tracker
simkl-scrobbler init

# Start tracking your movies
simkl-scrobbler start
```

## 🚀 Features

- **Zero Configuration** - Works with most media players out of the box
- **Cross-Platform** - Runs on Windows, macOS, and Linux
- **Smart Detection** - Intelligent movie recognition using guessit library
- *Background Operation (Still Working on it)* - Runs silently in the background
- **Progress Tracking** - Monitors viewing progress across sessions
- **Automatic Scrobbling** - Marks movies as watched after 80% completion
- **Offline Support** - Maintains sync backlog when offline
- **Resource Efficient** - Minimal CPU and memory footprint
- **Runtime Detection** - Uses actual movie runtime from Simkl API
- **Multi-Window Monitoring** - Can detect and track movies even in non-active windows
- **Enhanced Position Tracking** - Monitors actual player position for better completion detection
- **Comprehensive Logging** - Detailed playback events for debugging and analysis

## 🎥 Supported Media Players

The following media players are supported across platforms:

### Windows

| Media Player | Support Status | Position Detection |
|-------------|----------------|-------------------|
| VLC Media Player | ✅ Fully Supported | ✅ (with web interface) |
| MPC-HC/BE | ✅ Fully Supported | ✅ (with web interface) |
| Windows Media Player | ✅ Fully Supported | ⚠️ Title only |
| MPV Player | ✅ Fully Supported | ⚠️ Title only |
| PotPlayer | ✅ Fully Supported | ⚠️ Title only |
| SMPlayer | ✅ Fully Supported | ⚠️ Title only |
| KMPlayer | ✅ Fully Supported | ⚠️ Title only |
| GOM Player | ✅ Fully Supported | ⚠️ Title only |

### macOS

| Media Player | Support Status | Position Detection |
|-------------|----------------|-------------------|
| VLC Media Player | ✅ Fully Supported | ✅ (with web interface) |
| MPV Player | ✅ Fully Supported | ⚠️ Title only |
| IINA | ✅ Fully Supported | ⚠️ Title only |
| QuickTime Player | ✅ Basic Support | ⚠️ Title only |
| Elmedia Player | ✅ Basic Support | ⚠️ Title only |
| Movist/Movist Pro | ✅ Basic Support | ⚠️ Title only |

### Linux

| Media Player | Support Status | Position Detection |
|-------------|----------------|-------------------|
| VLC Media Player | ✅ Fully Supported | ✅ (with web interface) |
| MPV Player | ✅ Fully Supported | ⚠️ Title only |
| SMPlayer | ✅ Fully Supported | ⚠️ Title only |
| Totem | ✅ Basic Support | ⚠️ Title only |
| Celluloid | ✅ Basic Support | ⚠️ Title only |
| Kaffeine | ✅ Basic Support | ⚠️ Title only |
| Dragon Player | ✅ Basic Support | ⚠️ Title only |
| Parole | ✅ Basic Support | ⚠️ Title only |

The scrobbler monitors the active/background windows to detect media files currently being played. For VLC with web interface enabled, it can also get precise playback position information across all supported platforms.

## 📥 Installation

### Standard Installation (Recommended)

1.  **Ensure you have Python 3.7 or higher installed, and `pip` is available.**
    Check by running `python --version` and `pip --version`.

2.  **Install using pip:**
    ```bash
    pip install simkl-scrobbler
    ```
    This will make the `simkl-scrobbler` command available globally.

3.  **Initialize SIMKL Scrobbler:**
    ```bash
    simkl-scrobbler init
    ```
    Follow the prompts to authorize the application with your Simkl account using the PIN method.

4.  **Start tracking:**
    ```bash
    simkl-scrobbler start
    ```

### Installation with pipx (Alternative)

`pipx` installs packages into isolated environments.

1.  **Install pipx:**
    ```bash
    python -m pip install --user pipx
    python -m pipx ensurepath
    ```
    (Restart your terminal after running `ensurepath`)

2.  **Install SIMKL Scrobbler with pipx:**
    ```bash
    pipx install simkl-scrobbler
    ```

3.  **Initialize and start as above.**

### Installing as a Windows Service (Windows Only)

To have SIMKL Scrobbler start automatically with Windows:

```bash
simkl-scrobbler install-service
```
Follow the on-screen instructions.

### Development Installation (Using Poetry)

If you want to contribute or run from the source code:

1.  **Ensure Python 3.7+ and [Poetry](https://python-poetry.org/docs/#installation) are installed.**

2.  **Clone the repository:**
    ```bash
    git clone https://github.com/kavinthangavel/simkl-scrobbler.git
    cd simkl-scrobbler
    ```

3.  **Install dependencies using Poetry:**
    ```bash
    poetry install --with dev
    ```
    This installs the main package and development dependencies (like `pytest`, `flake8`).

4.  **Run commands using `poetry run`:**
    ```bash
    poetry run simkl-scrobbler init
    poetry run simkl-scrobbler start
    # To run tests (see Testing section)
    poetry run python tests/master_test.py --test-mode
    ```

## 🎮 Usage

The tracker runs silently in the background, automatically detecting and tracking movie playback in supported media players. Basic commands:

```bash
# Initialize the tracker (first-time setup)
simkl-scrobbler init

# Start tracking in the foreground
simkl-scrobbler start

# Install as a Windows service (Windows only)
simkl-scrobbler install-service

# Show help
simkl-scrobbler --help
```

### Monitoring and Logs

```bash
# On Windows:
type simkl_scrobbler.log

# On macOS/Linux:
cat simkl_scrobbler.log

# Check detailed playback events
# On Windows:
type simkl_scrobbler\playback_log.jsonl

# On macOS/Linux:
cat simkl_scrobbler/playback_log.jsonl
```

## ⚙️ Advanced Configuration

Key settings in `media_tracker.py`:
```python
DEFAULT_POLL_INTERVAL = 10  # Player check interval (seconds)
COMPLETION_THRESHOLD = 80   # Mark as watched threshold (percent)
VIDEO_PLAYER_EXECUTABLES = {...}  # Platform-specific supported players
```

### Player Web Interface Setup (for position tracking)

For enhanced position tracking with VLC:

**VLC Media Player on Windows:**
1. Go to Tools > Preferences
2. Select "All" settings mode (bottom left)
3. Navigate to Interface > Main interfaces
4. Check "Web" option
5. Set a password if desired (leave empty for no password)
6. Restart VLC

**VLC Media Player on macOS:**
1. Open VLC > Preferences
2. Click "Show All" (bottom left)
3. Navigate to Interface > Main Interfaces
4. Check "Web" option
5. Set a password if desired (leave empty for no password)
6. Restart VLC

**VLC Media Player on Linux:**
1. Go to Tools > Preferences
2. Click "All" settings (bottom left)
3. Navigate to Interface > Main interfaces
4. Check "Web" option
5. Set a password if desired (leave empty for no password)
6. Restart VLC

**MPC-HC/BE (Windows only):**
1. Go to View > Options > Player > Web Interface
2. Check "Listen on port:" (default 13579)

## 🔍 How It Works

```mermaid
graph LR
    A[Monitor Windows/Processes] --> B[Detect Player]
    B --> C[Extract Filename]
    C --> D[Parse with guessit]
    D --> E[Match Movie]
    E --> F[Track Progress]
    F --> G{>80% Complete?}
    G -->|Yes| H[Mark Watched]
    G -->|No| F
```

1. **Window/Process Detection**: Uses platform-specific methods to monitor active and background windows/processes
2. **Title Extraction**: Parses window title for filename/movie info
3. **Smart Parsing**: Uses guessit library to intelligently extract movie title and year
4. **Movie Matching**: Queries Simkl API to identify the movie
5. **Progress Tracking**: Monitors playback position directly from player (when available) or estimates based on time
6. **Auto-marking**: Updates Simkl when 80% threshold reached
7. **Offline Handling**: Queues failed updates in backlog for future retry

<!-- ## 🧪 Testing

SIMKL Scrobbler includes a comprehensive test suite to ensure reliability and functionality:

```bash
# Ensure development dependencies are installed (poetry install --with dev)
# Run the full test suite with mock API responses
poetry run python tests/master_test.py --test-mode

# Run specific test categories
poetry run python tests/master_test.py --test-mode --skip-api-errors --skip-offline

# Run tests with a real video file
poetry run python tests/master_test.py --test-mode --test-real-playback --video-file "path/to/movie.mp4"

# Get test help and options
poetry run python tests/master_test.py --help
```

### Test Suite Features:

- **Interactive Visual Output**: Modern colorized terminal display with progress bars and structured results
- **API Integration Tests**: Verifies Simkl API interactions work correctly
- **Error Handling Tests**: Ensures graceful handling of API and network failures
- **Offline Mode Testing**: Validates offline tracking and backlog sync capabilities
- **Movie Completion Tests**: Confirms proper threshold detection and marking behavior
- **Cache and Parsing Tests**: Validates movie title extraction from window titles
- **Media Player Interface Tests**: Verifies connectivity with player web interfaces
- **Real Playback Tests**: End-to-end testing with actual media player launch
- **Comprehensive Results**: Summary of all tests with timing and detailed error reporting
- **Export to JSON**: Test results saved to `test_results.json` for analysis

### Test Command Options:

| Option | Description |
|--------|-------------|
| `--test-mode` | Run with mock API responses (no actual API calls) |
| `--movie-title TITLE` | Test with specific movie title |
| `--video-file PATH` | Path to video file for real playback testing |
| `--test-real-playback` | Run real playback test with media player |
| `--skip-api` | Skip API integration tests |
| `--skip-api-errors` | Skip API error handling tests |
| `--skip-offline` | Skip offline tracking tests |
| `--skip-completion` | Skip movie completion tests |
| `--skip-cache` | Skip cache functionality tests |
| `--skip-title-parsing` | Skip title parsing tests |
| `--verbose` | Show more detailed test information |
| `--show-version` | Show test suite version and exit |

The master test suite automatically discovers and configures media players installed on your system, and sets up their web interfaces for enhanced position tracking when available. -->

## 🔧 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Movie not detected | Ensure media player shows filename in window title |
| No auto-marking | Check log file for API errors |
| Incorrect movie | Include year in filename: "Movie (2023).mp4" |
| Player not detected | Verify player is in supported list for your platform |
| Permission error | Run with appropriate permissions for your platform |
| Movie title parsing failed | Use standard naming: "Movie.Name.2023.mp4" |
| Position tracking not working | Enable web interface in VLC or MPC-HC/BE |
| VLC web interface shows no movie | Restart VLC after enabling web interface |
| Window detection not working on Linux | Install required utilities: xdotool, wmctrl |
| AppleScript error on macOS | Grant necessary permissions in System Preferences > Security & Privacy |

### Logs and Debugging
```bash
# Check main application log (Windows)
type simkl_scrobbler.log
# macOS/Linux
cat simkl_scrobbler.log

# Check detailed playback events (Windows)
type simkl_scrobbler\playback_log.jsonl
# macOS/Linux
cat simkl_scrobbler/playback_log.jsonl

```

### Diagnostic Commands

If you're having issues, these commands can help diagnose problems:

```bash
# Check Python version
python --version

# Verify installed dependencies (using Poetry)
poetry show

# Check network connectivity to Simkl API
# Windows (PowerShell)
Invoke-WebRequest -Uri https://api.simkl.com/ -Method Head
# macOS/Linux
curl -I https://api.simkl.com/

# List running media player processes
# Windows
tasklist | findstr "vlc mpc wmplayer"
# macOS
ps aux | grep -E "VLC|mpv|IINA"
# Linux
ps aux | grep -E "vlc|mpv|totem|celluloid"
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgments

- [Simkl](https://simkl.com) for their excellent API
- [iamkroot's Trakt Scrobbler](https://github.com/iamkroot/trakt-scrobbler/) for inspiration
- [guessit](https://github.com/guessit-io/guessit) for powerful video filename parsing
<!-- - All [contributors](https://github.com/kavinthangavel/simkl-scrobbler/graphs/contributors) -->

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📝 Roadmap

- [ ] Tray or Background Service with Notification
- [x] Add Linux and macOS support
- [x] Add real-time position tracking for supported players
- [x] Implement multi-window monitoring
- [ ] Create automated tests

