from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.deps import AuthContext
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.attendance import AttendanceLog
from app.models.auth import User
from app.models.employee import Department, Employee
from app.models.enums import AttendanceStatus, LeaveRequestStatus
from app.models.leave import LeaveRequest
from app.models.payroll import PayrollRun, Payslip, SalaryStructure
from app.models.utility import Holiday
from app.services.bootstrap_service import bootstrap_reference_data
from app.services.dashboard_service import DashboardService
from app.services.permission_service import EffectiveAccess
from app.services.report_service import ReportService


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_almost_equal(actual: float, expected: float, message: str, tolerance: float = 0.01) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"{message}: expected {expected}, got {actual}")


def _active_salary_structure_count(
    *,
    structures: list[SalaryStructure],
    active_employee_ids: set[str],
    period_start: date,
    period_end: date,
) -> int:
    active_structures: dict[str, SalaryStructure] = {}
    ordered_rows = sorted(
        [item for item in structures if str(item.employee_id) in active_employee_ids and item.effective_from <= period_end],
        key=lambda item: (str(item.employee_id), item.effective_from),
        reverse=True,
    )
    for structure in ordered_rows:
        employee_id = str(structure.employee_id)
        if employee_id in active_structures:
            continue
        if structure.effective_to is None or structure.effective_to >= period_start:
            active_structures[employee_id] = structure
    return len(active_structures)


def _build_super_admin_auth(db) -> AuthContext:
    super_admin = db.execute(
        select(User)
        .options(joinedload(User.role), joinedload(User.employee_profile))
        .where(User.email == str(settings.initial_super_admin_email).lower())
    ).scalar_one()
    return AuthContext(
        user=super_admin,
        session=None,
        access=EffectiveAccess(permission_keys={"*"}, is_super_admin=True),
    )


def _metric_map(summary: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(card["key"]): card
        for card in summary["cards"]
    }


