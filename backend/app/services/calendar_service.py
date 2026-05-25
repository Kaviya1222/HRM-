from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.auth import User
from app.models.employee import Employee
from app.models.enums import EmployeeStatus
from app.models.utility import CalendarEvent
from app.services.notification_service import NotificationService


class CalendarService:
    NOTIFY_EVENT_TYPES = {"huddle", "meeting"}

    @staticmethod
    def _normalize_event_type(value: object) -> str:
        event_type = str(value or "").strip().lower().replace(" ", "_")
        if event_type not in {"huddle", "meeting", "leave", "task", "reminder", "general"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid calendar event type")
        return event_type

    @staticmethod
    def _serialize(event: CalendarEvent) -> dict[str, object]:
        return {
            "id": event.id,
            "title": event.title,
            "description": event.description or "",
            "date": event.event_date,
            "time": event.event_time or "",
            "type": event.event_type,
            "event_type": event.event_type,
            "created_by": event.created_by_user_id,
            "created_at": event.created_at,
        }

    @staticmethod
    def _employee_notification_targets(db: Session) -> list[Employee]:
        employees = db.execute(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .options(joinedload(Employee.user))
            .where(
                User.is_active.is_(True),
                Employee.is_deleted.is_(False),
                Employee.status == EmployeeStatus.ACTIVE.value,
            )
        ).scalars().unique().all()
        return [employee for employee in employees if employee.user_id]

    @staticmethod
    def _format_event_message(event: CalendarEvent) -> str:
        event_label = "Huddle" if event.event_type == "huddle" else "Meeting"
        date_label = event.event_date.strftime("%d %b")
        if event.event_time:
            hour, minute = event.event_time.split(":")[:2]
            hour_number = int(hour)
            period = "PM" if hour_number >= 12 else "AM"
            display_hour = hour_number % 12 or 12
            time_label = f"{display_hour}:{minute} {period}"
            return f"New {event_label} scheduled: {event.title} on {date_label} at {time_label}"
        return f"New {event_label} scheduled: {event.title} on {date_label}"

    @staticmethod
    def _notify_employees(db: Session, event: CalendarEvent) -> None:
        if event.event_type not in CalendarService.NOTIFY_EVENT_TYPES:
            return

        message = CalendarService._format_event_message(event)
        title = f"New {event.event_type.title()} scheduled"
        for employee in CalendarService._employee_notification_targets(db):
            NotificationService.create_user_notification(
                db,
                user_id=employee.user_id,
                employee_id=employee.id,
                event_id=event.id,
                related_id=event.id,
                target_url="/calendar",
                title=title,
                message=message,
                notification_type="calendar",
                metadata_json={
                    "event_id": str(event.id),
                    "employee_id": str(employee.id),
                    "event_type": event.event_type,
                    "event_date": event.event_date.isoformat(),
                },
            )

    @staticmethod
    def list_events(db: Session, *, start_date: date | None = None, end_date: date | None = None) -> dict[str, object]:
        stmt = select(CalendarEvent).order_by(CalendarEvent.event_date.asc(), CalendarEvent.event_time.asc(), CalendarEvent.title.asc())
        if start_date:
            stmt = stmt.where(CalendarEvent.event_date >= start_date)
        if end_date:
            stmt = stmt.where(CalendarEvent.event_date <= end_date)
        events = db.execute(stmt).scalars().all()
        return {"items": [CalendarService._serialize(event) for event in events], "total": len(events)}

    @staticmethod
    def create_event(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event title is required")

        event_time = str(payload.get("time") or "").strip()
        event = CalendarEvent(
            title=title,
            description=str(payload.get("description") or "").strip() or None,
            event_date=payload["date"],
            event_time=event_time or None,
            event_type=CalendarService._normalize_event_type(payload.get("event_type")),
            created_by_user_id=auth.user.id,
        )
        db.add(event)
        db.flush()
        CalendarService._notify_employees(db, event)
        db.commit()
        db.refresh(event)
        return {"message": "Calendar event created successfully", "event": CalendarService._serialize(event)}

    @staticmethod
    def update_event(db: Session, event_id: str, payload: dict[str, object]) -> dict[str, object]:
        event = db.get(CalendarEvent, event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")

        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event title is required")

        event.title = title
        event.description = str(payload.get("description") or "").strip() or None
        event.event_date = payload["date"]
        event.event_time = str(payload.get("time") or "").strip() or None
        event.event_type = CalendarService._normalize_event_type(payload.get("event_type"))
        db.commit()
        db.refresh(event)
        return {"message": "Calendar event updated successfully", "event": CalendarService._serialize(event)}

    @staticmethod
    def delete_event(db: Session, event_id: str) -> dict[str, object]:
        event = db.get(CalendarEvent, event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")
        db.delete(event)
        db.commit()
        return {"message": "Calendar event deleted successfully"}
