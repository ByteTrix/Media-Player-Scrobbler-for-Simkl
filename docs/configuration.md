# ⚙️ Advanced Configuration

This document describes advanced configuration options for Media Player Scrobbler for SIMKL.

## 📁 Configuration Files

The primary configuration is stored in `.simkl_mps.env` in the application data directory:

- Windows: `%APPDATA%\kavinthangavel\media-player-scrobbler-for-simkl\.simkl_mps.env`
- macOS: `~/Library/Application Support/kavinthangavel/media-player-scrobbler-for-simkl/.simkl_mps.env`
- Linux: `~/.local/share/kavinthangavel/media-player-scrobbler-for-simkl/.simkl_mps.env`

## 🔧 Environment Variables

You can customize behavior by setting these environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SIMKL_CLIENT_ID` | Custom API client ID | Built-in ID |
| `SIMKL_ACCESS_TOKEN` | Manual access token | Auto-generated |
| `SIMKL_LOG_LEVEL` | Logging verbosity (DEBUG, INFO, etc.) | INFO |
| `SIMKL_POLL_INTERVAL` | Window check frequency (seconds) | 10 |
| `SIMKL_COMPLETION_THRESHOLD` | % to mark as watched | 80 |

## 📊 Application Data

Key files and their locations:

| File | Purpose | Location |
|------|---------|----------|
| `simkl_mps.log` | Main application log | APP_DATA_DIR/kavinthangavel/media-player-scrobbler-for-simkl |
| `playback_log.jsonl` | Detailed event log | APP_DATA_DIR/kavinthangavel/media-player-scrobbler-for-simkl |
| `media_cache.json` | Movie info cache | APP_DATA_DIR/kavinthangavel/media-player-scrobbler-for-simkl |
| `backlog.json` | Offline queue | APP_DATA_DIR/kavinthangavel/media-player-scrobbler-for-simkl |
| `.simkl_mps.env` | Configuration | APP_DATA_DIR/kavinthangavel/media-player-scrobbler-for-simkl |

Where `APP_DATA_DIR` is platform-specific:
- Windows: `%APPDATA%`
- macOS: `~/Library/Application Support`
- Linux: `~/.local/share`

## 🛠️ Advanced Settings

### ⏱️ Customizing the Completion Threshold

By default, movies are marked as watched after reaching 80% completion. To change this:

1. Create or edit `.simkl_mps.env` in the application data directory
2. Add: `SIMKL_COMPLETION_THRESHOLD=85` (or your preferred percentage)

### ⏲️ Custom Polling Interval

Adjust how frequently the application checks for active movie windows:

```
SIMKL_POLL_INTERVAL=5  # Check every 5 seconds (default is 10)
```

Lower values provide more responsive detection but use slightly more resources.

### 📝 Logging Levels

Control the verbosity of logging:

```
SIMKL_LOG_LEVEL=DEBUG  # Verbose logging for troubleshooting
```

Available levels (from most to least verbose):
- `DEBUG`: All messages, including detailed debugging information
- `INFO`: General operational events (default)
- `WARNING`: Potential issues that don't prevent operation
- `ERROR`: Errors that prevent specific operations
- `CRITICAL`: Critical errors that prevent application function

### 🔑 Custom Simkl API Client

To use your own Simkl API client:

1. Register a new client at https://simkl.com/settings/developer/
2. Set the redirect URL to `urn:ietf:wg:oauth:2.0:oob`
3. Add to configuration:
   ```
   SIMKL_CLIENT_ID=your_client_id_here
   ```

### 📂 Overriding Cache Directory

To store application data in a custom location:

```
SIMKL_APP_DATA_DIR=/path/to/custom/directory
```

## 🧪 Configuration for Development

When developing or testing:

```
# Enable debug logging
SIMKL_LOG_LEVEL=DEBUG

# Faster polling for testing
SIMKL_POLL_INTERVAL=2

# Testing mode (prevents actual API calls)
SIMKL_TESTING_MODE=True
```

## 🔄 Manual Configuration Reset

To completely reset the configuration:

1. Close all instances of the application
2. Delete the application data directory
3. Reinitialize with `media-player-scrobbler-for-simkl init`
