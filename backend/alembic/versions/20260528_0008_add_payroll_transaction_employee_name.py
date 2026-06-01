"""add payroll transaction employee name snapshot

Revision ID: 20260528_0008
Revises: 20260528_0007
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_0008"
down_revision = "20260528_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "payroll_transactions" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("payroll_transactions")}
    if "employee_name" not in columns:
        op.add_column("payroll_transactions", sa.Column("employee_name", sa.String(length=160), nullable=True))

    table_names = set(inspector.get_table_names())
    if {"employees", "users"}.issubset(table_names):
        bind.execute(
            sa.text(
                "UPDATE payroll_transactions pt "
                "LEFT JOIN employees e ON e.id = pt.employee_id "
                "LEFT JOIN users u ON u.id = e.user_id "
                "SET pt.employee_name = COALESCE(NULLIF(TRIM(CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, ''))), ''), e.employee_code) "
                "WHERE pt.employee_id IS NOT NULL AND pt.employee_name IS NULL"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "payroll_transactions" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("payroll_transactions")}
    if "employee_name" in columns:
        op.drop_column("payroll_transactions", "employee_name")
