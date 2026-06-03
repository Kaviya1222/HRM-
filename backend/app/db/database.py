from __future__ import annotations


def ensure_database_exists(database_url: str) -> None:
    """Neon/PostgreSQL databases are provisioned by the provider, not by the app."""
    return None


def ensure_attendance_runtime_schema(engine) -> None:
    return None


def ensure_leave_runtime_schema(engine) -> None:
    return None


def ensure_notification_runtime_schema(engine) -> None:
    return None


def ensure_payroll_runtime_schema(engine) -> None:
    return None


def ensure_tracker_runtime_schema(engine) -> None:
    return None
