from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import attendance, auth, calendar, dashboard, employees, leave, notifications, payroll, reports, search, settings, tracker

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(employees.router, prefix="/employees", tags=["Employees"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(leave.router, prefix="/leave", tags=["Leave"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(tracker.router, prefix="/tracker", tags=["Tracker"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(settings.router, prefix="/settings", tags=["Super Admin Settings"])
