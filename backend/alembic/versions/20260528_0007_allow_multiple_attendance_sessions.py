"""allow multiple attendance sessions per day

Revision ID: 20260528_0007
Revises: 20260527_0006
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_0007"
down_revision = "20260527_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "attendance_logs" not in table_names:
        return

    unique_names = {item["name"] for item in inspector.get_unique_constraints("attendance_logs")}
    for constraint_name in ("uq_attendance_logs_user_date", "uq_attendance_logs_employee_date"):
        if constraint_name in unique_names:
            op.drop_constraint(constraint_name, "attendance_logs", type_="unique")

    if bind.dialect.name.startswith("mysql"):
        indexes = {
            row["Key_name"]
            for row in bind.execute(sa.text("SHOW INDEX FROM attendance_logs")).mappings()
        }
        for index_name in ("uq_attendance_logs_user_date", "uq_attendance_logs_employee_date"):
            if index_name in indexes:
                op.drop_index(index_name, table_name="attendance_logs")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "attendance_logs" not in table_names:
        return

    unique_names = {item["name"] for item in inspector.get_unique_constraints("attendance_logs")}
    if "uq_attendance_logs_employee_date" not in unique_names:
        op.create_unique_constraint("uq_attendance_logs_employee_date", "attendance_logs", ["employee_id", "attendance_date"])
    if "uq_attendance_logs_user_date" not in unique_names:
        op.create_unique_constraint("uq_attendance_logs_user_date", "attendance_logs", ["user_id", "attendance_date"])
