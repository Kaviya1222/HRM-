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
from app.models.payroll import PayrollRun, Payslip, SalaryStructure
from app.models.utility import Holiday
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

        latest_logs: dict[tuple[str, date], AttendanceLog] = {}
        for log in logs:
            log_key = (str(log.employee_id), log.attendance_date)
            existing_log = latest_logs.get(log_key)
            if existing_log is None or (log.updated_at, log.created_at) >= (existing_log.updated_at, existing_log.created_at):
                latest_logs[log_key] = log
        return list(latest_logs.values())

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
            present_count = len(worked_logs)
            total_hours.append(round(total_minutes / 60, 2))
            average_hours.append(round((total_minutes / max(present_count, 1)) / 60, 2) if present_count else 0)

        return {
            "labels": labels,
            "total_hours": total_hours,
            "average_hours": average_hours,
            "employee_scope_count": len(active_employee_ids),
        }

    @staticmethod
    def _leave_usage_analysis(db: Session, *, active_employee_ids: list[str], today: date) -> dict[str, object]:
        month_starts = DashboardService._month_starts(today, 6)
        month_keys = [(item.year, item.month) for item in month_starts]
        labels = [item.strftime("%b %Y") for item in month_starts]
        month_totals = {key: 0 for key in month_keys}

        start_window = month_starts[0]
        end_window = DashboardService._shift_month(today.replace(day=1), 1) - timedelta(days=1)
        approved_leaves = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=active_employee_ids,
            start_date=start_window,
            end_date=end_window,
            status_value=LeaveRequestStatus.APPROVED.value,
        )
        leave_type_map = {
            str(item.id): item.name
            for item in db.execute(select(LeaveType)).scalars().all()
        }
        leave_type_totals: dict[str, int] = {}

        for leave_request in approved_leaves:
            effective_start = max(leave_request.start_date, start_window)
            effective_end = min(leave_request.end_date, end_window)
            for leave_day in DashboardService._daterange(effective_start, effective_end):
                month_key = (leave_day.year, leave_day.month)
                if month_key not in month_totals:
                    continue
                month_totals[month_key] += 1
                leave_type_key = str(leave_request.leave_type_id)
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
        approved_recent_leaves: list[LeaveRequest],
        today: date,
        *,
        days: int = 30,
    ) -> dict[str, object]:
        labels: list[str] = []
        present_series: list[int] = []
        leave_series: list[int] = []
        absent_series: list[int] = []

        logs_by_day: dict[date, list[AttendanceLog]] = {}
        for log in logs:
            logs_by_day.setdefault(log.attendance_date, []).append(log)

        leave_map: dict[date, set[str]] = {}
        for leave_request in approved_recent_leaves:
            for leave_day in DashboardService._daterange(leave_request.start_date, leave_request.end_date):
                if leave_day > today:
                    break
                leave_map.setdefault(leave_day, set()).add(str(leave_request.employee_id))

        start_date = today - timedelta(days=max(days - 1, 0))
        active_employee_set = set(active_employee_ids)
        for target_date in DashboardService._daterange(start_date, today):
            labels.append(target_date.strftime("%d %b"))
            day_logs = logs_by_day.get(target_date, [])
            present_ids = {
                str(log.employee_id)
                for log in day_logs
                if log.status in [AttendanceStatus.PRESENT.value, AttendanceStatus.HALF_DAY.value]
            }
            leave_ids = leave_map.get(target_date, set())
            absent_count = max(len(active_employee_set - present_ids - leave_ids), 0)
            present_series.append(len(present_ids))
            leave_series.append(len(leave_ids))
            absent_series.append(absent_count)

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
    def _kpi_table_rows(today: date) -> list[dict[str, object]]:
        next_day = today + timedelta(days=1)
        two_days_out = today + timedelta(days=2)

        return [
            {
                "scope_label": "Engineering",
                "total_employees": 184,
                "active_employees": 176,
                "inactive_employees": 8,
                "attendance_percentage": 94.9,
                "late_comers_count": 11,
                "absent_count": 3,
                "working_hours_display": "8.6 hrs avg",
                "leave_usage_display": "42 days",
                "pending_leave_approvals": 6,
                "payroll_pending_tasks": 5,
                "employees_on_leave_today": 6,
                "total_salary_expense_display": "INR 1.68 Cr",
                "pending_payments": 18,
                "meeting_event": f"{today.strftime('%d %b')}, 4:30 PM - Sprint review",
            },
            {
                "scope_label": "Product",
                "total_employees": 62,
                "active_employees": 59,
                "inactive_employees": 3,
                "attendance_percentage": 93.2,
                "late_comers_count": 4,
                "absent_count": 2,
                "working_hours_display": "8.2 hrs avg",
                "leave_usage_display": "15 days",
                "pending_leave_approvals": 2,
                "payroll_pending_tasks": 1,
                "employees_on_leave_today": 2,
                "total_salary_expense_display": "INR 58.20 L",
                "pending_payments": 5,
                "meeting_event": f"{today.strftime('%d %b')}, 11:00 AM - Roadmap sync",
            },
            {
                "scope_label": "Sales",
                "total_employees": 97,
                "active_employees": 91,
                "inactive_employees": 6,
                "attendance_percentage": 90.1,
                "late_comers_count": 9,
                "absent_count": 5,
                "working_hours_display": "7.9 hrs avg",
                "leave_usage_display": "21 days",
                "pending_leave_approvals": 3,
                "payroll_pending_tasks": 4,
                "employees_on_leave_today": 4,
                "total_salary_expense_display": "INR 74.80 L",
                "pending_payments": 11,
                "meeting_event": f"{today.strftime('%d %b')}, 3:00 PM - Regional pipeline review",
            },
            {
                "scope_label": "Human Resources",
                "total_employees": 54,
                "active_employees": 52,
                "inactive_employees": 2,
                "attendance_percentage": 94.2,
                "late_comers_count": 2,
                "absent_count": 2,
                "working_hours_display": "8.1 hrs avg",
                "leave_usage_display": "9 days",
                "pending_leave_approvals": 8,
                "payroll_pending_tasks": 2,
                "employees_on_leave_today": 1,
                "total_salary_expense_display": "INR 36.50 L",
                "pending_payments": 3,
                "meeting_event": f"{next_day.strftime('%d %b')}, 2:00 PM - Hiring calibration",
            },
            {
                "scope_label": "Finance",
                "total_employees": 51,
                "active_employees": 49,
                "inactive_employees": 2,
                "attendance_percentage": 93.9,
                "late_comers_count": 1,
                "absent_count": 2,
                "working_hours_display": "8.4 hrs avg",
                "leave_usage_display": "7 days",
                "pending_leave_approvals": 1,
                "payroll_pending_tasks": 7,
                "employees_on_leave_today": 1,
                "total_salary_expense_display": "INR 44.90 L",
                "pending_payments": 9,
                "meeting_event": f"{two_days_out.strftime('%d %b')}, 5:00 PM - Month-end close prep",
            },
            {
                "scope_label": "Operations",
                "total_employees": 73,
                "active_employees": 69,
                "inactive_employees": 4,
                "attendance_percentage": 89.9,
                "late_comers_count": 5,
                "absent_count": 4,
                "working_hours_display": "8.0 hrs avg",
                "leave_usage_display": "18 days",
                "pending_leave_approvals": 2,
                "payroll_pending_tasks": 3,
                "employees_on_leave_today": 3,
                "total_salary_expense_display": "INR 47.30 L",
                "pending_payments": 6,
                "meeting_event": f"{today.strftime('%d %b')}, 10:30 AM - Facilities audit standup",
            },
        ]

    @staticmethod
    def summary(db: Session, auth: AuthContext) -> dict[str, object]:
        scope_ids = DashboardService._scope(db, auth)
        employees = DashboardService._employees_for_scope(db, scope_ids)
        today = date.today()

        active_employees = [employee for employee in employees if employee.status == "active"]
        inactive_employees = [employee for employee in employees if employee.status != "active"]
        active_employee_ids = [str(item.id) for item in active_employees]
        total_employee_count = len(employees)
        active_count = len(active_employees)
        inactive_count = len(inactive_employees)

        today_logs = DashboardService._attendance_logs_in_range(db, employee_ids=active_employee_ids, start_date=today, end_date=today)
        present_log_ids = {
            str(log.employee_id)
            for log in today_logs
            if log.status == AttendanceStatus.PRESENT.value and not log.is_late
        }
        late_ids = {
            str(log.employee_id)
            for log in today_logs
            if log.status == AttendanceStatus.PRESENT.value and log.is_late
        }
        absent_ids = {
            str(log.employee_id)
            for log in today_logs
            if log.status == AttendanceStatus.ABSENT.value
        }
        half_day_ids = {
            str(log.employee_id)
            for log in today_logs
            if log.status == AttendanceStatus.HALF_DAY.value
        }
        late_comers_count = len(late_ids)

        leave_today_requests = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=active_employee_ids,
            start_date=today,
            end_date=today,
            status_value=LeaveRequestStatus.APPROVED.value,
        )
        leave_today_ids = {str(item.employee_id) for item in leave_today_requests}
        employees_on_leave_today = len(leave_today_ids)
        absent_count = len(absent_ids)
        half_day_count = len(half_day_ids)
        present_today_count = max(active_count - late_comers_count - absent_count - half_day_count, len(present_log_ids))
        attended_count = present_today_count + late_comers_count + half_day_count
        attendance_percentage = round((attended_count / active_count) * 100, 1) if active_count else 0.0

        pending_approvals = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=[str(item.id) for item in employees],
            status_value=LeaveRequestStatus.PENDING.value,
        )
        pending_leave_approvals = len(pending_approvals)

        current_period_start = today.replace(day=1)
        current_period_end = DashboardService._shift_month(current_period_start, 1) - timedelta(days=1)
        active_salary_structures = DashboardService._current_period_salary_structure_map(
            db,
            employee_ids=active_employee_ids,
            period_start=current_period_start,
            period_end=current_period_end,
        )
        payroll_pending_tasks = max(active_count - len(active_salary_structures), 0)

        current_payroll_run = db.execute(
            select(PayrollRun).where(PayrollRun.period_month == today.month, PayrollRun.period_year == today.year)
        ).scalar_one_or_none()
        current_payslips = db.execute(
            select(Payslip).where(Payslip.payroll_run_id == current_payroll_run.id)
        ).scalars().all() if current_payroll_run is not None else []
        current_payslip_employee_ids = {str(item.employee_id) for item in current_payslips}
        pending_payments = max(active_count - len(current_payslip_employee_ids), 0)
        total_salary_expense = sum((Decimal(str(item.net_salary)) for item in current_payslips), Decimal("0"))

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
        trend_approved_leaves = DashboardService._leave_requests_in_scope(
            db,
            employee_ids=active_employee_ids,
            start_date=trend_start_date,
            end_date=today,
            status_value=LeaveRequestStatus.APPROVED.value,
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
                "key": "payroll_pending_tasks",
                "label": "Payroll Pending Tasks",
                "value": payroll_pending_tasks,
                "display_value": str(payroll_pending_tasks),
                "helper": "Employees missing current salary setup",
                "accent": "cyan",
            },
            {
                "key": "total_salary_expense_month",
                "label": "Total Salary Expense (This Month)",
                "value": float(total_salary_expense),
                "display_value": DashboardService._format_currency(total_salary_expense),
                "helper": current_payroll_run.status.replace("_", " ").title() if current_payroll_run else "Current month payroll not processed",
                "accent": "emerald",
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
                "leave_usage": DashboardService._leave_usage_analysis(db, active_employee_ids=active_employee_ids, today=today),
                "attendance_trend": DashboardService._attendance_trend(
                    active_employee_ids,
                    trend_logs,
                    trend_approved_leaves,
                    today,
                    days=30,
                ),
            },
            "meta": {
                "upcoming_events_count": len(upcoming_events),
            },
            "monthly_attendance_preview": monthly_report["items"][:5],
            "kpi_table_rows": DashboardService._kpi_table_rows(today),
            "upcoming_events": upcoming_events,
        }
