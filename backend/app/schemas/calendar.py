from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CalendarEventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    event_type: str
    date: date
    time: str | None = None
    description: str | None = None

