# 💻 Development Guide

This document provides information for developers who want to contribute to Simkl Scrobbler.

## 📂 Project Structure

```
simkl-movie-tracker/
├── docs/                    # Documentation
├── simkl_mps/         # Main package
│   ├── __init__.py          # Package initialization
│   ├── backlog_cleaner.py   # Handles offline queue
│   ├── cli.py               # Command-line interface
│   ├── main.py              # Application entry point
│   ├── media_cache.py       # Movie info caching
│   ├── media_tracker.py     # Main tracking coordination
│   ├── monitor.py           # Window monitoring
│   ├── movie_scrobbler.py   # Movie tracking and Simkl integration
│   ├── service_manager.py   # System service management
│   ├── service_runner.py    # Background service implementation
│   ├── simkl_api.py         # Simkl API interactions
│   ├── tray_app.py          # System tray application
│   ├── window_detection.py  # Cross-platform window detection
│   ├── players/             # Media player integrations
│   │   ├── __init__.py
│   │   ├── mpc.py           # MPC-HC/BE integration
│   │   ├── mpv.py           # MPV integration
│   │   ├── potplayer.py     # PotPlayer integration
│   │   └── vlc.py           # VLC integration
│   └── utils/               # Utility functions and constants
├── tests/                   # Test suite
├── .gitignore               # Git ignore patterns
├── pyproject.toml           # Project metadata and dependencies
├── README.md                # Project overview
└── LICENSE                  # License information
```

## 🚀 Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/kavinthangavel/simkl-movie-tracker.git
   cd simkl-movie-tracker
   ```

2. Set up the development environment:
   ```bash
   # Using Poetry (recommended)
   poetry install --with dev
   
   # Or using pip
   pip install -e ".[dev]"
   ```

3. Set up pre-commit hooks (optional):
   ```bash
   pre-commit install
   ```

## 🧪 Running Tests

```bash
# Run tests with pytest
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=simkl_mps

# Run specific test file
poetry run pytest tests/test_specific_file.py
```

## 📝 Code Style

This project follows PEP 8 style guidelines. Use flake8 to check your code:

```bash
poetry run flake8 simkl_mps
```

## ➕ Adding a New Media Player

To add support for a new media player:

1. Create a new file in the `players/` directory (e.g., `simkl_mps/players/new_player.py`)
2. Implement a class that follows the player integration interface:
   ```python
   class NewPlayerIntegration:
       def __init__(self):
           # Initialize player connection
           pass
           
       def get_position_duration(self, process_name=None):
           # Return (position_seconds, duration_seconds) tuple or (None, None)
           pass
   ```
3. Add the player to `players/__init__.py`
4. Update window detection to recognize the player in `window_detection.py`

## 📦 Building and Publishing

```bash
# Build distribution packages
poetry build

# Publish to PyPI (requires credentials)
poetry publish
```

## 🔄 Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and commit them: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request against the main repository

## 🔑 API Access

For development, you can use the default client ID or register your own:

1. Go to https://simkl.com/settings/developer/
2. Create a new application
3. Set the redirect URL to `urn:ietf:wg:oauth:2.0:oob`
4. Use the client ID in your development environment:
   ```
   SIMKL_CLIENT_ID=your_client_id
   ```

## 🔍 Debugging Tips

- Use the `--debug` flag to enable detailed logging: `simkl-mps start --debug`
- Check logs in the application data directory
- Use Python's debugger (pdb) or an IDE like PyCharm or VS Code for step-by-step debugging
- Test player integration separately using the player-specific test scripts

## 🏗️ Architecture Overview

Simkl Scrobbler uses a modular architecture:

1. **🪟 Window Detection Layer**: Platform-specific code to detect media player windows
2. **🎮 Media Player Integration Layer**: Interfaces with specific players to get playback information
3. **🎬 Movie Identification Layer**: Parses titles and identifies movies via Simkl API
4. **📊 Progress Tracking Layer**: Monitors playback and determines completion
5. **🔌 Simkl API Layer**: Handles authentication and scrobbling to Simkl

This separation allows for easy maintenance and extension of individual components.

### Architecture Diagram

```mermaid
graph TD
    A[Window Detection] -->|Active Windows| B[Player Recognition]
    B -->|Window Info| C[Title Extraction]
    C -->|Movie Title| D[guessit Parser]
    D -->|Parsed Info| E[Simkl Search]
    E -->|Movie ID| F[Progress Tracker]
    F -->|Position Updates| G{Completion Check}
    G -->|>80%| H[Mark as Watched]
    G -->|<80%| F
    
    I[Player Integration] -->|Position Data| F
    J[OS-specific APIs] --> A
    
    style A fill:#d5f5e3,stroke:#333,stroke-width:2px
    style H fill:#f9d5e5,stroke:#333,stroke-width:2px
    style I fill:#d5eef7,stroke:#333,stroke-width:2px
    style J fill:#f7dc6f,stroke:#333,stroke-width:2px
```
