from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.utility import Notification


class NotificationService:
    DEFAULT_TARGETS = {
        "approval": "/leave",
        "leave_approved": "/leave",
        "leave_rejected": "/leave",
        "calendar": "/calendar",
        "payroll": "/payroll",
    }

    @staticmethod
    def serialize(notification: Notification) -> dict[str, object]:
        target_url = notification.target_url or NotificationService.DEFAULT_TARGETS.get(notification.notification_type)
        return {
            "id": notification.id,
            "employee_id": notification.employee_id,
            "event_id": notification.event_id,
            "related_id": notification.related_id,
            "target_url": target_url,
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "metadata_json": notification.metadata_json,
            "read_at": notification.read_at,
            "created_at": notification.created_at,
        }

    @staticmethod
    def create_user_notification(
        db: Session,
        *,
        user_id: UUID | str | None,
        title: str,
        message: str,
        notification_type: str = "info",
        metadata_json: dict[str, object] | None = None,
        employee_id: UUID | str | None = None,
        event_id: UUID | str | None = None,
        related_id: UUID | str | None = None,
        target_url: str | None = None,
        auto_commit: bool = False,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            employee_id=employee_id,
            event_id=event_id,
            related_id=str(related_id) if related_id is not None else None,
            target_url=target_url or NotificationService.DEFAULT_TARGETS.get(notification_type),
            title=title,
            message=message,
            notification_type=notification_type,
            metadata_json=metadata_json,
        )
        db.add(notification)
        if auto_commit:
            db.commit()
            db.refresh(notification)
        return notification

    @staticmethod
    def create_bulk_notifications(
        db: Session,
        *,
        user_ids: list[UUID | str],
        title: str,
        message: str,
        notification_type: str = "info",
        metadata_json: dict[str, object] | None = None,
        related_id: UUID | str | None = None,
        target_url: str | None = None,
    ) -> None:
        seen: set[str] = set()
        for user_id in user_ids:
            value = str(user_id)
            if value in seen:
                continue
            seen.add(value)
            NotificationService.create_user_notification(
                db,
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                metadata_json=metadata_json,
                related_id=related_id,
                target_url=target_url,
            )

    @staticmethod
    def list_user_notifications(db: Session, *, user_id: UUID | str, unread_only: bool = False) -> dict[str, object]:
        stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc())
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        notifications = db.execute(stmt).scalars().all()
        unread_count = db.execute(
            select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
        ).scalars().all()
        return {
            "items": [NotificationService.serialize(item) for item in notifications],
            "unread_count": len(unread_count),
        }

    @staticmethod
    def mark_notification_read(
        db: Session,
        *,
        user_id: UUID | str,
        notification_id: UUID | str,
        is_read: bool = True,
    ) -> dict[str, object]:
        notification = db.get(Notification, notification_id)
        if notification is None or str(notification.user_id) != str(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

        notification.read_at = datetime.now(UTC) if is_read else None
        db.commit()
        db.refresh(notification)
        return NotificationService.serialize(notification)
