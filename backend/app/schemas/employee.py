from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.auth import RoleSummary


class DepartmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str


class DesignationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str


class EmployeeManagerSummary(BaseModel):
    id: UUID
    employee_code: str
    full_name: str
    role_name: str | None = None


class EmployeeListItem(BaseModel):
    id: UUID
    user_id: UUID | None = None
    employee_code: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str
    role: RoleSummary | None = None
    department: DepartmentSummary | None = None
    designation: DesignationSummary | None = None
    manager: EmployeeManagerSummary | None = None
    joining_date: date | None = None
    phone_number: str | None = None
    address: str | None = None
    base_salary: Decimal | None = None
    is_billable: bool
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EmployeeListResponse(BaseModel):
    items: list[EmployeeListItem]
    total: int


class EmployeeDetail(EmployeeListItem):
    date_of_birth: date | None = None


class EmployeeCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role_id: UUID
    employee_code: str = Field(min_length=2, max_length=50)
    department_id: UUID | None = None
    designation_id: UUID | None = None
    manager_id: UUID | None = None
    joining_date: date | None = None
    date_of_birth: date | None = None
    phone_number: str | None = Field(default=None, max_length=30)
    address: str | None = None
    base_salary: Decimal | None = None
    is_billable: bool = True


class EmployeeUpdateRequest(BaseModel):
    email: EmailStr
    password: str | None = Field(default=None, min_length=8, max_length=256)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role_id: UUID
    employee_code: str = Field(min_length=2, max_length=50)
    department_id: UUID | None = None
    designation_id: UUID | None = None
    manager_id: UUID | None = None
    joining_date: date | None = None
    date_of_birth: date | None = None
    phone_number: str | None = Field(default=None, max_length=30)
    address: str | None = None
    base_salary: Decimal | None = None
    is_billable: bool = True


class EmployeeStatusUpdateRequest(BaseModel):
    is_active: bool


class EmployeeManagerUpdateRequest(BaseModel):
    manager_id: UUID | None = None
    start_date: date | None = None


class EmployeeMetaResponse(BaseModel):
    roles: list[RoleSummary]
    departments: list[DepartmentSummary]
    designations: list[DesignationSummary]
    managers: list[EmployeeManagerSummary]
