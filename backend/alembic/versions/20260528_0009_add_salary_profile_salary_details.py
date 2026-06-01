"""Add salary detail fields to salary profiles."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_0009"
down_revision = "20260528_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("salary_profiles")}

    if "actual_payable_days" not in columns:
        op.add_column("salary_profiles", sa.Column("actual_payable_days", sa.Numeric(8, 2), nullable=True))
    if "salary_amount" not in columns:
        op.add_column("salary_profiles", sa.Column("salary_amount", sa.Numeric(12, 2), nullable=True))
    if "salary_transaction_id" not in columns:
        op.add_column("salary_profiles", sa.Column("salary_transaction_id", sa.String(length=32), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("salary_profiles")}
    if "ix_salary_profiles_salary_transaction_id" not in indexes:
        op.create_index(
            op.f("ix_salary_profiles_salary_transaction_id"),
            "salary_profiles",
            ["salary_transaction_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("salary_profiles")}
    columns = {column["name"] for column in inspector.get_columns("salary_profiles")}

    if "ix_salary_profiles_salary_transaction_id" in indexes:
        op.drop_index(op.f("ix_salary_profiles_salary_transaction_id"), table_name="salary_profiles")
    if "salary_transaction_id" in columns:
        op.drop_column("salary_profiles", "salary_transaction_id")
    if "salary_amount" in columns:
        op.drop_column("salary_profiles", "salary_amount")
    if "actual_payable_days" in columns:
        op.drop_column("salary_profiles", "actual_payable_days")
