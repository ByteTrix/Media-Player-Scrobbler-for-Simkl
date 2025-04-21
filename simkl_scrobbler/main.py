import time
import sys
import signal
import threading
import pathlib
from .monitor import Monitor
from .simkl_api import search_movie, mark_as_watched, get_movie_details, is_internet_connected
from .credentials import get_credentials
import logging

APP_NAME = "simkl-scrobbler"
USER_SUBDIR = "kavinthangavel"
APP_DATA_DIR = pathlib.Path.home() / USER_SUBDIR / APP_NAME
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

log_file_path = APP_DATA_DIR / "simkl_scrobbler.log"

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_handler.setFormatter(logging.Formatter('%(levelname)s - %(name)s - %(message)s'))

file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, file_handler]
)

logger = logging.getLogger(__name__)
logger.info(f"Log file: {log_file_path}")
logger.info(f"App data dir: {APP_DATA_DIR}")


def load_configuration():
    logger.info("Loading credentials...")
    creds = get_credentials()
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    access_token = creds.get("access_token")

    if not client_id:
        logger.error("Client ID not found. Build might be corrupted.")
        print("Critical Error: Client ID missing. Check build/reinstall.")
        sys.exit(1)
    if not client_secret:
        logger.error("Client Secret not found. Build might be corrupted.")
        print("Critical Error: Client Secret missing. Check build/reinstall.")
        sys.exit(1)
    if not access_token:
        logger.error("Access Token not found.")
        print("Error: Access Token missing. Run 'simkl-scrobbler init'.")
        sys.exit(1)

    logger.info("Credentials loaded successfully.")
    return client_id, access_token

class SimklScrobbler:
    def __init__(self):
        self.running = False
        self.client_id = None
        self.access_token = None
        self.monitor = Monitor(app_data_dir=APP_DATA_DIR)

    def initialize(self):
        logger.info("Initializing Simkl Scrobbler...")
        self.client_id, self.access_token = load_configuration()

        if not self.client_id or not self.access_token:
            # load_configuration should exit if creds are missing, but double-check
            logger.error("Exiting due to missing credentials after load attempt.")
            return False

        self.monitor.set_credentials(self.client_id, self.access_token)

        try:
            backlog_count = self.monitor.scrobbler.process_backlog()
            if backlog_count > 0:
                logger.info(f"Processed {backlog_count} backlog items.")
        except Exception as e:
             logger.error(f"Error processing backlog during init: {e}", exc_info=True)

        return True

    def start(self):
        if not self.running:
            self.running = True
            logger.info("Starting Simkl Scrobbler monitor...")

            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)

            self.monitor.set_search_callback(self._search_and_cache_movie)

            if not self.monitor.start():
                 logger.error("Failed to start the monitor.")
                 self.running = False
                 return False

            logger.info("Monitor thread started.")
            return True
        else:
            logger.warning("Scrobbler already running.")
            return False

    def stop(self):
        if self.running:
            logger.info("Stopping Monitor...")
            self.running = False
            self.monitor.stop()
            logger.info("Monitor stopped.")
        else:
             logger.info("Scrobbler was not running.")

    def _signal_handler(self, sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        self.stop()

    def _search_and_cache_movie(self, title):
        if not title:
            logger.warning("Search callback: no title.")
            return
        if not self.client_id or not self.access_token:
             logger.warning(f"Search callback: no credentials for '{title}'.")
             return

        logger.info(f"Search callback triggered for: {title}")

        if not is_internet_connected():
            logger.warning(f"Search callback: no internet for '{title}'.")
            return

        try:
            movie = search_movie(title, self.client_id, self.access_token)
            if not movie:
                logger.warning(f"Search callback: no match for '{title}'.")
                return

            simkl_id = None
            movie_name = title
            runtime = None

            ids_dict = movie.get('ids') or movie.get('movie', {}).get('ids')
            if ids_dict:
                simkl_id = ids_dict.get('simkl') or ids_dict.get('simkl_id')

            if simkl_id:
                 movie_name = movie.get('title') or movie.get('movie', {}).get('title', title)
                 logger.info(f"Search callback: found ID {simkl_id} for '{movie_name}'")
                 try:
                     details = get_movie_details(simkl_id, self.client_id, self.access_token)
                     if details and 'runtime' in details:
                         runtime = details['runtime']
                         logger.info(f"Search callback: retrieved runtime {runtime} min.")
                 except Exception as detail_error:
                     logger.error(f"Search callback: error getting details for ID {simkl_id}: {detail_error}")

                 self.monitor.cache_movie_info(title, simkl_id, movie_name, runtime)
                 logger.info(f"Search callback: cached info for '{title}' -> '{movie_name}' (ID: {simkl_id}, Runtime: {runtime})")
            else:
                logger.warning(f"Search callback: no Simkl ID found for '{title}'.")
        except Exception as e:
            logger.error(f"Search callback error for '{title}': {e}", exc_info=True)

def main():
    logger.info("Starting Simkl Scrobbler application")
    scrobbler_instance = SimklScrobbler()
    if scrobbler_instance.initialize():
        if scrobbler_instance.start():
            while scrobbler_instance.running:
                try:
                    time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("KeyboardInterrupt in main, stopping...")
                    scrobbler_instance.stop()
                    break
            logger.info("Main thread exiting.")
        else:
             logger.error("Failed to start scrobbler monitor.")
             sys.exit(1)
    else:
        logger.error("Failed to initialize scrobbler.")
        sys.exit(1)

if __name__ == "__main__":
    main()