from __future__ import annotations

from typing import Any

import requests


class TrackerApiClient:
    def __init__(self, base_url: str, auth_token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if auth_token:
            self.session.headers.update({"Authorization": f"Bearer {auth_token}"})

    def post(self, endpoint: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        try:
            response = self.session.post(f"{self.base_url}/{endpoint.lstrip('/')}", json=payload, timeout=15)
            response.raise_for_status()
            return True, response.json() if response.content else {}
        except requests.RequestException:
            return False, None
