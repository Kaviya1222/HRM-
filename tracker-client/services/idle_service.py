from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.client import TrackerApiClient
from utils.cache import LocalEventCache
from utils.system import get_idle_seconds


class IdleService:
    def __init__(self, api_client: TrackerApiClient, cache: LocalEventCache, threshold_minutes: int, device_state: dict[str, Any]) -> None:
        self.api_client = api_client
        self.cache = cache
        self.threshold_seconds = threshold_minutes * 60
        self.device_state = device_state
        self.is_idle = False
        self.idle_started_at: str | None = None

    def poll(self, tracker_session_id: str | None) -> None:
        idle_seconds = get_idle_seconds()

        if idle_seconds >= self.threshold_seconds and not self.is_idle:
            self.is_idle = True
            self.idle_started_at = datetime.now(UTC).isoformat()
            payload = {
                "device_uuid": self.device_state.get("device_uuid"),
                "tracker_session_id": tracker_session_id,
                "idle_start_at": self.idle_started_at,
            }
            success, _ = self.api_client.post("/tracker/idle-start", payload)
            if not success:
                self.cache.enqueue("idle_start", payload)

        elif idle_seconds < self.threshold_seconds and self.is_idle:
            payload = {
                "device_uuid": self.device_state.get("device_uuid"),
                "tracker_session_id": tracker_session_id,
                "idle_start_at": self.idle_started_at,
                "idle_end_at": datetime.now(UTC).isoformat(),
            }
            success, _ = self.api_client.post("/tracker/idle-end", payload)
            if not success:
                self.cache.enqueue("idle_end", payload)
            self.is_idle = False
            self.idle_started_at = None
