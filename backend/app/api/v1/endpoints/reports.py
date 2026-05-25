from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_permissions
from app.schemas.report import EmployeeReportSubmitRequest
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/monthly-attendance")
def get_monthly_attendance_report(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    auth: AuthContext = Depends(require_permissions("reports.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    today = date.today()
    month = month or today.month
    year = year or today.year
    return ReportService.monthly_attendance_report(db, auth, month=month, year=year)


@router.get("/submitted")
def get_employee_submitted_reports(
    auth: AuthContext = Depends(require_permissions("reports.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return ReportService.employee_submitted_reports(db, auth)


@router.post("/submitted")
def submit_employee_report(
    payload: EmployeeReportSubmitRequest,
    auth: AuthContext = Depends(require_permissions("reports.submit")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return ReportService.submit_employee_report(db, auth, title=payload.title, report_body=payload.report_body)


@router.get("/submitted/{report_id}")
def get_employee_submitted_report(
    report_id: str,
    auth: AuthContext = Depends(require_permissions("reports.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return ReportService.get_employee_submitted_report(db, auth, report_id)


@router.get("/monthly-attendance/export")
def export_monthly_attendance_csv(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    auth: AuthContext = Depends(require_permissions("reports.export.csv")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    today = date.today()
    month = month or today.month
    year = year or today.year
    csv_text = ReportService.export_monthly_attendance_csv(db, auth, month=month, year=year)
    return StreamingResponse(
        BytesIO(csv_text.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="attendance-report-{year}-{month:02d}.csv"'},
    )
