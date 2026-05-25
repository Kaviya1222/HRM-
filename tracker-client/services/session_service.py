from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.client import TrackerApiClient
from utils.cache import LocalEventCache


class SessionService:
    def __init__(self, api_client: TrackerApiClient, cache: LocalEventCache, device_state: dict[str, Any]) -> None:
        self.api_client = api_client
        self.cache = cache
        self.device_state = device_state
        self.current_session_id: str | None = None

    def start_session(self) -> dict[str, Any]:
        payload = {
            "device_uuid": self.device_state.get("device_uuid"),
            "session_start_at": datetime.now(UTC).isoformat(),
        }
        success, response = self.api_client.post("/tracker/start-session", payload)
        if success and response is not None:
            self.current_session_id = response.get("tracker_session_id")
            return response

        self.cache.enqueue("start_session", payload)
        return payload

    def end_session(self) -> None:
        payload = {
            "device_uuid": self.device_state.get("device_uuid"),
            "tracker_session_id": self.current_session_id,
            "session_end_at": datetime.now(UTC).isoformat(),
        }
        success, _ = self.api_client.post("/tracker/end-session", payload)
        if not success:
            self.cache.enqueue("end_session", payload)
