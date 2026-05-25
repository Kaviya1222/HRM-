from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.client import TrackerApiClient
from utils.system import get_device_uuid, get_hostname, get_os_version, get_username


class DeviceService:
    def __init__(self, api_client: TrackerApiClient, state_file: Path, employee_email: str = "") -> None:
        self.api_client = api_client
        self.state_file = state_file
        self.employee_email = employee_email
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {}
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def save_state(self, payload: dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def build_registration_payload(self) -> dict[str, Any]:
        return {
            "employee_email": self.employee_email,
            "device_uuid": get_device_uuid(),
            "device_name": get_hostname(),
            "os_version": get_os_version(),
            "username": get_username(),
        }

    def register_device(self) -> dict[str, Any]:
        payload = self.build_registration_payload()
        success, response = self.api_client.post("/tracker/register-device", payload)
        if success and response is not None:
            state = {**payload, **response}
            self.save_state(state)
            return state
        return self.load_state() or payload
