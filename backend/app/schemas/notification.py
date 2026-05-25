from __future__ import annotations

from pydantic import BaseModel


class NotificationReadRequest(BaseModel):
    is_read: bool = True