def main() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        bootstrap_reference_data(db)
        auth = _build_super_admin_auth(db)
        today = date.today()
        current_period_start = today.replace(day=1)
        current_period_end = DashboardService._shift_month(current_period_start, 1) - timedelta(days=1)

        employees = db.execute(
            select(Employee)
            .options(joinedload(Employee.user), joinedload(Employee.department))
            .where(Employee.is_deleted.is_(False))
        ).scalars().all()
        attendance_logs = db.execute(select(AttendanceLog)).scalars().all()
        leave_requests = db.execute(select(LeaveRequest)).scalars().all()
        payroll_runs = db.execute(select(PayrollRun)).scalars().all()
        payslips = db.execute(select(Payslip)).scalars().all()
        departments = db.execute(select(Department).where(Department.is_deleted.is_(False))).scalars().all()
        holidays = db.execute(select(Holiday)).scalars().all()
        salary_structures = db.execute(select(SalaryStructure)).scalars().all()

        require(len(employees) >= 5, "Seed must create at least 5 employees")
        require(len(attendance_logs) >= 5, "Seed must create at least 5 attendance rows")
        require(len(leave_requests) >= 5, "Seed must create at least 5 leave rows")
        require(len(payslips) >= 5, "Seed must create at least 5 payslips")
        require(len(departments) >= 5, "Seed must create at least 5 departments")
        require(len(holidays) >= 5, "Seed must create at least 5 meeting or event rows")
        require(all(employee.department_id is not None for employee in employees), "All seeded employees must be linked to a department")

        active_employees = [employee for employee in employees if employee.status == "active"]
        inactive_employees = [employee for employee in employees if employee.status != "active"]
        active_employee_ids = {str(employee.id) for employee in active_employees}

        today_logs = [
            log for log in attendance_logs
            if str(log.employee_id) in active_employee_ids and log.attendance_date == today
        ]
        present_ids = {
            str(log.employee_id)
            for log in today_logs
            if log.status in (AttendanceStatus.PRESENT.value, AttendanceStatus.HALF_DAY.value)
        }
        late_count = sum(1 for log in today_logs if log.is_late)

        leave_today = [
            row for row in leave_requests
            if row.status == LeaveRequestStatus.APPROVED.value
            and str(row.employee_id) in active_employee_ids
            and row.start_date <= today <= row.end_date
        ]
        leave_today_ids = {str(item.employee_id) for item in leave_today}
        absent_count = max(len(active_employees) - len(present_ids) - len(leave_today_ids), 0)
        attendance_percentage = round((len(present_ids) / len(active_employees)) * 100, 1) if active_employees else 0.0

        pending_leave_approvals = sum(1 for row in leave_requests if row.status == LeaveRequestStatus.PENDING.value)
        current_run = next(
            (row for row in payroll_runs if row.period_month == today.month and row.period_year == today.year),
            None,
        )
        current_payslips = [row for row in payslips if current_run is not None and row.payroll_run_id == current_run.id]
        current_payslip_employee_ids = {str(item.employee_id) for item in current_payslips}
        total_salary_expense = sum((Decimal(str(item.net_salary)) for item in current_payslips), Decimal("0"))
        payroll_pending_tasks = max(
            len(active_employees)
            - _active_salary_structure_count(
                structures=salary_structures,
                active_employee_ids=active_employee_ids,
                period_start=current_period_start,
                period_end=current_period_end,
            ),
            0,
        )
        pending_payments = max(len(active_employees) - len(current_payslip_employee_ids), 0)

        summary = DashboardService.summary(db, auth)
        cards = _metric_map(summary)

        require(cards["total_employees"]["value"] == len(employees), "Total employees card does not match seeded employee count")
        require(
            cards["total_employees"]["helper"] == f"Active {len(active_employees)} / Inactive {len(inactive_employees)}",
            "Active and inactive split is incorrect",
        )
        require_almost_equal(float(cards["today_attendance_pct"]["value"]), attendance_percentage, "Attendance percentage is incorrect")
        require(int(cards["late_comers_count"]["value"]) == late_count, "Late comers count is incorrect")
        require(int(cards["absent_count"]["value"]) == absent_count, "Absent count is incorrect")
        require(int(cards["employees_on_leave_today"]["value"]) == len(leave_today_ids), "Employees on leave count is incorrect")
        require(int(cards["pending_leave_approvals"]["value"]) == pending_leave_approvals, "Pending leave approvals count is incorrect")
        require(int(cards["payroll_pending_tasks"]["value"]) == payroll_pending_tasks, "Payroll pending tasks count is incorrect")
        require_almost_equal(
            float(cards["total_salary_expense_month"]["value"]),
            float(total_salary_expense),
            "Total salary expense is incorrect",
        )
        require(int(cards["pending_payments"]["value"]) == pending_payments, "Pending payments count is incorrect")
        require(summary["meta"]["upcoming_events_count"] == len(summary["upcoming_events"]), "Upcoming events count is inconsistent")

        require(len(summary["charts"]["working_hours"]["labels"]) == 7, "Working hours analysis must contain 7 labels")
        require(len(summary["charts"]["leave_usage"]["labels"]) == 6, "Leave usage chart must contain 6 monthly buckets")
        require(len(summary["charts"]["attendance_trend"]["labels"]) == 7, "Attendance trend must contain 7 labels")
        require(len(summary["kpi_table_rows"]) >= 5, "Dashboard KPI table must contain at least 5 rows")
        require(len(summary["upcoming_events"]) > 0, "Dashboard must expose upcoming meetings or events")

        monthly_report = ReportService.monthly_attendance_report(db, auth, month=today.month, year=today.year)
        require(monthly_report["total"] == len(employees), "Monthly attendance report row count must match seeded employees")

        print("Seed and dashboard validation passed.")
        print(f"Employees: {len(employees)} total | {len(active_employees)} active | {len(inactive_employees)} inactive")
        print(f"Departments: {len(departments)}")
        print(f"Attendance rows: {len(attendance_logs)}")
        print(f"Leave requests: {len(leave_requests)}")
        print(f"Payroll runs: {len(payroll_runs)} | Payslips: {len(payslips)}")
        print(f"Meetings / Events: {len(holidays)}")
        print(
            "Dashboard metrics: "
            f"attendance={attendance_percentage:.1f}% "
            f"late={late_count} "
            f"absent={absent_count} "
            f"leave_today={len(leave_today_ids)} "
            f"salary_expense={float(total_salary_expense):.2f} "
            f"pending_payments={pending_payments}"
        )


if __name__ == "__main__":
    main()
