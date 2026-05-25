from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DeviceStatus, TrackerSessionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Device(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    device_uuid: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    os_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    auth_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=DeviceStatus.ACTIVE.value, server_default=DeviceStatus.ACTIVE.value)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrackerSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tracker_sessions"
    __table_args__ = (
        Index("ix_tracker_sessions_employee_status", "employee_id", "status"),
        Index("ix_tracker_sessions_device_started", "device_id", "started_at"),
    )

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    login_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    logout_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_token: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    device_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_idle_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=TrackerSessionStatus.ACTIVE.value,
        server_default=TrackerSessionStatus.ACTIVE.value,
    )
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    sync_state: Mapped[str] = mapped_column(String(30), nullable=False, default="synced", server_default="synced")


class TrackerIdleLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tracker_idle_logs"

    tracker_session_id: Mapped[str] = mapped_column(ForeignKey("tracker_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    idle_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idle_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class TrackerHeartbeat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tracker_heartbeats"
    __table_args__ = (
        Index("ix_tracker_heartbeats_device_time", "device_id", "heartbeat_at"),
        UniqueConstraint("device_id", "tracker_session_id", "heartbeat_at", name="uq_tracker_heartbeat_event"),
    )

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    tracker_session_id: Mapped[str | None] = mapped_column(ForeignKey("tracker_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_idle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
