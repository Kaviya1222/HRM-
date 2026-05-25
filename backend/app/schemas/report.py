from __future__ import annotations

from pydantic import BaseModel, Field


class EmployeeReportSubmitRequest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    report_body: str = Field(min_length=1)
