"""Prevent duplicate salary transactions per employee period."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_0010"
down_revision = "20260528_0009"
branch_labels = None
depends_on = None


def _constraint_exists(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    return any(constraint["name"] == constraint_name for constraint in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("payroll_transactions")}

    if "payroll_month" not in columns:
        op.add_column("payroll_transactions", sa.Column("payroll_month", sa.Integer(), nullable=True))
    if "payroll_year" not in columns:
        op.add_column("payroll_transactions", sa.Column("payroll_year", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("payroll_transactions")}
    if "ix_payroll_transactions_payroll_month" not in indexes:
        op.create_index(op.f("ix_payroll_transactions_payroll_month"), "payroll_transactions", ["payroll_month"], unique=False)
    if "ix_payroll_transactions_payroll_year" not in indexes:
        op.create_index(op.f("ix_payroll_transactions_payroll_year"), "payroll_transactions", ["payroll_year"], unique=False)

    bind.execute(
        sa.text(
            """
            UPDATE payroll_transactions
            SET payroll_month = EXTRACT(MONTH FROM transaction_date),
                payroll_year = EXTRACT(YEAR FROM transaction_date)
            WHERE transaction_type = 'salary'
              AND employee_id IS NOT NULL
              AND transaction_date IS NOT NULL
              AND (payroll_month IS NULL OR payroll_year IS NULL)
            """
        )
    )

    duplicate_rows = bind.execute(
        sa.text(
            """
            SELECT id, employee_id, payroll_month, payroll_year, updated_at, created_at
            FROM payroll_transactions
            WHERE transaction_type = 'salary'
              AND employee_id IS NOT NULL
              AND payroll_month IS NOT NULL
              AND payroll_year IS NOT NULL
            """
        )
    ).mappings().all()

    keepers: dict[tuple[str, int, int], object] = {}
    duplicate_ids: list[str] = []
    for row in duplicate_rows:
        key = (str(row["employee_id"]), int(row["payroll_month"]), int(row["payroll_year"]))
        current = keepers.get(key)
        if current is None:
            keepers[key] = row
            continue

        row_order = (row["updated_at"], row["created_at"], row["id"])
        current_order = (current["updated_at"], current["created_at"], current["id"])
        if row_order > current_order:
            duplicate_ids.append(str(current["id"]))
            keepers[key] = row
        else:
            duplicate_ids.append(str(row["id"]))

    for duplicate_id in duplicate_ids:
        bind.execute(sa.text("DELETE FROM payroll_transactions WHERE id = :id"), {"id": duplicate_id})

    inspector = sa.inspect(bind)
    if not _constraint_exists(inspector, "payroll_transactions", "uq_salary_transaction_employee_period"):
        op.create_unique_constraint(
            "uq_salary_transaction_employee_period",
            "payroll_transactions",
            ["transaction_type", "employee_id", "payroll_month", "payroll_year"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("payroll_transactions")}
    indexes = {index["name"] for index in inspector.get_indexes("payroll_transactions")}

    if _constraint_exists(inspector, "payroll_transactions", "uq_salary_transaction_employee_period"):
        op.drop_constraint("uq_salary_transaction_employee_period", "payroll_transactions", type_="unique")
    if "ix_payroll_transactions_payroll_year" in indexes:
        op.drop_index(op.f("ix_payroll_transactions_payroll_year"), table_name="payroll_transactions")
    if "ix_payroll_transactions_payroll_month" in indexes:
        op.drop_index(op.f("ix_payroll_transactions_payroll_month"), table_name="payroll_transactions")
    if "payroll_year" in columns:
        op.drop_column("payroll_transactions", "payroll_year")
    if "payroll_month" in columns:
        op.drop_column("payroll_transactions", "payroll_month")
