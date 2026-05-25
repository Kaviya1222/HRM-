from __future__ import annotations

import signal
import time

from api.client import TrackerApiClient
from config import settings
from services.device_service import DeviceService
from services.heartbeat_service import HeartbeatService
from services.idle_service import IdleService
from services.session_service import SessionService
from utils.cache import LocalEventCache


class TrackerApplication:
    def __init__(self) -> None:
        self.running = True
        self.cache = LocalEventCache(settings.cache_db_path)
        self.api_client = TrackerApiClient(settings.tracker_api_base_url, settings.tracker_auth_token)
        self.device_service = DeviceService(
            self.api_client,
            settings.device_state_path,
            settings.tracker_employee_email,
        )
        self.device_state = self.device_service.register_device()
        self.session_service = SessionService(self.api_client, self.cache, self.device_state)
        self.idle_service = IdleService(
            self.api_client,
            self.cache,
            settings.tracker_idle_threshold_minutes,
            self.device_state,
        )
        self.heartbeat_service = HeartbeatService(
            self.api_client,
            self.cache,
            self.device_state,
            settings.tracker_idle_threshold_minutes,
        )

    def stop(self, *_args) -> None:
        self.running = False

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        self.session_service.start_session()

        while self.running:
            self.idle_service.poll(self.session_service.current_session_id)
            self.heartbeat_service.send(self.session_service.current_session_id)
            self.heartbeat_service.flush_cached_events()
            time.sleep(settings.tracker_heartbeat_interval_seconds)

        self.session_service.end_session()


if __name__ == "__main__":
    TrackerApplication().run()
