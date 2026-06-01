from __future__ import annotations

import calendar
import csv
from datetime import date
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.api.deps import AuthContext
from app.models.attendance import AttendanceDailySummary, AttendanceLog
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, LeaveRequestStatus
from app.models.leave import LeaveRequest
from app.models.utility import EmployeeSubmittedReport, Holiday
from app.services.user_scope_service import UserScopeService


class ReportService:
    @staticmethod
    def _working_dates(db: Session, month: int, year: int) -> list[date]:
        _, days_in_month = calendar.monthrange(year, month)
        holidays = {
            holiday.holiday_date
            for holiday in db.execute(select(Holiday).where(Holiday.holiday_date >= date(year, month, 1), Holiday.holiday_date <= date(year, month, days_in_month))).scalars().all()
        }
        dates: list[date] = []
        for day in range(1, days_in_month + 1):
            current = date(year, month, day)
            if current.weekday() >= 5 or current in holidays:
                continue
            dates.append(current)
        return dates

    @staticmethod
    def _scope(db: Session, auth: AuthContext) -> set[str] | None:
        if auth.access.is_super_admin or "attendance.view.all" in auth.access.permission_keys:
            return None
        return UserScopeService.resolve_employee_scope(
            db,
            auth,
            own_permission="attendance.view.own",
            team_permission="attendance.view.team",
            all_permission="attendance.view.all",
        )

    @staticmethod
    def _status_for_day(db: Session, employee_id: str, target_date: date) -> str:
        leave_request = db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveRequestStatus.APPROVED.value,
                LeaveRequest.start_date <= target_date,
                LeaveRequest.end_date >= target_date,
            )
        ).scalar_one_or_none()
        if leave_request is not None:
            return AttendanceStatus.LEAVE.value

        summary = db.execute(
            select(AttendanceDailySummary).where(
                AttendanceDailySummary.employee_id == employee_id,
                AttendanceDailySummary.summary_date == target_date,
            )
        ).scalar_one_or_none()
        if summary is not None:
            return summary.status

        logs = db.execute(
            select(AttendanceLog).where(AttendanceLog.employee_id == employee_id, AttendanceLog.attendance_date == target_date)
        ).scalars().all()
        if any(log.status == AttendanceStatus.HALF_DAY.value for log in logs):
            return AttendanceStatus.HALF_DAY.value
        if any(log.check_in_at or log.status in {"online", "offline", AttendanceStatus.PRESENT.value} for log in logs):
            return AttendanceStatus.PRESENT.value
        if any(log.status == AttendanceStatus.ABSENT.value for log in logs):
            return AttendanceStatus.ABSENT.value
        return AttendanceStatus.ABSENT.value

    @staticmethod
    def monthly_attendance_report(db: Session, auth: AuthContext, *, month: int, year: int) -> dict[str, object]:
        scope_ids = ReportService._scope(db, auth)
        employee_stmt = select(Employee).options(joinedload(Employee.user)).where(Employee.is_deleted.is_(False))
        if scope_ids is not None:
            if not scope_ids:
                return {"items": [], "total": 0}
            employee_stmt = employee_stmt.where(Employee.id.in_(scope_ids))
        employees = db.execute(employee_stmt).scalars().all()

        working_dates = ReportService._working_dates(db, month, year)
        items: list[dict[str, object]] = []
        for employee in employees:
            counters = {
                "present_days": 0,
                "half_days": 0,
                "leave_days": 0,
                "absent_days": 0,
                "working_days": len(working_dates),
            }
            for target_date in working_dates:
                status_value = ReportService._status_for_day(db, str(employee.id), target_date)
                if status_value == AttendanceStatus.PRESENT.value:
                    counters["present_days"] += 1
                elif status_value == AttendanceStatus.HALF_DAY.value:
                    counters["half_days"] += 1
                elif status_value == AttendanceStatus.LEAVE.value:
                    counters["leave_days"] += 1
                else:
                    counters["absent_days"] += 1

            items.append(
                {
                    "employee_id": employee.id,
                    "employee_name": employee.user.full_name if employee.user else employee.employee_code,
                    "employee_code": employee.employee_code,
                    **counters,
                }
            )

        return {"items": items, "total": len(items)}

    @staticmethod
    def export_monthly_attendance_csv(db: Session, auth: AuthContext, *, month: int, year: int) -> str:
        report = ReportService.monthly_attendance_report(db, auth, month=month, year=year)
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["employee_name", "employee_code", "working_days", "present_days", "half_days", "leave_days", "absent_days"],
        )
        writer.writeheader()
        for item in report["items"]:
            writer.writerow(
                {
                    "employee_name": item["employee_name"],
                    "employee_code": item["employee_code"],
                    "working_days": item["working_days"],
                    "present_days": item["present_days"],
                    "half_days": item["half_days"],
                    "leave_days": item["leave_days"],
                    "absent_days": item["absent_days"],
                }
            )
        return output.getvalue()

    @staticmethod
    def employee_submitted_reports(db: Session, auth: AuthContext) -> dict[str, object]:
        scope_ids = ReportService._scope(db, auth)
        if scope_ids is not None and not scope_ids:
            return {"items": [], "total": 0}

        stmt = (
            select(EmployeeSubmittedReport, Employee)
            .join(Employee, EmployeeSubmittedReport.employee_id == Employee.id)
            .options(joinedload(Employee.user), joinedload(Employee.department))
            .where(Employee.is_deleted.is_(False))
            .order_by(EmployeeSubmittedReport.submitted_at.desc(), EmployeeSubmittedReport.created_at.desc())
        )
        if scope_ids is not None:
            stmt = stmt.where(EmployeeSubmittedReport.employee_id.in_(scope_ids))

        rows = db.execute(stmt).unique().all()
        items: list[dict[str, object]] = []
        employee_ids: set[str] = set()
        for submitted_report, employee in rows:
            employee_ids.add(str(employee.id))
            items.append(
                {
                    "id": submitted_report.id,
                    "employee_id": employee.id,
                    "employee_name": employee.user.full_name if employee.user else employee.employee_code,
                    "department": employee.department.name if employee.department else "--",
                    "submitted_at": submitted_report.submitted_at,
                    "title": submitted_report.title,
                    "report_body": submitted_report.report_body or "",
                }
            )

        return {"items": items, "total": len(employee_ids)}

    @staticmethod
    def _submitted_report_payload(submitted_report: EmployeeSubmittedReport, employee: Employee) -> dict[str, object]:
        return {
            "id": submitted_report.id,
            "employee_id": employee.id,
            "employee_name": employee.user.full_name if employee.user else employee.employee_code,
            "department": employee.department.name if employee.department else "--",
            "submitted_at": submitted_report.submitted_at,
            "title": submitted_report.title,
            "report_body": submitted_report.report_body or "",
        }

    @staticmethod
    def submit_employee_report(db: Session, auth: AuthContext, *, title: str, report_body: str) -> dict[str, object]:
        employee = auth.user.employee_profile
        if employee is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee profile is not linked to this user.")

        submitted_report = EmployeeSubmittedReport(
            employee_id=employee.id,
            title=title.strip(),
            report_body=report_body.strip(),
        )
        db.add(submitted_report)
        db.commit()

        refreshed_report, refreshed_employee = db.execute(
            select(EmployeeSubmittedReport, Employee)
            .join(Employee, EmployeeSubmittedReport.employee_id == Employee.id)
            .options(joinedload(Employee.user), joinedload(Employee.department))
            .where(EmployeeSubmittedReport.id == submitted_report.id)
        ).unique().one()
        return ReportService._submitted_report_payload(refreshed_report, refreshed_employee)

    @staticmethod
    def get_employee_submitted_report(db: Session, auth: AuthContext, report_id: str) -> dict[str, object]:
        scope_ids = ReportService._scope(db, auth)
        stmt = (
            select(EmployeeSubmittedReport, Employee)
            .join(Employee, EmployeeSubmittedReport.employee_id == Employee.id)
            .options(joinedload(Employee.user), joinedload(Employee.department))
            .where(EmployeeSubmittedReport.id == report_id, Employee.is_deleted.is_(False))
        )
        if scope_ids is not None:
            if not scope_ids:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submitted report not found.")
            stmt = stmt.where(EmployeeSubmittedReport.employee_id.in_(scope_ids))

        row = db.execute(stmt).unique().one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submitted report not found.")

        submitted_report, employee = row
        return ReportService._submitted_report_payload(submitted_report, employee)
