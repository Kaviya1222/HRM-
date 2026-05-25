from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PayrollRunStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SalaryStructure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "salary_structures"

    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True)
    grade_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    allowances: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deductions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class PayrollRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("period_month", "period_year", name="uq_payroll_runs_period"),)

    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=PayrollRunStatus.DRAFT.value,
        server_default=PayrollRunStatus.DRAFT.value,
    )
    initiated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Payslip(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payslip_run_employee"),
        Index("ix_payslips_employee_period", "employee_id", "payroll_run_id"),
    )

    payroll_run_id: Mapped[str] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    gross_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    deduction_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    net_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    paid_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    attendance_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payroll_transactions"
    __table_args__ = (
        Index("ix_payroll_transactions_type_date", "transaction_type", "transaction_date"),
        Index("ix_payroll_transactions_employee_date", "employee_id", "transaction_date"),
    )

    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
