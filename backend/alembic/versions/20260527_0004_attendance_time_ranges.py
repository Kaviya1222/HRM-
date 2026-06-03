"""replace attendance minute thresholds with time ranges

Revision ID: 20260527_0004
Revises: 20260527_0003
Create Date: 2026-05-27
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260527_0004"
down_revision = "20260527_0003"
branch_labels = None
depends_on = None


ATTENDANCE_SETTINGS = [
    {
        "key": "attendance.start_time",
        "category": "attendance",
        "name": "Start Time",
        "description": "Check-in at or before this time is treated as on-time.",
        "value_type": "json",
        "value_json": {"hour": 9, "minute": 30},
        "is_public": False,
    },
    {
        "key": "attendance.late_entry_range",
        "category": "attendance",
        "name": "Late Entry",
        "description": "Check-ins in this time range are marked as late entry.",
        "value_type": "json",
        "value_json": {"start_hour": 9, "start_minute": 45, "end_hour": 13, "end_minute": 0},
        "is_public": False,
    },
    {
        "key": "attendance.half_day_range",
        "category": "attendance",
        "name": "Half Day",
        "description": "Check-ins in this time range are marked as half day.",
        "value_type": "json",
        "value_json": {"start_hour": 13, "start_minute": 1, "end_hour": 18, "end_minute": 30},
        "is_public": False,
    },
]


DEPRECATED_ATTENDANCE_KEYS = [
    "attendance.automation_enabled",
    "attendance.check_in_start",
    "attendance.late_entry_cutoff",
    "attendance.late_mark_after_minutes",
    "attendance.half_day_min_minutes",
    "attendance.full_day_min_minutes",
    "attendance.workday_start",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "app_settings" not in set(inspector.get_table_names()):
        return

    bind.execute(
        sa.text('DELETE FROM app_settings WHERE "key" IN :keys').bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": DEPRECATED_ATTENDANCE_KEYS},
    )

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


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "app_settings" not in set(inspector.get_table_names()):
        return

    keys = [item["key"] for item in ATTENDANCE_SETTINGS]
    bind.execute(
        sa.text('DELETE FROM app_settings WHERE "key" IN :keys').bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": keys},
    )
