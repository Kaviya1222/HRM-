from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AttendanceStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AttendanceRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attendance_rules"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    late_mark_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    half_day_min_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=240)
    full_day_min_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())


class AttendanceLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        Index("ix_attendance_logs_employee_date", "employee_id", "attendance_date"),
        Index("ix_attendance_logs_user_date", "user_id", "attendance_date"),
    )

    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    work_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    work_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=AttendanceStatus.ABSENT.value, server_default=AttendanceStatus.ABSENT.value)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="web", server_default="web")
    corrected_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttendanceDailySummary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attendance_daily_summary"
    __table_args__ = (Index("ix_attendance_summary_employee_date", "employee_id", "summary_date"),)

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    work_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    work_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    idle_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    leave_request_id: Mapped[str | None] = mapped_column(ForeignKey("leave_requests.id"), nullable=True)


class AttendanceCorrection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attendance_corrections"

    attendance_log_id: Mapped[str] = mapped_column(ForeignKey("attendance_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    old_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")


class AttendanceAuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attendance_audit_logs"

    attendance_log_id: Mapped[str] = mapped_column(ForeignKey("attendance_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
