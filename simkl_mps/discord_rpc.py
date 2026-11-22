"""
Discord Rich Presence module for Media Player Scrobbler for Simkl.
Synchronizes active media playback to user's Discord profile via local IPC.
"""

import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

GENERIC_EPISODE_TITLE_REGEX = re.compile(
    r"^(?:(?:season\s*\d+[\s,]+)?(?:episode|ep\.?|e)\s*#?\s*\d+\.?|s\d+\s*e\d+|\d+|tba|tbd|n/a|unknown)$",
    re.IGNORECASE
)


def is_generic_episode_title(title: Optional[str]) -> bool:
    """
    Checks whether an episode title is a generic placeholder (e.g. 'Episode 1', 'Ep 01', 'E1', '1').
    Returns True if title is empty, None, or matches a generic pattern.
    """
    if not title:
        return True
    cleaned = str(title).strip()
    if not cleaned:
        return True
    return bool(GENERIC_EPISODE_TITLE_REGEX.match(cleaned))


try:
    from pypresence import Presence, ActivityType
    PYPRESENCE_AVAILABLE = True
except ImportError:
    Presence = None
    ActivityType = None
    PYPRESENCE_AVAILABLE = False
    logger.debug("pypresence is not installed. Discord Rich Presence will be disabled.")


DEFAULT_DISCORD_CLIENT_ID = "1556713709462880316"
SIMKL_ICON_URL = "https://raw.githubusercontent.com/ByteTrix/Media-Player-Scrobbler-for-Simkl/master/simkl_mps/assets/simkl-mps-128.png"


