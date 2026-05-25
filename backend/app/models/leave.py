from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import LeaveRequestStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class LeaveType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leave_types"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    annual_allowance: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class LeaveRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"
    __table_args__ = (Index("ix_leave_requests_employee_dates", "employee_id", "start_date", "end_date"),)

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[str] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=LeaveRequestStatus.PENDING.value,
        server_default=LeaveRequestStatus.PENDING.value,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class LeaveBalance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leave_balances"
    __table_args__ = (UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balances_employee_type_year"),)

    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type_id: Mapped[str] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    used_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    remaining_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)


class LeaveApproval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leave_approvals"

    leave_request_id: Mapped[str] = mapped_column(ForeignKey("leave_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    approver_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
