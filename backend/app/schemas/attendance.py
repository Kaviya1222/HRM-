from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ManualAttendanceRequest(BaseModel):
    employee_id: UUID
    attendance_date: date
    status: Literal["present", "absent", "leave", "late_come", "half_day"]


class AttendanceCheckInRequest(BaseModel):
    check_in_at: datetime | None = None


class AttendanceCheckOutRequest(BaseModel):
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    elapsed_seconds: int | None = Field(default=None, ge=0)


class AttendanceCorrectionRequest(BaseModel):
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("Reason is required")
        return normalized_value


class AttendanceFilterParams(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    employee_id: str | None = None
