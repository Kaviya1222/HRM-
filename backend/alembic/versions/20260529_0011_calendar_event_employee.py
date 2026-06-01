"""Add selected employee to calendar events."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260529_0011"
down_revision = "20260528_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("calendar_events")}
    indexes = {index["name"] for index in inspector.get_indexes("calendar_events")}

    if "employee_id" not in columns:
        op.add_column("calendar_events", sa.Column("employee_id", sa.String(length=36), nullable=True))
    if "ix_calendar_events_employee_id" not in indexes:
        op.create_index(op.f("ix_calendar_events_employee_id"), "calendar_events", ["employee_id"], unique=False)

    inspector = sa.inspect(bind)
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("calendar_events")}
    if "fk_calendar_events_employee_id_employees" not in foreign_keys:
        op.create_foreign_key(
            "fk_calendar_events_employee_id_employees",
            "calendar_events",
            "employees",
            ["employee_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("calendar_events")}
    indexes = {index["name"] for index in inspector.get_indexes("calendar_events")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("calendar_events")}

    if "fk_calendar_events_employee_id_employees" in foreign_keys:
        op.drop_constraint("fk_calendar_events_employee_id_employees", "calendar_events", type_="foreignkey")
    if "ix_calendar_events_employee_id" in indexes:
        op.drop_index(op.f("ix_calendar_events_employee_id"), table_name="calendar_events")
    if "employee_id" in columns:
        op.drop_column("calendar_events", "employee_id")
