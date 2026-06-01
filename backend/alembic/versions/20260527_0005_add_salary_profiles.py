"""add salary profiles

Revision ID: 20260527_0005
Revises: 20260527_0004
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0005"
down_revision = "20260527_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "salary_profiles" not in table_names:
        op.create_table(
            "salary_profiles",
            sa.Column("employee_id", sa.CHAR(length=32), nullable=False),
            sa.Column("date_joined", sa.Date(), nullable=True),
            sa.Column("department", sa.String(length=120), nullable=True),
            sa.Column("sub_department", sa.String(length=120), nullable=True),
            sa.Column("designation", sa.String(length=120), nullable=True),
            sa.Column("payment_mode", sa.String(length=80), nullable=True),
            sa.Column("bank", sa.String(length=120), nullable=True),
            sa.Column("bank_ifsc", sa.String(length=40), nullable=True),
            sa.Column("bank_account_number", sa.String(length=80), nullable=True),
            sa.Column("uan", sa.String(length=80), nullable=True),
            sa.Column("pf_number", sa.String(length=80), nullable=True),
            sa.Column("pan_number", sa.String(length=40), nullable=True),
            sa.Column("id", sa.CHAR(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("employee_id", name="uq_salary_profiles_employee"),
        )

    index_names = {index["name"] for index in inspector.get_indexes("salary_profiles")}
    if "ix_salary_profiles_employee_id" not in index_names:
        op.create_index(op.f("ix_salary_profiles_employee_id"), "salary_profiles", ["employee_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_salary_profiles_employee_id"), table_name="salary_profiles")
    op.drop_table("salary_profiles")
