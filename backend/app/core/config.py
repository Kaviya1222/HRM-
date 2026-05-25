from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "HRM API"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-this-secret-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    database_url: str = "mysql+pymysql://root:root@localhost:3306/hrm_db?charset=utf8mb4"
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080"
    auto_bootstrap: bool = True
    seed_demo_data: bool = True
    tracker_shared_token: str = "tracker-dev-token"
    initial_super_admin_email: EmailStr = "superadmin@hrm.local"
    initial_super_admin_password: str = "SuperAdmin@123"

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        raw_value = self.cors_origins.strip()
        if not raw_value:
            return []
        if raw_value.startswith("["):
            return [item.strip() for item in json.loads(raw_value) if str(item).strip()]
        return [item.strip() for item in raw_value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
