from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator


class LeaveCreateRequest(BaseModel):
    employee_id: str | None = None
    leave_type_id: str | None = None
    leave_type: str | None = None
    start_date: date
    end_date: date
    reason: str | None = None
    remarks: str | None = None
    total_days: float | None = None

    @model_validator(mode="after")
    def validate_leave_request(self) -> "LeaveCreateRequest":
        if self.end_date < self.start_date:
            raise ValueError("Leave end date cannot be before start date")
        if not (self.reason or self.remarks or "").strip():
            raise ValueError("Reason is required")
        if not self.leave_type_id and not (self.leave_type or "").strip():
            raise ValueError("Leave type is required")
        return self


class LeaveDecisionRequest(BaseModel):
    decision: str
    remarks: str | None = None
