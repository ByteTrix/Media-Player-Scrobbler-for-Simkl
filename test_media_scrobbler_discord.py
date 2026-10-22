import pytest
from unittest.mock import MagicMock, patch
from simkl_mps.media_scrobbler import MediaScrobbler
from simkl_mps.utils.constants import PLAYING, PAUSED, STOPPED


@pytest.fixture(autouse=True)
def mock_network_offline(monkeypatch):
    monkeypatch.setattr("simkl_mps.media_scrobbler.is_internet_connected", lambda: False)


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_syncs_discord_on_playing(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Succession"
    scrobbler.media_type = "show"
    scrobbler.season = 2
    scrobbler.episode = 2
    scrobbler.display_season = 2
    scrobbler.display_episode = 2
    scrobbler.simkl_id = 12345
    scrobbler.state = PLAYING
    scrobbler.current_position_seconds = 100
    scrobbler.total_duration_seconds = 3600

    scrobbler._sync_discord_presence()
    assert mock_rpc.update_presence.called
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["title"] == "Succession"
    assert kwargs["media_type"] == "show"
    assert kwargs["season"] == 2
    assert kwargs["episode"] == 2
    assert kwargs["is_paused"] is False


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_syncs_discord_on_paused(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Inception"
    scrobbler.media_type = "movie"
    scrobbler.simkl_id = 472214
    scrobbler.state = PAUSED
    scrobbler.current_position_seconds = 500
    scrobbler.total_duration_seconds = 7200

    scrobbler._sync_discord_presence()
    assert mock_rpc.update_presence.called
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["title"] == "Inception"
    assert kwargs["is_paused"] is True


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_clears_discord_on_stop(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.state = STOPPED
    scrobbler._sync_discord_presence()
    assert mock_rpc.clear_presence.called


@patch("simkl_mps.media_scrobbler.get_setting")
@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_disabled_setting_clears_discord(mock_rpc_cls, mock_get_setting, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    def fake_get_setting(key, default=None):
        if key == "enable_discord_rpc":
            return False
        return default

    mock_get_setting.side_effect = fake_get_setting

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Inception"
    scrobbler.state = PLAYING
    scrobbler._sync_discord_presence()
    assert mock_rpc.clear_presence.called
    assert not mock_rpc.update_presence.called


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_resolves_poster_url(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Inception"
    scrobbler.media_type = "movie"
    scrobbler.simkl_id = 472214
    scrobbler.state = PLAYING
    scrobbler.current_filepath = "C:/Videos/Inception.mkv"

    # Add cache entry with poster key
    scrobbler.media_cache.cache["Inception"] = {
        "title": "Inception",
        "poster": "47/472214posterkey"
    }

    scrobbler._sync_discord_presence()
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["poster_url"] == "https://simkl.net/posters/47/472214posterkey_m.jpg"


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_resolves_poster_via_simkl_id_lookup(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Succession"
    scrobbler.media_type = "show"
    scrobbler.simkl_id = 739608
    scrobbler.state = PLAYING
    scrobbler.current_filepath = "V:/My Pack/Succession.S02E03.Hunting.1080p.mkv"

    # Cache is keyed by lowercase filename (as Simkl search does)
    scrobbler.media_cache.set("succession.s02e03.hunting.1080p.mkv", {
        "simkl_id": 739608,
        "movie_name": "Succession",
        "poster_url": "13/13667609b5f759c72f",
        "year": 2018
    })

    scrobbler._sync_discord_presence()
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["poster_url"] == "https://simkl.net/posters/13/13667609b5f759c72f_m.jpg"
    assert kwargs["year"] == 2018


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_stop_tracking_clears_discord_even_without_currently_tracking(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.currently_tracking = None
    scrobbler._discord_reported_state = "playing"

    scrobbler.stop_tracking()
    assert mock_rpc.clear_presence.called
    assert scrobbler._discord_reported_state == "cleared"


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_stop_tracking_clears_discord_when_tracking(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.currently_tracking = "Succession"
    scrobbler.movie_name = "Succession"
    scrobbler.state = PLAYING
    scrobbler._discord_reported_state = "playing"

    scrobbler.stop_tracking()
    assert mock_rpc.clear_presence.called
    assert scrobbler._discord_reported_state == "cleared"


def test_monitor_stop_clears_discord_presence(tmp_path):
    from simkl_mps.monitor import Monitor
    monitor = Monitor(app_data_dir=tmp_path)
    mock_rpc = MagicMock()
    monitor.scrobbler.discord_rpc = mock_rpc
    monitor.scrobbler._discord_reported_state = "playing"

    monitor.stop()
    assert mock_rpc.clear_presence.called
    assert monitor.scrobbler._discord_reported_state == "cleared"


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_syncs_discord_with_episode_title(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Succession"
    scrobbler.media_type = "show"
    scrobbler.season = 2
    scrobbler.episode = 4
    scrobbler.display_season = 2
    scrobbler.display_episode = 4
    scrobbler.episode_title = "Safe Room"
    scrobbler.simkl_id = 739608
    scrobbler.state = PLAYING
    scrobbler.current_position_seconds = 200
    scrobbler.total_duration_seconds = 3600

    scrobbler._sync_discord_presence()
    assert mock_rpc.update_presence.called
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["title"] == "Succession"
    assert kwargs["season"] == 2
    assert kwargs["episode"] == 4
    assert kwargs["episode_title"] == "Safe Room"


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_media_scrobbler_resolves_episode_title_from_media_cache(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.movie_name = "Succession"
    scrobbler.media_type = "show"
    scrobbler.simkl_id = 739608
    scrobbler.episode_title = None
    scrobbler.state = PLAYING
    scrobbler.current_filepath = "V:/TV/Succession.S02E04.Safe.Room.mkv"

    scrobbler.media_cache.set("succession.s02e04.safe.room.mkv", {
        "simkl_id": 739608,
        "movie_name": "Succession",
        "episode_title": "Safe Room",
        "year": 2018
    })

    scrobbler._sync_discord_presence()
    assert mock_rpc.update_presence.called
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["episode_title"] == "Safe Room"
    assert scrobbler.episode_title == "Safe Room"


def test_stop_tracking_resets_episode_title(tmp_path):
    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    scrobbler.episode_title = "Safe Room"
    scrobbler.stop_tracking()
    assert scrobbler.episode_title is None


def test_start_new_media_item_extracts_episode_title_from_guessit(tmp_path, monkeypatch):
    monkeypatch.setattr("simkl_mps.media_scrobbler.is_internet_connected", lambda: False)
    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    guessit_info = {
        "title": "Succession",
        "season": 2,
        "episode": 4,
        "episode_title": "Safe Room"
    }
    scrobbler._start_new_media_item(
        raw_title="Succession.S02E04.Safe.Room.1080p.mkv",
        filepath="V:/TV/Succession.S02E04.Safe.Room.1080p.mkv",
        initial_media_type_guess="show",
        guessit_info=guessit_info
    )
    assert scrobbler.episode_title == "Safe Room"
    assert scrobbler._local_episode_title == "Safe Room"


def test_start_new_media_item_ignores_generic_guessit_title(tmp_path):
    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    guessit_info = {
        "title": "Small Prophets",
        "season": 1,
        "episode": 1,
        "episode_title": "Episode 1"
    }
    scrobbler._start_new_media_item(
        raw_title="Small.Prophets.S01E01.Episode.1.1080p.mkv",
        filepath="V:/TV/Small.Prophets.S01E01.Episode.1.1080p.mkv",
        initial_media_type_guess="show",
        guessit_info=guessit_info
    )
    assert scrobbler.episode_title is None
    assert scrobbler._local_episode_title is None


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_simkl_generic_title_falls_back_to_local_filename(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    guessit_info = {
        "title": "Small Prophets",
        "season": 1,
        "episode": 1,
        "episode_title": "The Secret"
    }
    scrobbler._start_new_media_item(
        raw_title="Small.Prophets.S01E01.The.Secret.1080p.mkv",
        filepath="V:/TV/Small.Prophets.S01E01.The.Secret.1080p.mkv",
        initial_media_type_guess="show",
        guessit_info=guessit_info
    )

    # Simkl search returns generic "Episode 1"
    search_res = {
        "show": {
            "title": "Small Prophets",
            "year": 2026,
            "type": "show",
            "ids": {"simkl": 99999}
        },
        "episode": {
            "season": 1,
            "episode": 1,
            "title": "Episode 1"
        }
    }
    scrobbler._process_simkl_search_result(
        search_res,
        "Small.Prophets.S01E01.The.Secret.1080p.mkv",
        "small.prophets.s01e01.the.secret.1080p.mkv",
        "simkl_search"
    )
    # Must fallback to local filename title "The Secret"
    assert scrobbler.episode_title == "The Secret"

    scrobbler._sync_discord_presence()
    assert mock_rpc.update_presence.called
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["episode_title"] == "The Secret"


@patch("simkl_mps.media_scrobbler.DiscordRPCManager")
def test_simkl_generic_title_omitted_when_no_local_title(mock_rpc_cls, tmp_path):
    mock_rpc = MagicMock()
    mock_rpc_cls.return_value = mock_rpc

    scrobbler = MediaScrobbler(app_data_dir=tmp_path)
    # Filename has NO episode title
    guessit_info = {
        "title": "Small Prophets",
        "season": 1,
        "episode": 1
    }
    scrobbler._start_new_media_item(
        raw_title="Small.Prophets.S01E01.1080p.mkv",
        filepath="V:/TV/Small.Prophets.S01E01.1080p.mkv",
        initial_media_type_guess="show",
        guessit_info=guessit_info
    )

    # Simkl search returns generic "Episode 1"
    search_res = {
        "show": {
            "title": "Small Prophets",
            "year": 2026,
            "type": "show",
            "ids": {"simkl": 99999}
        },
        "episode": {
            "season": 1,
            "episode": 1,
            "title": "Episode 1"
        }
    }
    scrobbler._process_simkl_search_result(
        search_res,
        "Small.Prophets.S01E01.1080p.mkv",
        "small.prophets.s01e01.1080p.mkv",
        "simkl_search"
    )
    # Must be None (no episode title)
    assert scrobbler.episode_title is None

    scrobbler._sync_discord_presence()
    assert mock_rpc.update_presence.called
    kwargs = mock_rpc.update_presence.call_args[1]
    assert kwargs["episode_title"] is None






