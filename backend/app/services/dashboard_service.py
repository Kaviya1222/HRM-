from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.attendance import AttendanceLog
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, LeaveRequestStatus
from app.models.leave import LeaveRequest, LeaveType
from app.models.payroll import SalaryStructure
from app.models.utility import CalendarEvent, Holiday
from app.services.attendance_service import AttendanceService
from app.services.payroll_service import PayrollService
from app.services.report_service import ReportService
from app.services.user_scope_service import UserScopeService


class DashboardService:
    @staticmethod
    def _scope(db: Session, auth: AuthContext) -> set[str] | None:
        if auth.access.is_super_admin:
            return None
        if any(key in auth.access.permission_keys for key in ["dashboard.view.super_admin", "dashboard.view.admin", "dashboard.view.hr", "attendance.view.all"]):
            return None
        if "dashboard.view.team" in auth.access.permission_keys or "attendance.view.team" in auth.access.permission_keys:
            return UserScopeService.get_team_employee_ids(db, auth, include_self=True)
        return UserScopeService.resolve_employee_scope(
            db,
            auth,
            own_permission="attendance.view.own",
            team_permission="attendance.view.team",
            all_permission="attendance.view.all",
        )

    @staticmethod
    def _daterange(start_date: date, end_date: date):
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)

    @staticmethod
    def _shift_month(base_date: date, months: int) -> date:
        total_month_index = (base_date.year * 12 + (base_date.month - 1)) + months
        year = total_month_index // 12
        month = total_month_index % 12 + 1
        return date(year, month, 1)

    @staticmethod
    def _month_starts(today: date, count: int) -> list[date]:
        current_month_start = today.replace(day=1)
        return [DashboardService._shift_month(current_month_start, -offset) for offset in range(count - 1, -1, -1)]

    @staticmethod
    def _format_currency(amount: Decimal | float | int) -> str:
        numeric_amount = float(amount)
        if numeric_amount >= 1_00_00_000:
            return f"INR {numeric_amount / 1_00_00_000:.2f} Cr"
        if numeric_amount >= 1_00_000:
            return f"INR {numeric_amount / 1_00_000:.2f} L"
        return f"INR {numeric_amount:,.0f}"

    @staticmethod
    def _employees_for_scope(db: Session, scope_ids: set[str] | None) -> list[Employee]:
        employees_stmt = select(Employee).options(joinedload(Employee.user)).where(Employee.is_deleted.is_(False))
        if scope_ids is not None:
            if not scope_ids:
                return []
            employees_stmt = employees_stmt.where(Employee.id.in_(scope_ids))
        return db.execute(employees_stmt).scalars().all()

    @staticmethod
    def _leave_requests_in_scope(
        db: Session,
        *,
        employee_ids: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        status_value: str | None = None,
    ) -> list[LeaveRequest]:
        if not employee_ids:
            return []
        stmt = select(LeaveRequest).where(LeaveRequest.employee_id.in_(employee_ids))
        if status_value is not None:
            stmt = stmt.where(LeaveRequest.status == status_value)
        if start_date is not None:
            stmt = stmt.where(LeaveRequest.end_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(LeaveRequest.start_date <= end_date)
        return db.execute(stmt).scalars().all()

    @staticmethod
    def _attendance_logs_in_range(db: Session, *, employee_ids: list[str], start_date: date, end_date: date) -> list[AttendanceLog]:
        if not employee_ids:
            return []
        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id.in_(employee_ids),
                AttendanceLog.attendance_date >= start_date,
                AttendanceLog.attendance_date <= end_date,
            )
        ).scalars().all()

        return logs

    @staticmethod
    def _current_period_salary_structure_map(db: Session, *, employee_ids: list[str], period_start: date, period_end: date) -> dict[str, SalaryStructure]:
        if not employee_ids:
            return {}

        structures = db.execute(
            select(SalaryStructure)
            .where(
                SalaryStructure.employee_id.in_(employee_ids),
                SalaryStructure.effective_from <= period_end,
            )
            .order_by(SalaryStructure.employee_id.asc(), SalaryStructure.effective_from.desc())
        ).scalars().all()

        active_structures: dict[str, SalaryStructure] = {}
        for structure in structures:
            employee_id = str(structure.employee_id)
            if employee_id in active_structures:
                continue
            if structure.effective_to is None or structure.effective_to >= period_start:
                active_structures[employee_id] = structure
        return active_structures

    @staticmethod
    def _working_hours_analysis(active_employee_ids: list[str], logs: list[AttendanceLog], today: date) -> dict[str, object]:
        labels: list[str] = []
        total_hours: list[float] = []
        average_hours: list[float] = []

        logs_by_day: dict[date, list[AttendanceLog]] = {}
        for log in logs:
            logs_by_day.setdefault(log.attendance_date, []).append(log)

        start_date = today - timedelta(days=6)
        for target_date in DashboardService._daterange(start_date, today):
            labels.append(target_date.strftime("%d %b"))
            day_logs = logs_by_day.get(target_date, [])
            worked_logs = [log for log in day_logs if log.work_minutes]
            total_minutes = sum(log.work_minutes for log in worked_logs)
            present_count = len({str(log.employee_id) for log in worked_logs})
            total_hours.append(round(total_minutes / 60, 2))
            average_hours.append(round((total_minutes / max(present_count, 1)) / 60, 2) if present_count else 0)

        return {
            "labels": labels,
            "total_hours": total_hours,
            "average_hours": average_hours,
            "employee_scope_count": len(active_employee_ids),
        }

    @staticmethod
    def _leave_usage_analysis(db: Session, *, employee_ids: list[str], today: date) -> dict[str, object]:
        month_starts = DashboardService._month_starts(today, 6)
        month_keys = [(item.year, item.month) for item in month_starts]
        labels = [item.strftime("%b %Y") for item in month_starts]
        month_totals = {key: 0 for key in month_keys}

        start_window = month_starts[0]
        end_window = DashboardService._shift_month(today.replace(day=1), 1) - timedelta(days=1)
        leave_requests = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=employee_ids,
            start_date=start_window,
            end_date=end_window,
        )
        leave_types = sorted(db.execute(select(LeaveType)).scalars().all(), key=lambda item: item.name)
        leave_type_map = {str(item.id): item.name for item in leave_types}
        leave_type_totals: dict[str, int] = {str(item.id): 0 for item in leave_types}

        excluded_statuses = {LeaveRequestStatus.REJECTED.value, LeaveRequestStatus.CANCELLED.value}
        for leave_request in leave_requests:
            if leave_request.status in excluded_statuses:
                continue
            effective_start = max(leave_request.start_date, start_window)
            effective_end = min(leave_request.end_date, end_window)
            if effective_start > effective_end:
                continue
            leave_type_key = str(leave_request.leave_type_id)
            leave_type_totals.setdefault(leave_type_key, 0)
            for leave_day in DashboardService._daterange(effective_start, effective_end):
                month_key = (leave_day.year, leave_day.month)
                if month_key not in month_totals:
                    continue
                month_totals[month_key] += 1
                leave_type_totals[leave_type_key] = leave_type_totals.get(leave_type_key, 0) + 1

        return {
            "labels": labels,
            "values": [month_totals[key] for key in month_keys],
            "by_type": [
                {"label": leave_type_map.get(key, "Leave"), "value": value}
                for key, value in leave_type_totals.items()
            ],
        }

    @staticmethod
    def _attendance_trend(
        active_employee_ids: list[str],
        logs: list[AttendanceLog],
        recent_leaves: list[LeaveRequest],
        today: date,
        *,
        days: int = 30,
    ) -> dict[str, object]:
        labels: list[str] = []
        present_series: list[int] = []
        leave_series: list[int] = []
        absent_series: list[int] = []

        latest_logs: dict[tuple[str, date], AttendanceLog] = {}
        for log in logs:
            if not log.employee_id:
                continue
            log_key = (str(log.employee_id), log.attendance_date)
            existing_log = latest_logs.get(log_key)
            if existing_log is None or (log.updated_at, log.created_at) >= (existing_log.updated_at, existing_log.created_at):
                latest_logs[log_key] = log

        logs_by_day: dict[date, list[AttendanceLog]] = {}
        for log in latest_logs.values():
            logs_by_day.setdefault(log.attendance_date, []).append(log)

        leave_map: dict[date, set[str]] = {}
        for leave_request in recent_leaves:
            if leave_request.status in {LeaveRequestStatus.REJECTED.value, LeaveRequestStatus.CANCELLED.value}:
                continue
            for leave_day in DashboardService._daterange(leave_request.start_date, leave_request.end_date):
                if leave_day > today:
                    break
                leave_map.setdefault(leave_day, set()).add(str(leave_request.employee_id))

        start_date = today - timedelta(days=max(days - 1, 0))
        active_employee_set = set(active_employee_ids)
        for target_date in DashboardService._daterange(start_date, today):
            labels.append(target_date.strftime("%d %b"))
            day_logs = logs_by_day.get(target_date, [])
            leave_ids = leave_map.get(target_date, set()) & active_employee_set
            present_ids = {
                str(log.employee_id)
                for log in day_logs
                if log.check_in_at or log.status in [AttendanceStatus.PRESENT.value, AttendanceStatus.HALF_DAY.value, "online", "offline"]
            } - leave_ids
            absent_ids = {
                str(log.employee_id)
                for log in day_logs
                if log.status == AttendanceStatus.ABSENT.value
            } - leave_ids - present_ids
            present_series.append(len(present_ids))
            leave_series.append(len(leave_ids))
            absent_series.append(len(absent_ids))

        return {
            "labels": labels,
            "present": present_series,
            "leave": leave_series,
            "absent": absent_series,
        }

    @staticmethod
    def _upcoming_events(
        db: Session,
        *,
        today: date,
        pending_approvals: int,
        payroll_pending_tasks: int,
        pending_payments: int,
    ) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []

        holidays = db.execute(
            select(Holiday).where(Holiday.holiday_date >= today).order_by(Holiday.holiday_date.asc()).limit(3)
        ).scalars().all()
        for holiday in holidays:
            events.append(
                {
                    "title": holiday.name,
                    "date": holiday.holiday_date,
                    "time": "All day",
                    "type": "holiday",
                    "subtitle": "Company event",
                }
            )

        calendar_events = db.execute(
            select(CalendarEvent)
            .where(CalendarEvent.event_date >= today)
            .order_by(CalendarEvent.event_date.asc(), CalendarEvent.event_time.asc(), CalendarEvent.title.asc())
            .limit(6)
        ).scalars().all()
        for calendar_event in calendar_events:
            event_time = calendar_event.event_time or "All day"
            events.append(
                {
                    "title": calendar_event.title,
                    "date": calendar_event.event_date,
                    "time": event_time,
                    "type": calendar_event.event_type,
                    "subtitle": calendar_event.description or calendar_event.event_type.replace("_", " ").title(),
                }
            )

        if pending_approvals:
            events.append(
                {
                    "title": "Leave Approval Review",
                    "date": today,
                    "time": "10:00 AM",
                    "type": "workflow",
                    "subtitle": f"{pending_approvals} request(s) awaiting approval",
                }
            )

        if payroll_pending_tasks or pending_payments:
            payroll_day = date(today.year, today.month, min(25, calendar.monthrange(today.year, today.month)[1]))
            if payroll_day < today:
                payroll_day = DashboardService._shift_month(today.replace(day=1), 1).replace(day=25)
            events.append(
                {
                    "title": "Payroll Processing Window",
                    "date": payroll_day,
                    "time": "04:00 PM",
                    "type": "payroll",
                    "subtitle": f"{pending_payments} pending payment(s), {payroll_pending_tasks} payroll setup task(s)",
                }
            )

        events.sort(key=lambda item: (item["date"], item["time"] == "All day", item["title"]))
        return events[:4]

    @staticmethod
    def _today_attendance_counts(db: Session, auth: AuthContext, *, active_count: int, today: date) -> dict[str, int | float]:
        attendance_response = AttendanceService.list_attendance(db, auth, start_date=today, end_date=today)
        attendance_items = attendance_response.get("items", [])

        late_count = sum(
            1
            for item in attendance_items
            if item.get("status") == AttendanceStatus.PRESENT.value and item.get("is_late")
        )
        half_day_count = sum(1 for item in attendance_items if item.get("status") == AttendanceStatus.HALF_DAY.value)
        absent_count = sum(1 for item in attendance_items if item.get("status") == AttendanceStatus.ABSENT.value)
        present_record_count = sum(
            1
            for item in attendance_items
            if item.get("status") == AttendanceStatus.PRESENT.value and not item.get("is_late")
        )
        leave_count = sum(1 for item in attendance_items if item.get("status") == AttendanceStatus.LEAVE.value)
        non_present_count = late_count + half_day_count + absent_count
        present_count = max(active_count - non_present_count, present_record_count)
        attended_count = present_count + late_count + half_day_count
        attendance_percentage = round((attended_count / active_count) * 100, 1) if active_count else 0.0

        return {
            "present": present_count,
            "late": late_count,
            "half_day": half_day_count,
            "absent": absent_count,
            "leave": leave_count,
            "attended": attended_count,
            "attendance_percentage": attendance_percentage,
        }

    @staticmethod
    def summary(db: Session, auth: AuthContext) -> dict[str, object]:
        scope_ids = DashboardService._scope(db, auth)
        employees = DashboardService._employees_for_scope(db, scope_ids)
        today = date.today()

        active_employees = [employee for employee in employees if employee.status == "active"]
        inactive_employees = [employee for employee in employees if employee.status != "active"]
        employee_ids = [str(item.id) for item in employees]
        active_employee_ids = [str(item.id) for item in active_employees]
        total_employee_count = len(employees)
        active_count = len(active_employees)
        inactive_count = len(inactive_employees)

        attendance_counts = DashboardService._today_attendance_counts(db, auth, active_count=active_count, today=today)
        present_today_count = int(attendance_counts["present"])
        late_comers_count = int(attendance_counts["late"])
        half_day_count = int(attendance_counts["half_day"])
        absent_count = int(attendance_counts["absent"])
        attended_count = int(attendance_counts["attended"])
        attendance_percentage = float(attendance_counts["attendance_percentage"])

        pending_approvals = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=[str(item.id) for item in employees],
            status_value=LeaveRequestStatus.PENDING.value,
        )
        pending_leave_approvals = len(pending_approvals)

        payroll_summary = PayrollService.dashboard_summary(
            db,
            auth,
            employee_ids=active_employee_ids,
            month=today.month,
            year=today.year,
        )
        payroll_pending_tasks = int(payroll_summary["payroll_pending_tasks"])
        pending_payments = int(payroll_summary["pending_payslips"])
        total_income = Decimal(str(payroll_summary["total_income"]))
        total_expense = Decimal(str(payroll_summary["total_expense"]))
        payroll_page_summary = PayrollService.get_transaction_summary(db, auth)
        total_salary = Decimal(str(payroll_page_summary["total_salary"]))

        monthly_report = ReportService.monthly_attendance_report(db, auth, month=today.month, year=today.year)

        recent_logs = DashboardService._attendance_logs_in_range(
            db,
            employee_ids=active_employee_ids,
            start_date=today - timedelta(days=6),
            end_date=today,
        )
        trend_start_date = today - timedelta(days=29)
        trend_logs = DashboardService._attendance_logs_in_range(
            db,
            employee_ids=active_employee_ids,
            start_date=trend_start_date,
            end_date=today,
        )
        trend_recent_leaves = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=active_employee_ids,
            start_date=trend_start_date,
            end_date=today,
        )

        upcoming_events = DashboardService._upcoming_events(
            db,
            today=today,
            pending_approvals=pending_leave_approvals,
            payroll_pending_tasks=payroll_pending_tasks,
            pending_payments=pending_payments,
        )

        cards = [
            {
                "key": "present_today",
                "label": "Present Today",
                "value": present_today_count,
                "display_value": str(present_today_count).zfill(2),
                "helper": "Marked present today",
                "accent": "green",
            },
            {
                "key": "late_comers_count",
                "label": "Late Entry",
                "value": late_comers_count,
                "display_value": str(late_comers_count).zfill(2),
                "helper": "Marked late come today",
                "accent": "amber",
            },
            {
                "key": "absent_count",
                "label": "Absent",
                "value": absent_count,
                "display_value": str(absent_count).zfill(2),
                "helper": "Marked absent today",
                "accent": "red",
            },
            {
                "key": "half_day_count",
                "label": "Half Day",
                "value": half_day_count,
                "display_value": str(half_day_count).zfill(2),
                "helper": "Marked half day today",
                "accent": "violet",
            },
            {
                "key": "total_employees",
                "label": "Total Employees",
                "value": total_employee_count,
                "display_value": str(total_employee_count),
                "helper": f"Active {active_count} / Inactive {inactive_count}",
                "accent": "blue",
            },
            {
                "key": "today_attendance_pct",
                "label": "Today Attendance %",
                "value": attendance_percentage,
                "display_value": f"{attendance_percentage:.1f}%",
                "helper": f"{attended_count} marked present/late/half-day out of {active_count} active",
                "accent": "green",
            },
            {
                "key": "pending_leave_approvals",
                "label": "Pending Leave Approvals",
                "value": pending_leave_approvals,
                "display_value": str(pending_leave_approvals),
                "helper": "Requests waiting for action",
                "accent": "orange",
            },
            {
                "key": "payroll_total_income",
                "label": "Payroll Total Income",
                "value": float(total_income),
                "display_value": DashboardService._format_currency(total_income),
                "helper": "From payroll income transactions",
                "accent": "green",
            },
            {
                "key": "payroll_total_expense",
                "label": "Payroll Total Expense",
                "value": float(total_expense),
                "display_value": DashboardService._format_currency(total_expense),
                "helper": "From payroll expense transactions",
                "accent": "red",
            },
            {
                "key": "total_salary_processed_month",
                "label": "Total Salary Processed",
                "value": float(total_salary),
                "display_value": DashboardService._format_currency(total_salary),
                "helper": "From payroll salary transactions",
                "accent": "emerald",
                "target_url": "/payroll",
            },
            {
                "key": "pending_payments",
                "label": "Pending Payments",
                "value": pending_payments,
                "display_value": str(pending_payments),
                "helper": "Employees without a generated payslip this month",
                "accent": "pink",
            },
        ]

        return {
            "cards": cards,
            "charts": {
                "working_hours": DashboardService._working_hours_analysis(active_employee_ids, recent_logs, today),
                "leave_usage": DashboardService._leave_usage_analysis(db, employee_ids=employee_ids, today=today),
                "attendance_trend": DashboardService._attendance_trend(
                    active_employee_ids,
                    trend_logs,
                    trend_recent_leaves,
                    today,
                    days=30,
                ),
            },
            "meta": {
                "upcoming_events_count": len(upcoming_events),
                "payroll_summary": payroll_summary,
            },
            "monthly_attendance_preview": monthly_report["items"][:5],
            "kpi_table_rows": [],
            "upcoming_events": upcoming_events,
        }
