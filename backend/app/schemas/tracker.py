from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class RegisterDeviceRequest(BaseModel):
    employee_email: EmailStr
    device_uuid: str
    device_name: str
    os_version: str | None = None
    username: str | None = None


class TrackerSessionStartRequest(BaseModel):
    device_uuid: str
    session_start_at: datetime


class TrackerSessionEndRequest(BaseModel):
    device_uuid: str
    tracker_session_id: str | None = None
    session_end_at: datetime


class TrackerIdleStartRequest(BaseModel):
    device_uuid: str
    tracker_session_id: str | None = None
    idle_start_at: datetime


class TrackerIdleEndRequest(BaseModel):
    device_uuid: str
    tracker_session_id: str | None = None
    idle_start_at: datetime | None = None
    idle_end_at: datetime


class TrackerHeartbeatRequest(BaseModel):
    device_uuid: str
    tracker_session_id: str | None = None
    heartbeat_at: datetime
    is_idle: bool = False
    device_name: str | None = None


class TrackerStatusUpdateRequest(BaseModel):
    status: str
    last_active_time: datetime | None = None


class WebTrackerCheckInRequest(BaseModel):
    check_in_at: datetime | None = None
    device_info: dict[str, object] | None = None


class WebTrackerHeartbeatRequest(BaseModel):
    heartbeat_at: datetime | None = None
    is_idle: bool = False
    device_info: dict[str, object] | None = None


class WebTrackerLogoutRequest(BaseModel):
    logout_time: datetime | None = None
    reason: str | None = None
