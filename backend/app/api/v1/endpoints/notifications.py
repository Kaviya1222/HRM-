from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_any_permissions
from app.schemas.notification import NotificationReadRequest
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("")
def list_notifications(
    unread_only: bool = Query(default=False),
    auth: AuthContext = Depends(require_any_permissions("notifications.view.own", "notifications.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return NotificationService.list_user_notifications(db, user_id=auth.user.id, unread_only=unread_only)


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    payload: NotificationReadRequest,
    auth: AuthContext = Depends(require_any_permissions("notifications.view.own", "notifications.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return NotificationService.mark_notification_read(
        db,
        user_id=auth.user.id,
        notification_id=notification_id,
        is_read=payload.is_read,
    )
