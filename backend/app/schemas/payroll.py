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


class SalaryProfileUpsertRequest(BaseModel):
    employee_id: str
    date_joined: date | None = None
    department: str | None = None
    sub_department: str | None = None
    designation: str | None = None
    payment_mode: str | None = None
    bank: str | None = None
    bank_ifsc: str | None = None
    bank_account_number: str | None = None
    uan: str | None = None
    pf_number: str | None = None
    pan_number: str | None = None
    actual_payable_days: float | None = Field(default=None, ge=0)
    total_working_days: float | None = Field(default=None, ge=0)
    loss_of_pay: float | None = Field(default=None, ge=0)
    present_days: float | None = Field(default=None, ge=0)
    salary_amount: float | None = Field(default=None, ge=0)


class PayrollRunRequest(BaseModel):
    period_month: int = Field(ge=1, le=12)
    period_year: int = Field(ge=1900)
    employee_id: str | None = None


class PayslipCalculateRequest(BaseModel):
    employee_id: str
    monthly_salary: float = Field(gt=0)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=1900)


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


class PayrollTransactionUpdateRequest(BaseModel):
    transaction_type: Literal["income", "expense", "salary", "amount"] | None = None
    amount: float | None = Field(default=None, gt=0)
    employee_id: str | None = None
    transaction_date: date | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_salary_employee(self) -> "PayrollTransactionUpdateRequest":
        if self.transaction_type == "salary" and not self.employee_id:
            raise ValueError("Employee selection is required for salary transactions")
        return self
