from __future__ import annotations

import logging
import re
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.auth import User
from app.models.employee import Employee
from app.models.enums import EmployeeStatus
from app.models.utility import CalendarEvent
from app.services.email_service import EmailService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CalendarService:
    NOTIFY_EVENT_TYPES = {"huddle", "meeting", "leave", "task", "reminder", "general"}

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
            "employee_id": event.employee_id,
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
        event_label = event.event_type.replace("_", " ").title()
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
    def _is_valid_email(value: str) -> bool:
        return bool(EMAIL_PATTERN.fullmatch(value))

    @staticmethod
    def _notify_employees(db: Session, event: CalendarEvent) -> None:
        if event.event_type not in CalendarService.NOTIFY_EVENT_TYPES:
            return

        message = CalendarService._format_event_message(event)
        title = f"New {event.event_type.replace('_', ' ').title()} scheduled"
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
    def _send_event_email(db: Session, event: CalendarEvent, auth: AuthContext) -> tuple[bool, str | None]:
        if event.event_type not in CalendarService.NOTIFY_EVENT_TYPES:
            return False, None

        employees = CalendarService._employee_notification_targets(db)
        if not employees:
            return False, "No active employee email addresses are available."

        event_label = event.event_type.replace("_", " ").title()
        created_by = auth.user.full_name or auth.user.email
        attempted_emails: set[str] = set()
        failed_count = 0

        for employee in employees:
            recipient = str(employee.user.email if employee.user else "").strip()
            dedupe_key = recipient.lower()
            if not dedupe_key or dedupe_key in attempted_emails or not CalendarService._is_valid_email(recipient):
                continue

            attempted_emails.add(dedupe_key)
            employee_name = employee.user.full_name if employee.user and employee.user.full_name else employee.employee_code
            body_lines = [
                f"Hello {employee_name},",
                "",
                f"A new {event_label.lower()} has been scheduled.",
                "",
                f"Title/type: {event.title} ({event_label})",
                f"Date: {event.event_date}",
                f"Time: {event.event_time or '--'}",
                f"Description: {event.description or '--'}",
                f"Created by admin: {created_by}",
                "",
                "Regards,",
                "HRM",
            ]
            email_sent, email_error = EmailService.send_email(
                to_email=recipient,
                subject=f"New {event_label}: {event.title}",
                body="\n".join(body_lines),
            )
            if not email_sent:
                failed_count += 1
                logger.warning("Calendar email notification failed for %s: %s", recipient, email_error)

        if not attempted_emails:
            logger.info("Calendar event %s has no valid employee email addresses to notify.", event.id)
            return True, None
        if failed_count:
            logger.warning(
                "Calendar email notification failed for %s of %s employee email(s) for event %s.",
                failed_count,
                len(attempted_emails),
                event.id,
            )
            return False, f"Email notification failed for {failed_count} employee email(s). Check backend logs."
        return True, None

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
    def list_employee_options(db: Session) -> dict[str, object]:
        employees = CalendarService._employee_notification_targets(db)
        return {
            "items": [
                {
                    "id": employee.id,
                    "employee_code": employee.employee_code,
                    "full_name": employee.user.full_name if employee.user and employee.user.full_name else employee.employee_code,
                    "email": employee.user.email if employee.user else None,
                }
                for employee in employees
            ],
            "total": len(employees),
        }

    @staticmethod
    def create_event(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event title is required")

        event_time = str(payload.get("time") or "").strip()
        event_type = CalendarService._normalize_event_type(payload.get("event_type"))

        event = CalendarEvent(
            title=title,
            description=str(payload.get("description") or "").strip() or None,
            event_date=payload["date"],
            event_time=event_time or None,
            event_type=event_type,
            created_by_user_id=auth.user.id,
            employee_id=None,
        )
        db.add(event)
        db.flush()
        CalendarService._notify_employees(db, event)
        db.commit()
        db.refresh(event)
        email_sent, email_error = CalendarService._send_event_email(db, event, auth)
        response_message = "Calendar event created successfully and email notification sent successfully."
        if event.event_type in CalendarService.NOTIFY_EVENT_TYPES and not email_sent:
            response_message = "Calendar event created successfully, but email notification could not be sent."
        return {
            "message": response_message,
            "event": CalendarService._serialize(event),
            "email_sent": email_sent,
            "email_error": email_error,
        }

    @staticmethod
    def update_event(db: Session, event_id: str, payload: dict[str, object]) -> dict[str, object]:
        event = db.get(CalendarEvent, event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found")

        title = str(payload.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event title is required")

        event_type = CalendarService._normalize_event_type(payload.get("event_type"))

        event.title = title
        event.description = str(payload.get("description") or "").strip() or None
        event.event_date = payload["date"]
        event.event_time = str(payload.get("time") or "").strip() or None
        event.event_type = event_type
        event.employee_id = None
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
