"""add payroll transactions

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "payroll_transactions" not in table_names:
        op.create_table(
            "payroll_transactions",
            sa.Column("transaction_type", sa.String(length=20), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("employee_id", sa.CHAR(length=32), nullable=True),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("id", sa.CHAR(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    index_names = {index["name"] for index in inspector.get_indexes("payroll_transactions")}
    if "ix_payroll_transactions_employee_date" not in index_names:
        op.create_index("ix_payroll_transactions_employee_date", "payroll_transactions", ["employee_id", "transaction_date"], unique=False)
    if "ix_payroll_transactions_employee_id" not in index_names:
        op.create_index(op.f("ix_payroll_transactions_employee_id"), "payroll_transactions", ["employee_id"], unique=False)
    if "ix_payroll_transactions_transaction_date" not in index_names:
        op.create_index(op.f("ix_payroll_transactions_transaction_date"), "payroll_transactions", ["transaction_date"], unique=False)
    if "ix_payroll_transactions_transaction_type" not in index_names:
        op.create_index(op.f("ix_payroll_transactions_transaction_type"), "payroll_transactions", ["transaction_type"], unique=False)
    if "ix_payroll_transactions_type_date" not in index_names:
        op.create_index("ix_payroll_transactions_type_date", "payroll_transactions", ["transaction_type", "transaction_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payroll_transactions_type_date", table_name="payroll_transactions")
    op.drop_index(op.f("ix_payroll_transactions_transaction_type"), table_name="payroll_transactions")
    op.drop_index(op.f("ix_payroll_transactions_transaction_date"), table_name="payroll_transactions")
    op.drop_index(op.f("ix_payroll_transactions_employee_id"), table_name="payroll_transactions")
    op.drop_index("ix_payroll_transactions_employee_date", table_name="payroll_transactions")
    op.drop_table("payroll_transactions")