class DiscordRPCManager:
    """
    Manages connection and activity updates to Discord Rich Presence via IPC.
    """

    def __init__(self, client_id: Optional[str] = None):
        self.client_id = str(client_id or DEFAULT_DISCORD_CLIENT_ID)
        self._presence: Optional[Any] = None
        self.is_connected: bool = False
        self._last_update_time: float = 0.0
        self._last_connect_attempt: float = 0.0
        self._last_failed_connect_attempt: float = 0.0
        self._connect_cooldown_seconds: float = 30.0
        self._update_debounce_seconds: float = 1.5
        self._last_payload: Optional[Dict[str, Any]] = None

    def connect(self) -> bool:
        """
        Attempts to connect to the local Discord client via IPC.
        Fails silently if Discord is not running.
        """
        if not PYPRESENCE_AVAILABLE:
            return False

        now = time.time()
        self._last_connect_attempt = now
        if now - self._last_failed_connect_attempt < self._connect_cooldown_seconds:
            return False

        try:
            if not self._presence:
                self._presence = Presence(self.client_id)
            self._presence.connect()
            self.is_connected = True
            self._last_failed_connect_attempt = 0.0
            logger.info("Connected to Discord Rich Presence IPC.")
            return True
        except Exception as e:
            logger.debug("Could not connect to Discord RPC (is Discord running?): %s", e)
            self.is_connected = False
            self._presence = None
            self._last_failed_connect_attempt = now
            return False

    def _build_payload(
        self,
        title: str,
        year: Optional[int] = None,
        media_type: str = "movie",
        season: Optional[int] = None,
        episode: Optional[int] = None,
        episode_title: Optional[str] = None,
        current_position: Optional[float] = None,
        total_duration: Optional[float] = None,
        poster_url: Optional[str] = None,
        simkl_id: Optional[Any] = None,
        is_paused: bool = False
    ) -> Dict[str, Any]:
        """
        Builds and formats the payload for Discord Presence.update().
        """
        # 1. Details (Title + Year)
        details = f"{title} ({year})" if year else title
        if len(details) > 128:
            details = details[:125] + "..."

        # 2. State (Season/Episode / Watching / Paused)
        if is_generic_episode_title(episode_title):
            episode_title = None

        if media_type in ("show", "anime"):
            if season is not None and episode is not None:
                ep_code = f"S{season:02d}E{episode:02d}"
                if is_paused:
                    state = f"Paused · {ep_code}"
                elif episode_title:
                    state = f"{ep_code} · {episode_title}"
                else:
                    state = ep_code
            elif episode is not None:
                ep_code = f"EP {episode}"
                if is_paused:
                    state = f"Paused · {ep_code}"
                elif episode_title:
                    state = f"{ep_code} · {episode_title}"
                else:
                    state = ep_code
            else:
                state = "Paused" if is_paused else "Watching"
        else:
            state = "Paused" if is_paused else "Watching"

        if len(state) > 128:
            state = state[:125] + "..."

        payload: Dict[str, Any] = {
            "details": details,
            "state": state
        }

        # 3. Timestamps (Playback Progress Bar: Start & End)
        if not is_paused and total_duration and total_duration > 0 and current_position is not None:
            start_timestamp = int(time.time() - current_position)
            end_timestamp = int(start_timestamp + total_duration)
            payload["timestamps"] = {
                "start": start_timestamp,
                "end": end_timestamp
            }
        else:
            payload["timestamps"] = None

        # 4. Large Image & Large Text
        if poster_url:
            norm_poster = str(poster_url).strip()
            if not norm_poster.startswith("http://") and not norm_poster.startswith("https://"):
                norm_poster = f"https://simkl.net/posters/{norm_poster}_m.jpg"
            payload["large_image"] = norm_poster
            payload["large_text"] = title[:128]
        else:
            payload["large_image"] = SIMKL_ICON_URL
            payload["large_text"] = "SIMKL"

        # 5. Small Image (omitted for clean Harbor-style poster layout)
        payload["small_image"] = None
        payload["small_text"] = None

        # 6. Buttons (Single 'View on Simkl' button)
        if simkl_id and not str(simkl_id).startswith("temp_"):
            if media_type == "anime":
                type_path = "anime"
            elif media_type == "show":
                type_path = "tv"
            else:
                type_path = "movies"
            simkl_url = f"https://simkl.com/{type_path}/{simkl_id}"
            payload["buttons"] = [
                {"label": "View on Simkl", "url": simkl_url}
            ]

        return payload

    def update_presence(
        self,
        title: str,
        year: Optional[int] = None,
        media_type: str = "movie",
        season: Optional[int] = None,
        episode: Optional[int] = None,
        episode_title: Optional[str] = None,
        current_position: Optional[float] = None,
        total_duration: Optional[float] = None,
        poster_url: Optional[str] = None,
        simkl_id: Optional[Any] = None,
        is_paused: bool = False,
        force: bool = False
    ) -> bool:
        """
        Updates Discord Rich Presence with current media playback state.
        """
        if not self.is_connected:
            if not self.connect():
                return False

        now = time.time()
        if not force and now - self._last_update_time < self._update_debounce_seconds:
            return False

        payload = self._build_payload(
            title=title,
            year=year,
            media_type=media_type,
            season=season,
            episode=episode,
            episode_title=episode_title,
            current_position=current_position,
            total_duration=total_duration,
            poster_url=poster_url,
            simkl_id=simkl_id,
            is_paused=is_paused
        )

        try:
            update_kwargs: Dict[str, Any] = {
                "details": payload["details"],
                "state": payload["state"],
            }
            if PYPRESENCE_AVAILABLE and ActivityType:
                update_kwargs["activity_type"] = ActivityType.WATCHING

            if payload.get("timestamps"):
                update_kwargs["start"] = payload["timestamps"]["start"]
                update_kwargs["end"] = payload["timestamps"]["end"]
            if payload.get("large_image"):
                update_kwargs["large_image"] = payload["large_image"]
                update_kwargs["large_text"] = payload.get("large_text")
            if payload.get("small_image"):
                update_kwargs["small_image"] = payload["small_image"]
                update_kwargs["small_text"] = payload.get("small_text")
            if payload.get("buttons"):
                update_kwargs["buttons"] = payload["buttons"]

            self._presence.update(**update_kwargs)
            self._last_update_time = now
            self._last_payload = payload
            logger.debug("Updated Discord Rich Presence: %s - %s", payload["details"], payload["state"])
            return True
        except Exception as e:
            logger.debug("Failed to update Discord RPC (pipe closed or disconnected): %s", e)
            self.is_connected = False
            self._presence = None
            return False

    def clear_presence(self) -> bool:
        """
        Clears the Discord Rich Presence activity and disconnects the IPC pipe.
        Closing the connection ensures Discord unconditionally drops presence
        from the user profile and prevents lingering presence state.
        """
        self._last_payload = None
        if not self._presence:
            self.is_connected = False
            return True

        cleared = False
        try:
            self._presence.clear()
            cleared = True
        except Exception as e:
            logger.warning("Failed to clear Discord RPC activity: %s", e)

        try:
            self._presence.close()
        except Exception as e:
            logger.debug("Failed to close Discord RPC connection: %s", e)

        self._presence = None
        self.is_connected = False
        self._last_failed_connect_attempt = 0.0

        if cleared:
            logger.info("Cleared Discord Rich Presence.")
        return True

    def close(self) -> None:
        """
        Gracefully disconnects and closes the Discord RPC client.
        """
        self.clear_presence()
