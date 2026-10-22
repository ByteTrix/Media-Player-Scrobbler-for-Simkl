# ⚙️ Advanced & Developer Guide

This guide combines advanced configuration and developer documentation for MPS for SIMKL.

## 🛠️ Advanced Configuration

Settings can be customized via config files, environment variables, or command-line options. See the [Media Players Guide](media-players.md) for player-specific settings.


### Config File Locations

Use the tray menu for the most reliable path on any OS:

- `Maintenance → Open Data Folder`

Typical locations:

| Platform | Typical Data Location |
|----------|------------------------|
| Windows  | `%USERPROFILE%\kavin\simkl-mps\` |
| macOS    | `~/kavin/simkl-mps/` |
| Linux    | `~/.local/share/kavin/simkl-mps/` |

If you are upgrading from older versions, migration handles older paths automatically.

### Example Settings

```ini
# .simkl_mps.env
SIMKL_ACCESS_TOKEN=your_access_token_here
USER_ID=your_user_id
```

### Directory Whitelisting / Blacklisting

Directory filters live in `settings.json` inside your app data folder. You can allow only specific folders and/or exclude folders you never want tracked.

You can edit these lists from the tray menu: **Maintenance → Directory Filters**.

**Rules (Deny rules override allow rules):**
- If `allow_dirs` is empty, all paths are allowed by default.
- If `allow_dirs` has entries, only those paths are allowed by default.
- After allow rules are evaluated, `deny_dirs` rules are applied and can override them.

**Glob patterns are supported.** Examples: `D:\\Media\\**\\Anime\\*`, `~/Videos/**/*.mkv`.

Example `settings.json`:

```json
{
  "watch_completion_threshold": 80,
  "enable_realtime_scrobble": true,
  "enable_playback_resume": true,
  "resume_start_tolerance_seconds": 30,
  "min_rewatch_watch_seconds": 180,
  "auto_sync_interval": 120,
  "disable_notifications": false,
  "allow_dirs": [
    "D:\\Media\\Movies",
    "D:\\Media\\Shows"
  ],
  "deny_dirs": [
    "D:\\Media\\Movies\\Kids"
  ]
}
```

### Real-Time Scrobbling & Playback Resume

MPS for SIMKL supports real-time watch state reporting and reverse resume synchronization with the Simkl Playback Progress Manager:

- **`enable_realtime_scrobble`** (default: `true`): Reports live playback state (`start` and `pause`) to Simkl so your profile displays "Watching now". When playback stops before reaching `watch_completion_threshold` (with at least 30 seconds watched and progress $\ge$ 2%), your exact progress is saved to Simkl via `/scrobble/pause`. This avoids server-side auto-completion and respects any custom threshold (e.g. 65% or 90%). When playback completes or is stopped near 0%, any active playback session is cleared.
- **`enable_playback_resume`** (default: `true`): When opening media in supported players (such as MPV, MPV wrappers, and PotPlayer), checks your unfinished playbacks on Simkl. If the saved position is between 2% and your completion threshold, the player automatically seeks to that timestamp and shows an on-screen notification.
- **`resume_start_tolerance_seconds`** (default: `30`): Maximum playback position (in seconds) allowed when opening media for auto-resume to trigger. If you have already played further than this tolerance, automatic seek is skipped.

### Minimum Watch Time Threshold

- **`min_rewatch_watch_seconds`** (default: `180`): Minimum watch time (in seconds) required before marking media as watched on Simkl. Applies to both first-time watches and rewatches, preventing accidental completions when opening already-finished media or jumping directly to the credits. For videos shorter than this duration, the required watch time scales dynamically based on video length (`duration * threshold%`).
  - Configurable via `settings.json` or through the system tray menu (`Scrobbling → Minimum Watch Time`: presets for `None (0s)`, `1 Minute (60s)`, `3 Minutes (Default)`, `5 Minutes (300s)`, `10 Minutes (600s)`, or `Custom...`).


### Notifications

Notifications can be toggled from the tray menu or by editing `settings.json`.

- `disable_notifications`: set to `true` to suppress desktop notifications.
- Player web-interface connection errors are written to `simkl_mps.log` only and do not trigger notifications.

See [Media Players Guide](media-players.md) for player-specific environment variables.

---

## 👩‍💻 Developer Guide

### Project Structure

```
Media-Player-Scrobbler-for-Simkl/
  docs/                # Documentation
  simkl_mps/           # Main package
    players/           # Media player integrations
    utils/             # Utility functions
  pyproject.toml       # Project metadata
  README.md            # Project overview
  LICENSE              # License info
```

### Setup & Environment

```bash
git clone https://github.com/ByteTrix/media-player-scrobbler-for-simkl.git
cd Media-Player-Scrobbler-for-Simkl
poetry install --with dev
# or
pip install -e ".[dev]"
```

### Adding a New Media Player

1. Create a new file in `players/` (e.g. `simkl_mps/players/new_player.py`)
2. Implement a class with a `get_position_duration()` method
3. Add the player to `players/__init__.py`
4. Update detection in `window_detection.py`

### Building & Publishing

```bash
poetry build
poetry publish
```

### Architecture Overview

```mermaid
graph TD
    A[Window Detection] -->|Active Windows| B[Media Monitor]
  B -->|Window Info| C[Media Scrobbler]
  C -->|Media Title| D[Title Parser]
    D -->|Parsed Info| E[SIMKL API Client]
  E -->|Media ID & Metadata| F[Progress Tracker]
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

---

For more, see the [Usage Guide](usage.md) and [Media Players Guide](media-players.md).

