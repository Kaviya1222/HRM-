from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_runtime_base_dir()


class TrackerSettings(BaseSettings):
    tracker_api_base_url: str = "https://localhost:8000/api/v1"
    tracker_auth_token: str = ""
    tracker_employee_email: str = ""
    tracker_heartbeat_interval_seconds: int = 60
    tracker_idle_threshold_minutes: int = 5
    tracker_cache_db: str = "local_cache/tracker_cache.sqlite3"
    tracker_device_state_file: str = "local_cache/device_state.json"

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cache_db_path(self) -> Path:
        return (BASE_DIR / self.tracker_cache_db).resolve()

    @property
    def device_state_path(self) -> Path:
        return (BASE_DIR / self.tracker_device_state_file).resolve()


@lru_cache(maxsize=1)
def get_settings() -> TrackerSettings:
    return TrackerSettings()


settings = get_settings()
