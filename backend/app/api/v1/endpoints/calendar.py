from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_permissions
from app.schemas.calendar import CalendarEventRequest
from app.services.calendar_service import CalendarService

router = APIRouter()


@router.get("/events")
def list_calendar_events(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: AuthContext = Depends(require_permissions("page.calendar.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return CalendarService.list_events(db, start_date=start_date, end_date=end_date)


@router.get("/employee-options")
def list_calendar_employee_options(
    _: AuthContext = Depends(require_permissions("calendar.events.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return CalendarService.list_employee_options(db)


@router.post("/events")
def create_calendar_event(
    payload: CalendarEventRequest,
    auth: AuthContext = Depends(require_permissions("calendar.events.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return CalendarService.create_event(db, auth, payload=payload.model_dump())


@router.put("/events/{event_id}")
def update_calendar_event(
    event_id: UUID,
    payload: CalendarEventRequest,
    _: AuthContext = Depends(require_permissions("calendar.events.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return CalendarService.update_event(db, str(event_id), payload.model_dump())


@router.delete("/events/{event_id}")
def delete_calendar_event(
    event_id: UUID,
    _: AuthContext = Depends(require_permissions("calendar.events.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return CalendarService.delete_event(db, str(event_id))
