from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.client import TrackerApiClient
from utils.cache import LocalEventCache
from utils.system import get_hostname, get_idle_seconds


class HeartbeatService:
    def __init__(
        self,
        api_client: TrackerApiClient,
        cache: LocalEventCache,
        device_state: dict[str, Any],
        idle_threshold_minutes: int,
    ) -> None:
        self.api_client = api_client
        self.cache = cache
        self.device_state = device_state
        self.idle_threshold_seconds = idle_threshold_minutes * 60

    def send(self, tracker_session_id: str | None) -> None:
        payload = {
            "device_uuid": self.device_state.get("device_uuid"),
            "tracker_session_id": tracker_session_id,
            "heartbeat_at": datetime.now(UTC).isoformat(),
            "is_idle": get_idle_seconds() >= self.idle_threshold_seconds,
            "device_name": get_hostname(),
        }
        success, _ = self.api_client.post("/tracker/client-heartbeat", payload)
        if not success:
            self.cache.enqueue("heartbeat", payload)

    def flush_cached_events(self) -> None:
        for event in self.cache.fetch_batch():
            success, _ = self.api_client.post(f"/tracker/offline-sync/{event['event_type']}", event["payload"])
            if success:
                self.cache.delete(event["id"])
