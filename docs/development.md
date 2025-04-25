# 💻 Development Guide

This guide is for developers and contributors to Media Player Scrobbler for SIMKL.

## 📁 Project Structure

```
simkl-movie-tracker/
├── docs/                # Documentation
├── simkl_mps/           # Main package
│   ├── __init__.py
│   ├── ...
│   ├── players/         # Media player integrations
│   └── utils/           # Utility functions
├── tests/               # Test suite
├── pyproject.toml       # Project metadata
├── README.md            # Project overview
└── LICENSE              # License info
```

## ⚙️ Setup & Environment

1. Clone the repo:
   ```bash
   git clone https://github.com/kavinthangavel/simkl-movie-tracker.git
   cd simkl-movie-tracker
   ```
2. Install dependencies:
   ```bash
   poetry install --with dev
   # or
   pip install -e ".[dev]"
   ```
3. (Optional) Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

<!-- ## 🧪 Testing & Code Style

- Run all tests:
  ```bash
  poetry run pytest
  ```
- Run with coverage:
  ```bash
  poetry run pytest --cov=simkl_mps
  ```
- Lint code:
  ```bash
  poetry run flake8 simkl_mps
  ``` -->

## ➕ Adding a New Media Player

1. Create a new file in `players/` (e.g. `simkl_mps/players/new_player.py`)
2. Implement a class with a `get_position_duration()` method
3. Add the player to `players/__init__.py`
4. Update detection in `window_detection.py`

## 📦 Building & Publishing

- Build:
  ```bash
  poetry build
  ```
- Publish to PyPI:
  ```bash
  poetry publish
  ```

## 🤝 Contributor Info

- Fork, branch, commit, push, and open a Pull Request
- For API access, register a client at https://simkl.com/settings/developer/
- Use `--debug` for detailed logs
- Test integrations separately if needed

---

## 🏗️ Architecture Overview

MPS for SIMKL uses a modular architecture:

```mermaid
graph TD
    A[Window Detection] -->|Active Windows| B[Media Monitor]
    B -->|Window Info| C[Movie Scrobbler]
    C -->|Movie Title| D[Title Parser]
    D -->|Parsed Info| E[SIMKL API Client]
    E -->|Movie ID & Metadata| F[Progress Tracker]
    F -->|Position Updates| G{Completion Check}
    G -->|>80% Complete| H[Mark as Watched]
    G -->|<80% Complete| F
    I[Player Integrations] -->|Position & Duration| F
    J[Backlog Cleaner] <-->|Offline Queue| C
    K[Media Cache] <-->|Movie Info| C
    L[Tray Application] <-->|Status & Controls| B
    I -.->|Connectivity| M{Internet Available?}
    M -->|Yes| E
    M -->|No| J
    style A fill:#d5f5e3,stroke:#333,stroke-width:2px
    style E fill:#f9d5e5,stroke:#333,stroke-width:2px
    style H fill:#f9d5e5,stroke:#333,stroke-width:2px
    style I fill:#d5eef7,stroke:#333,stroke-width:2px
```

### Component Roles

| Component         | File                  | Description                                 |
|------------------|-----------------------|---------------------------------------------|
| Window Detection | `window_detection.py` | OS-specific window monitoring               |
| Media Monitor    | `monitor.py`          | Coordinates detection and status tracking   |
| Movie Scrobbler  | `movie_scrobbler.py`  | Core tracking and scrobbling logic          |
| Player Integrations | `players/*.py`      | Player APIs for position tracking           |
| SIMKL API Client | `simkl_api.py`        | Auth and SIMKL communication                |
| Backlog Cleaner  | `backlog_cleaner.py`  | Offline queue management                    |
| Media Cache      | `media_cache.py`      | Local movie metadata                        |
| Tray Application | `tray_app.py`         | System tray UI                              |

---

## 🔄 Data Flow

```mermaid
sequenceDiagram
    participant MP as Media Player
    participant WD as Window Detection
    participant SC as Movie Scrobbler
    participant PI as Player Integration
    participant API as SIMKL API
    participant UI as Tray UI
    MP->>WD: Active Window (title)
    WD->>SC: Window Info
    SC->>SC: Parse Movie Title
    SC->>API: Search Movie
    API->>SC: Movie Metadata
    loop Every Poll Interval
        SC->>PI: Request Position
        PI->>MP: Connect to Player API
        MP->>PI: Position & Duration
        PI->>SC: Position Data
        SC->>SC: Update Progress
    end
    alt Progress >= Threshold
        SC->>API: Mark as Watched
        API->>SC: Success/Failure
        SC->>UI: Show Notification
    else No Internet
        SC->>SC: Add to Backlog
    end
```

---

## 🧩 Class Relationships

```mermaid
classDiagram
    class SimklScrobbler {
        +initialize()
        +start()
        +stop()
        +pause()
        +resume()
    }
    class MediaTracker {
        -monitor: Monitor
        +start()
        +stop()
        +set_credentials()
    }
    class Monitor {
        -scrobbler: MovieScrobbler
        -running: bool
        +start()
        +stop()
        +set_credentials()
    }
    class MovieScrobbler {
        -currently_tracking: str
        -track_start_time: datetime
        -state: int
        +set_credentials()
        +process_window()
        +process_backlog()
    }
    class PlayerIntegration {
        +get_position_duration()
    }
    class SimklAPI {
        +authenticate()
        +search_movie()
        +mark_as_watched()
    }
    class TrayApp {
        -scrobbler: SimklScrobbler
        -tray_icon
        +run()
        +start_monitoring()
        +pause_monitoring()
        +process_backlog()
    }
    SimklScrobbler *-- MediaTracker
    MediaTracker *-- Monitor
    Monitor *-- MovieScrobbler
    MovieScrobbler -- PlayerIntegration
    MovieScrobbler -- SimklAPI
    TrayApp -- SimklScrobbler
```

---

## 🏁 Execution Flow

```mermaid
graph TD
    A[User Starts Application] --> B{Start Method}
    B -->|CLI 'start'| C[Background Mode]
    B -->|CLI 'tray'| D[Tray Mode]
    C --> E[Create SimklScrobbler]
    D --> F[Create TrayApp]
    E --> G[Initialize]
    F --> H[Create SimklScrobbler]
    H --> G
    G --> I{First Run?}
    I -->|Yes| J[Auth Flow]
    I -->|No| K[Load Credentials]
    J --> L[Start Monitoring]
    K --> L
    L --> M[Monitor Loop]
    M --> N[Detect Windows]
    N --> O[Process Windows]
    O --> P[Update Progress]
    P --> M
    style A fill:#4285f4,stroke:#333,stroke-width:2px,color:#fff
    style J fill:#fbbc05,stroke:#333,stroke-width:2px
    style L fill:#34a853,stroke:#333,stroke-width:2px,color:#fff
```

---

## 🖥️ Platform Abstraction

```mermaid
graph TB
    A[Platform-Specific Modules] --> B{Operating System}
    B -->|Windows| C[Windows Implementation]
    B -->|macOS| D[macOS Implementation]
    B -->|Linux| E[Linux Implementation]
    C --> F[Common Interface]
    D --> F
    E --> F
    F --> G[Platform-Independent Logic]
    subgraph "Platform-Specific Code"
    C
    D
    E
    end
    subgraph "Cross-Platform Code"
    F
    G
    end
    style A fill:#f9d5e5,stroke:#333,stroke-width:2px
    style G fill:#d5eef7,stroke:#333,stroke-width:2px
```

**Key abstraction points:**
- Window detection
- System tray integration
- File system access
- Process management
- Notifications
