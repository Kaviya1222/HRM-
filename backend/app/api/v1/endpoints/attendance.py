from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_any_permissions, require_permissions
from app.schemas.attendance import AttendanceCheckInRequest, AttendanceCheckOutRequest, AttendanceCorrectionRequest, ManualAttendanceRequest
from app.services.attendance_service import AttendanceService

router = APIRouter()


@router.get("/meta")
def get_attendance_meta(
    auth: AuthContext = Depends(require_any_permissions("attendance.view.own", "attendance.view.team", "attendance.view.all")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.get_meta(db, auth)


@router.get("/today")
def get_today_attendance(
    auth: AuthContext = Depends(require_any_permissions("attendance.view.own", "attendance.view.team", "attendance.view.all")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.get_today_overview(db, auth)


@router.post("/check-in")
def check_in(
    payload: AttendanceCheckInRequest | None = None,
    auth: AuthContext = Depends(require_permissions("attendance.check_in")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.check_in(db, auth, payload=payload.model_dump(exclude_unset=True) if payload else None)


@router.post("/check-out")
def check_out(
    payload: AttendanceCheckOutRequest | None = None,
    auth: AuthContext = Depends(require_permissions("attendance.check_out")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.check_out(db, auth, payload=payload.model_dump(exclude_unset=True) if payload else None)


@router.get("")
def list_attendance(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    employee_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(require_any_permissions("attendance.view.own", "attendance.view.team", "attendance.view.all")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.list_attendance(
        db,
        auth,
        start_date=start_date,
        end_date=end_date,
        employee_id=str(employee_id) if employee_id else None,
    )


@router.post("/manual")
def update_manual_attendance(
    payload: ManualAttendanceRequest,
    auth: AuthContext = Depends(require_permissions("attendance.correct")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.update_manual_attendance(db, auth, payload=payload.model_dump())


@router.post("/{log_id}/corrections")
def correct_attendance(
    log_id: UUID,
    payload: AttendanceCorrectionRequest,
    auth: AuthContext = Depends(require_permissions("attendance.correct")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return AttendanceService.correct_attendance(db, auth, log_id=str(log_id), payload=payload.model_dump(exclude_unset=True))
