from __future__ import annotations

from enum import StrEnum


class PermissionCategory(StrEnum):
    MODULE = "module"
    MENU = "menu"
    PAGE = "page"
    ACTION = "action"
    APPROVAL = "approval"
    CORRECTION = "correction"
    EXPORT = "export"
    SETTING = "setting"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    LEAVE = "leave"


class LeaveRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PayrollRunStatus(StrEnum):
    DRAFT = "draft"
    PROCESSING = "processing"
    COMPLETED = "completed"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TrackerSessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
