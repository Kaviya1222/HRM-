"""add attendance automation settings and uniqueness

Revision ID: 20260527_0003
Revises: 20260526_0002
Create Date: 2026-05-27
"""

from __future__ import annotations

import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260527_0003"
down_revision = "20260526_0002"
branch_labels = None
depends_on = None


ATTENDANCE_SETTINGS = [
    {
        "key": "attendance.automation_enabled",
        "category": "attendance",
        "name": "Attendance Automation",
        "description": "Enable automatic status calculation from check-in, check-out and worked minutes.",
        "value_type": "json",
        "value_json": {"enabled": True},
        "is_public": False,
    },
    {
        "key": "attendance.check_in_start",
        "category": "attendance",
        "name": "Check-In Start Time",
        "description": "Check-in at or before this time is treated as on-time.",
        "value_type": "json",
        "value_json": {"hour": 9, "minute": 30},
        "is_public": False,
    },
    {
        "key": "attendance.late_entry_cutoff",
        "category": "attendance",
        "name": "Late Entry Cutoff Time",
        "description": "Check-in after this time is outside the late-entry window.",
        "value_type": "json",
        "value_json": {"hour": 9, "minute": 45},
        "is_public": False,
    },
    {
        "key": "attendance.full_day_min_minutes",
        "category": "attendance",
        "name": "Full Day Threshold",
        "description": "Minimum worked minutes required for full-day present status.",
        "value_type": "json",
        "value_json": {"minutes": 480},
        "is_public": False,
    },
]


def _delete_duplicate_attendance_logs(bind: sa.Connection, table_name: str) -> None:
    rows = bind.execute(
        sa.text(
            f"SELECT id, employee_id, user_id, attendance_date, created_at, updated_at "
            f"FROM {table_name} ORDER BY attendance_date, employee_id, user_id, updated_at, created_at"
        )
    ).mappings().all()
    grouped: dict[tuple[str, object, object], list[dict[str, object]]] = {}
    for row in rows:
        if row["employee_id"] is not None:
            key = ("employee", row["employee_id"], row["attendance_date"])
        elif row["user_id"] is not None:
            key = ("user", row["user_id"], row["attendance_date"])
        else:
            continue
        grouped.setdefault(key, []).append(dict(row))

    delete_ids: list[str] = []
    for group_rows in grouped.values():
        if len(group_rows) <= 1:
            continue
        keep = max(group_rows, key=lambda item: (item["updated_at"], item["created_at"], item["id"]))
        delete_ids.extend(str(item["id"]) for item in group_rows if item["id"] != keep["id"])

    for index in range(0, len(delete_ids), 500):
        chunk = delete_ids[index:index + 500]
        bind.execute(sa.text(f"DELETE FROM {table_name} WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)), {"ids": chunk})


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "app_settings" in table_names:
        app_settings = sa.table(
            "app_settings",
            sa.column("id", sa.String),
            sa.column("key", sa.String),
            sa.column("category", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.String),
            sa.column("value_type", sa.String),
            sa.column("value_json", sa.JSON),
            sa.column("is_public", sa.Boolean),
        )
        existing_keys = set(bind.execute(sa.text('SELECT "key" FROM app_settings')).scalars().all())
        rows = [{**item, "id": uuid4().hex} for item in ATTENDANCE_SETTINGS if item["key"] not in existing_keys]
        if rows:
            op.bulk_insert(app_settings, rows)

        bind.execute(
            sa.text(
                "UPDATE app_settings SET value_json = :value_json "
                'WHERE "key" = \'attendance.workday_start\''
            ),
            {"value_json": json.dumps({"hour": 9, "minute": 30})},
        )

    if "attendance_logs" in table_names:
        _delete_duplicate_attendance_logs(bind, "attendance_logs")
        unique_names = {item["name"] for item in inspector.get_unique_constraints("attendance_logs")}
        if "uq_attendance_logs_employee_date" not in unique_names:
            op.create_unique_constraint("uq_attendance_logs_employee_date", "attendance_logs", ["employee_id", "attendance_date"])
        if "uq_attendance_logs_user_date" not in unique_names:
            op.create_unique_constraint("uq_attendance_logs_user_date", "attendance_logs", ["user_id", "attendance_date"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "attendance_logs" in table_names:
        unique_names = {item["name"] for item in inspector.get_unique_constraints("attendance_logs")}
        if "uq_attendance_logs_user_date" in unique_names:
            op.drop_constraint("uq_attendance_logs_user_date", "attendance_logs", type_="unique")
        if "uq_attendance_logs_employee_date" in unique_names:
            op.drop_constraint("uq_attendance_logs_employee_date", "attendance_logs", type_="unique")

    if "app_settings" in table_names:
        keys = [item["key"] for item in ATTENDANCE_SETTINGS]
        bind.execute(sa.text('DELETE FROM app_settings WHERE "key" IN :keys').bindparams(sa.bindparam("keys", expanding=True)), {"keys": keys})
