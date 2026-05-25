from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_any_permissions, require_permissions
from app.schemas.leave import LeaveCreateRequest, LeaveDecisionRequest
from app.services.leave_service import LeaveService

router = APIRouter()


@router.get("/meta")
def get_leave_meta(
    auth: AuthContext = Depends(require_any_permissions("leave.apply", "leave.view.own", "leave.view.team", "leave.view.all")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return LeaveService.get_meta(db, auth)


@router.get("/requests")
def list_leave_requests(
    status: str | None = Query(default=None),
    employee_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(require_any_permissions("leave.view.own", "leave.view.team", "leave.view.all", "leave.approve", "leave.recommend")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return LeaveService.list_requests(
        db,
        auth,
        status_filter=status,
        employee_id=str(employee_id) if employee_id else None,
    )


@router.post("/requests")
def apply_leave(
    payload: LeaveCreateRequest,
    auth: AuthContext = Depends(require_permissions("leave.apply")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return LeaveService.apply_leave(db, auth, payload.model_dump())


@router.post("/requests/{leave_request_id}/decision")
def decide_leave(
    leave_request_id: UUID,
    payload: LeaveDecisionRequest,
    auth: AuthContext = Depends(require_any_permissions("leave.approve", "leave.recommend")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return LeaveService.decide_leave(
        db,
        auth,
        leave_request_id=str(leave_request_id),
        decision=payload.decision,
        remarks=payload.remarks,
    )
