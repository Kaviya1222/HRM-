from __future__ import annotations

from enum import StrEnum


class RoleCode(StrEnum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    HR = "hr"
    TL = "tl"
    EMPLOYEE = "employee"


ROLE_HIERARCHY: list[RoleCode] = [
    RoleCode.SUPER_ADMIN,
    RoleCode.ADMIN,
    RoleCode.HR,
    RoleCode.TL,
    RoleCode.EMPLOYEE,
]

ROLE_DISPLAY_NAMES: dict[RoleCode, str] = {
    RoleCode.SUPER_ADMIN: "Super Admin",
    RoleCode.ADMIN: "Admin",
    RoleCode.HR: "HR",
    RoleCode.TL: "TL",
    RoleCode.EMPLOYEE: "Employee",
}


def normalize_role_code(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_super_admin_role(*, code: str | None = None, name: str | None = None) -> bool:
    return normalize_role_code(code) == RoleCode.SUPER_ADMIN.value or (name or "").strip().lower() == ROLE_DISPLAY_NAMES[RoleCode.SUPER_ADMIN].lower()

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
