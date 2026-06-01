"""add salary profile attendance fields

Revision ID: 20260527_0006
Revises: 20260527_0005
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0006"
down_revision = "20260527_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("salary_profiles")}

    if "total_working_days" not in columns:
        op.add_column("salary_profiles", sa.Column("total_working_days", sa.Numeric(8, 2), nullable=True))
    if "loss_of_pay" not in columns:
        op.add_column("salary_profiles", sa.Column("loss_of_pay", sa.Numeric(8, 2), nullable=True))
    if "present_days" not in columns:
        op.add_column("salary_profiles", sa.Column("present_days", sa.Numeric(8, 2), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("salary_profiles")}

    if "present_days" in columns:
        op.drop_column("salary_profiles", "present_days")
    if "loss_of_pay" in columns:
        op.drop_column("salary_profiles", "loss_of_pay")
    if "total_working_days" in columns:
        op.drop_column("salary_profiles", "total_working_days")
