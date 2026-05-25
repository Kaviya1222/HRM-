from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.attendance import AttendanceDailySummary
from app.models.auth import User
from app.models.employee import Department, Designation, Employee
from app.models.leave import LeaveRequest, LeaveType
from app.models.payroll import PayrollRun, Payslip
from app.services.attendance_service import AttendanceService
from app.services.leave_service import LeaveService
from app.services.permission_service import PermissionService
from app.services.user_scope_service import UserScopeService


class SearchService:
    @staticmethod
    def global_search(
        db: Session,
        auth: AuthContext,
        *,
        query: str,
        limit_per_module: int = 4,
    ) -> dict[str, object]:
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return {"query": normalized_query, "total_results": 0, "sections": []}

        limit_per_module = max(1, min(int(limit_per_module), 8))
        sections = [
            SearchService._search_employees(db, auth, normalized_query, limit_per_module),
            SearchService._search_attendance(db, auth, normalized_query, limit_per_module),
            SearchService._search_leave(db, auth, normalized_query, limit_per_module),
            SearchService._search_payroll(db, auth, normalized_query, limit_per_module),
        ]
        sections = [section for section in sections if section["items"]]

        return {
            "query": normalized_query,
            "total_results": sum(len(section["items"]) for section in sections),
            "sections": sections,
        }

    @staticmethod
    def _pattern(query: str) -> str:
        return f"%{query}%"

    @staticmethod
    def _format_date(value: date | None) -> str:
        if value is None:
            return "--"
        return value.strftime("%d %b %Y")

    @staticmethod
    def _format_minutes(minutes: int | None) -> str:
        if not minutes:
            return "0m"
        hours, remaining_minutes = divmod(int(minutes), 60)
        if hours == 0:
            return f"{remaining_minutes}m"
        if remaining_minutes == 0:
            return f"{hours}h"
        return f"{hours}h {remaining_minutes}m"

    @staticmethod
    def _format_currency(value: Decimal | float | int | None) -> str:
        amount = Decimal(str(value or 0))
        return f"INR {amount:,.2f}"

    @staticmethod
    def _empty_section(module: str, label: str, path: str) -> dict[str, object]:
        return {"module": module, "label": label, "path": path, "items": []}

    @staticmethod
    def _search_employees(db: Session, auth: AuthContext, query: str, limit_per_module: int) -> dict[str, object]:
        section = SearchService._empty_section("employees", "Employees", "/employees")
        if not PermissionService.has_permission_with_module(auth.access, "employees.view"):
            return section

        pattern = SearchService._pattern(query)
        stmt = (
            select(Employee)
            .join(User, Employee.user_id == User.id, isouter=True)
            .join(Department, Employee.department_id == Department.id, isouter=True)
            .join(Designation, Employee.designation_id == Designation.id, isouter=True)
            .options(joinedload(Employee.user), joinedload(Employee.department), joinedload(Employee.designation))
            .where(
                Employee.is_deleted.is_(False),
                or_(
                    Employee.employee_code.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    User.email.ilike(pattern),
                    Department.name.ilike(pattern),
                    Designation.name.ilike(pattern),
                ),
            )
            .order_by(User.first_name.asc(), User.last_name.asc(), Employee.employee_code.asc())
            .limit(limit_per_module)
        )

        employees = db.execute(stmt).unique().scalars().all()
        section["items"] = [
            {
                "id": str(employee.id),
                "module": "employees",
                "title": employee.user.full_name if employee.user else employee.employee_code,
                "subtitle": " | ".join(
                    part
                    for part in [
                        employee.employee_code,
                        employee.department.name if employee.department else None,
                        employee.designation.name if employee.designation else None,
                    ]
                    if part
                ),
                "description": employee.user.email if employee.user else None,
                "path": "/employees",
            }
            for employee in employees
        ]
        return section

    @staticmethod
    def _search_attendance(db: Session, auth: AuthContext, query: str, limit_per_module: int) -> dict[str, object]:
        section = SearchService._empty_section("attendance", "Attendance", "/attendance")
        if not PermissionService.has_any_permission_with_module(
            auth.access,
            ("attendance.view.own", "attendance.view.team", "attendance.view.all"),
        ):
            return section

        scope_ids = AttendanceService._attendance_scope(db, auth)
        if scope_ids is not None and not scope_ids:
            return section

        pattern = SearchService._pattern(query)
        stmt = (
            select(AttendanceDailySummary, Employee, User)
            .join(Employee, AttendanceDailySummary.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id, isouter=True)
            .where(
                Employee.is_deleted.is_(False),
                or_(
                    Employee.employee_code.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    AttendanceDailySummary.status.ilike(pattern),
                    cast(AttendanceDailySummary.summary_date, String).ilike(pattern),
                ),
            )
            .order_by(AttendanceDailySummary.summary_date.desc(), User.first_name.asc(), User.last_name.asc())
            .limit(limit_per_module)
        )
        if scope_ids is not None:
            stmt = stmt.where(AttendanceDailySummary.employee_id.in_(scope_ids))

        rows = db.execute(stmt).all()
        items: list[dict[str, object]] = []
        for summary, employee, user in rows:
            items.append(
                {
                    "id": str(summary.id),
                    "module": "attendance",
                    "title": user.full_name if user else employee.employee_code,
                    "subtitle": f"{SearchService._format_date(summary.summary_date)} | {str(summary.status).replace('_', ' ').title()}",
                    "description": f"{employee.employee_code} | {SearchService._format_minutes(summary.work_minutes)} worked",
                    "path": "/attendance",
                }
            )

        section["items"] = items
        return section

    @staticmethod
    def _search_leave(db: Session, auth: AuthContext, query: str, limit_per_module: int) -> dict[str, object]:
        section = SearchService._empty_section("leave", "Leave", "/leave")
        if not PermissionService.has_any_permission_with_module(
            auth.access,
            ("leave.view.own", "leave.view.team", "leave.view.all", "leave.approve", "leave.recommend"),
        ):
            return section

        scope_ids = LeaveService._scope(db, auth)
        if scope_ids is not None and not scope_ids:
            return section

        pattern = SearchService._pattern(query)
        stmt = (
            select(LeaveRequest, Employee, User, LeaveType)
            .join(Employee, LeaveRequest.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id, isouter=True)
            .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
            .where(
                Employee.is_deleted.is_(False),
                or_(
                    Employee.employee_code.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    LeaveType.name.ilike(pattern),
                    LeaveRequest.status.ilike(pattern),
                    LeaveRequest.reason.ilike(pattern),
                    cast(LeaveRequest.start_date, String).ilike(pattern),
                    cast(LeaveRequest.end_date, String).ilike(pattern),
                ),
            )
            .order_by(LeaveRequest.requested_at.desc())
            .limit(limit_per_module)
        )
        if scope_ids is not None:
            stmt = stmt.where(LeaveRequest.employee_id.in_(scope_ids))

        rows = db.execute(stmt).all()
        items: list[dict[str, object]] = []
        for request, employee, user, leave_type in rows:
            items.append(
                {
                    "id": str(request.id),
                    "module": "leave",
                    "title": user.full_name if user else employee.employee_code,
                    "subtitle": f"{leave_type.name} | {str(request.status).replace('_', ' ').title()}",
                    "description": f"{SearchService._format_date(request.start_date)} - {SearchService._format_date(request.end_date)}",
                    "path": "/leave",
                }
            )

        section["items"] = items
        return section

    @staticmethod
    def _search_payroll(db: Session, auth: AuthContext, query: str, limit_per_module: int) -> dict[str, object]:
        section = SearchService._empty_section("payroll", "Payroll", "/payroll")
        if not PermissionService.has_any_permission_with_module(
            auth.access,
            ("payroll.view.own", "payroll.view.all", "payroll.manage"),
        ):
            return section

        pattern = SearchService._pattern(query)
        stmt = (
            select(Payslip, Employee, User, PayrollRun)
            .join(Employee, Payslip.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id, isouter=True)
            .join(PayrollRun, Payslip.payroll_run_id == PayrollRun.id)
            .where(
                Employee.is_deleted.is_(False),
                or_(
                    Employee.employee_code.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    cast(PayrollRun.period_month, String).ilike(pattern),
                    cast(PayrollRun.period_year, String).ilike(pattern),
                    cast(Payslip.net_salary, String).ilike(pattern),
                ),
            )
            .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc(), Payslip.created_at.desc())
            .limit(limit_per_module)
        )

        if not auth.access.is_super_admin and "payroll.view.all" not in auth.access.permission_keys and "payroll.manage" not in auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None:
                return section
            stmt = stmt.where(Payslip.employee_id == employee.id)

        rows = db.execute(stmt).all()
        items: list[dict[str, object]] = []
        for payslip, employee, user, payroll_run in rows:
            items.append(
                {
                    "id": str(payslip.id),
                    "module": "payroll",
                    "title": user.full_name if user else employee.employee_code,
                    "subtitle": f"Payroll | {date(payroll_run.period_year, payroll_run.period_month, 1).strftime('%b %Y')}",
                    "description": f"{employee.employee_code} | Net {SearchService._format_currency(payslip.net_salary)}",
                    "path": "/payroll",
                }
            )

        section["items"] = items
        return section
