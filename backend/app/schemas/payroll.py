from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SalaryStructureUpsertRequest(BaseModel):
    employee_id: str | None = None
    grade_name: str | None = None
    basic_salary: float
    allowances: dict[str, float] | None = None
    deductions: dict[str, float] | None = None
    effective_from: date
    effective_to: date | None = None


class PayrollRunRequest(BaseModel):
    period_month: int
    period_year: int
    employee_id: str | None = None


class PayrollTransactionCreateRequest(BaseModel):
    transaction_type: Literal["income", "expense", "salary", "amount"]
    amount: float = Field(gt=0)
    employee_id: str | None = None
    transaction_date: date
    description: str | None = None

    @model_validator(mode="after")
    def validate_salary_employee(self) -> "PayrollTransactionCreateRequest":
        if self.transaction_type == "salary" and not self.employee_id:
            raise ValueError("Employee selection is required for salary transactions")
        return self
