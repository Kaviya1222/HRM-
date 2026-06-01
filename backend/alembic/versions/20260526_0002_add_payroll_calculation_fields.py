"""add payroll calculation fields

Revision ID: 20260526_0002
Revises: 20260525_0001
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260526_0002"
down_revision = "20260525_0001"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector: sa.Inspector, column_name: str, column: sa.Column) -> None:
    existing_columns = {item["name"] for item in inspector.get_columns("payslips")}
    if column_name not in existing_columns:
        op.add_column("payslips", column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "payslips" not in table_names:
        return

    _add_column_if_missing(inspector, "monthly_salary", sa.Column("monthly_salary", sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "total_days", sa.Column("total_days", sa.Integer(), nullable=False, server_default="30"))
    _add_column_if_missing(inspector, "worked_days", sa.Column("worked_days", sa.Numeric(8, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "per_day_salary", sa.Column("per_day_salary", sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "basic", sa.Column("basic", sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "hra", sa.Column("hra", sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "special_allowance", sa.Column("special_allowance", sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "transport", sa.Column("transport", sa.Numeric(12, 2), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "medical", sa.Column("medical", sa.Numeric(12, 2), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "payslips" not in set(inspector.get_table_names()):
        return

    existing_columns = {item["name"] for item in inspector.get_columns("payslips")}
    for column_name in ["medical", "transport", "special_allowance", "hra", "basic", "per_day_salary", "worked_days", "total_days", "monthly_salary"]:
        if column_name in existing_columns:
            op.drop_column("payslips", column_name)
