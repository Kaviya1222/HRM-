from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.attendance import AttendanceDailySummary, AttendanceLog
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, EmployeeStatus, LeaveRequestStatus, PayrollRunStatus
from app.models.leave import LeaveRequest
from app.models.payroll import PayrollRun, PayrollTransaction, Payslip, SalaryStructure
from app.models.utility import Holiday
from app.services.notification_service import NotificationService
from app.services.user_scope_service import UserScopeService


class PayrollService:
    TRANSACTION_TYPES = {"income", "expense", "salary", "amount"}

    @staticmethod
    def _transaction_scope(stmt, auth: AuthContext):
        if auth.access.is_super_admin or {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            return stmt
        employee = UserScopeService.current_employee(auth)
        if employee is None:
            return stmt.where(PayrollTransaction.employee_id.is_(None), PayrollTransaction.id.is_(None))
        return stmt.where(PayrollTransaction.employee_id == employee.id)

    @staticmethod
    def _serialize_transaction(transaction: PayrollTransaction, employee_map: dict[str, Employee]) -> dict[str, object]:
        employee = employee_map.get(str(transaction.employee_id)) if transaction.employee_id else None
        return {
            "id": transaction.id,
            "transaction_type": transaction.transaction_type,
            "amount": transaction.amount,
            "employee_id": transaction.employee_id,
            "employee_name": employee.user.full_name if employee and employee.user else None,
            "employee_code": employee.employee_code if employee else None,
            "transaction_date": transaction.transaction_date,
            "description": transaction.description,
            "created_at": transaction.created_at,
        }

    @staticmethod
    def _calculate_summary(transactions: list[PayrollTransaction]) -> dict[str, Decimal]:
        total_income = Decimal("0")
        total_expense = Decimal("0")
        total_salary = Decimal("0")

        for transaction in transactions:
            amount = Decimal(str(transaction.amount or 0))
            if transaction.transaction_type in {"income", "amount"}:
                total_income += amount
            elif transaction.transaction_type == "expense":
                total_expense += amount
            elif transaction.transaction_type == "salary":
                total_salary += amount

        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "total_salary": total_salary,
            "total_amount": total_income - total_expense - total_salary,
        }

    @staticmethod
    def get_transaction_summary(db: Session, auth: AuthContext) -> dict[str, object]:
        stmt = PayrollService._transaction_scope(select(PayrollTransaction), auth)
        transactions = db.execute(stmt).scalars().all()
        return PayrollService._calculate_summary(transactions)

    @staticmethod
    def list_transactions(db: Session, auth: AuthContext) -> dict[str, object]:
        stmt = PayrollService._transaction_scope(
            select(PayrollTransaction).order_by(PayrollTransaction.transaction_date.desc(), PayrollTransaction.created_at.desc()),
            auth,
        )
        transactions = db.execute(stmt).scalars().all()
        employee_ids = {str(item.employee_id) for item in transactions if item.employee_id}
        employees = db.execute(select(Employee).options(joinedload(Employee.user)).where(Employee.id.in_(employee_ids))).scalars().all() if employee_ids else []
        employee_map = {str(item.id): item for item in employees}
        items = [PayrollService._serialize_transaction(item, employee_map) for item in transactions]
        return {"items": items, "total": len(items), "summary": PayrollService._calculate_summary(transactions)}

    @staticmethod
    def add_transaction(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        transaction_type = str(payload["transaction_type"]).lower()
        if transaction_type not in PayrollService.TRANSACTION_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payroll transaction type")

        amount = Decimal(str(payload["amount"])).quantize(Decimal("0.01"))
        if amount <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")

        employee_id = payload.get("employee_id")
        if transaction_type == "salary" and not employee_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee selection is required for salary transactions")

        employee = None
        if employee_id:
            employee = db.execute(
                select(Employee)
                .options(joinedload(Employee.user))
                .where(
                    Employee.id == employee_id,
                    Employee.is_deleted.is_(False),
                    Employee.status == EmployeeStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()
            if employee is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active employee not found")

        transaction = PayrollTransaction(
            transaction_type=transaction_type,
            amount=amount,
            employee_id=str(employee_id) if employee_id else None,
            transaction_date=payload["transaction_date"],
            description=(payload.get("description") or None),
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        employee_map = {str(employee.id): employee} if employee else {}
        return {
            "transaction": PayrollService._serialize_transaction(transaction, employee_map),
            "summary": PayrollService.get_transaction_summary(db, auth),
        }

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
            if current.weekday() >= 5:
                continue
            if current in holidays:
                continue
            dates.append(current)
        return dates

    @staticmethod
    def _sum_components(values: dict[str, float] | None) -> Decimal:
        total = Decimal("0")
        for value in (values or {}).values():
            total += Decimal(str(value))
        return total

    @staticmethod
    def _resolve_salary_structure(db: Session, employee: Employee, month: int, year: int) -> SalaryStructure | None:
        period_end = date(year, month, calendar.monthrange(year, month)[1])
        structures = db.execute(
            select(SalaryStructure)
            .where(
                SalaryStructure.employee_id == employee.id,
                SalaryStructure.effective_from <= period_end,
            )
            .order_by(SalaryStructure.effective_from.desc())
        ).scalars().all()
        for item in structures:
            if item.effective_to is None or item.effective_to >= date(year, month, 1):
                return item
        return None

    @staticmethod
    def _status_for_day(
        db: Session,
        *,
        employee_id: str,
        target_date: date,
    ) -> str:
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

        log = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date == target_date,
            )
        ).scalar_one_or_none()
        if log is not None:
            return log.status
        return AttendanceStatus.ABSENT.value

    @staticmethod
    def _paid_units_for_month(db: Session, *, employee_id: str, month: int, year: int) -> tuple[Decimal, dict[str, int]]:
        working_dates = PayrollService._working_dates(db, month, year)
        paid_units = Decimal("0")
        counters = {
            "present_days": 0,
            "half_days": 0,
            "leave_days": 0,
            "absent_days": 0,
            "working_days": len(working_dates),
        }
        for target_date in working_dates:
            status_value = PayrollService._status_for_day(db, employee_id=employee_id, target_date=target_date)
            if status_value == AttendanceStatus.PRESENT.value:
                paid_units += Decimal("1")
                counters["present_days"] += 1
            elif status_value == AttendanceStatus.HALF_DAY.value:
                paid_units += Decimal("0.5")
                counters["half_days"] += 1
            elif status_value == AttendanceStatus.LEAVE.value:
                paid_units += Decimal("1")
                counters["leave_days"] += 1
            else:
                counters["absent_days"] += 1
        return paid_units, counters

    @staticmethod
    def serialize_salary_structure(structure: SalaryStructure, employee_map: dict[str, Employee]) -> dict[str, object]:
        employee = employee_map.get(str(structure.employee_id)) if structure.employee_id else None
        return {
            "id": structure.id,
            "employee_id": structure.employee_id,
            "employee_name": employee.user.full_name if employee and employee.user else None,
            "employee_code": employee.employee_code if employee else None,
            "grade_name": structure.grade_name,
            "basic_salary": structure.basic_salary,
            "allowances": structure.allowances or {},
            "deductions": structure.deductions or {},
            "effective_from": structure.effective_from,
            "effective_to": structure.effective_to,
        }

    @staticmethod
    def serialize_payslip(payslip: Payslip, employee_map: dict[str, Employee], run_map: dict[str, PayrollRun]) -> dict[str, object]:
        employee = employee_map.get(str(payslip.employee_id))
        payroll_run = run_map.get(str(payslip.payroll_run_id))
        return {
            "id": payslip.id,
            "payroll_run_id": payslip.payroll_run_id,
            "employee_id": payslip.employee_id,
            "employee_name": employee.user.full_name if employee and employee.user else None,
            "employee_code": employee.employee_code if employee else None,
            "period_month": payroll_run.period_month if payroll_run else None,
            "period_year": payroll_run.period_year if payroll_run else None,
            "gross_salary": payslip.gross_salary,
            "deduction_amount": payslip.deduction_amount,
            "net_salary": payslip.net_salary,
            "paid_days": payslip.paid_days,
            "attendance_summary": payslip.attendance_summary or {},
            "created_at": payslip.created_at,
        }

    @staticmethod
    def get_meta(db: Session, auth: AuthContext) -> dict[str, object]:
        employees_stmt = (
            select(Employee)
            .options(joinedload(Employee.user))
            .where(Employee.is_deleted.is_(False), Employee.status == EmployeeStatus.ACTIVE.value)
            .order_by(Employee.employee_code.asc())
        )
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            employees_stmt = employees_stmt.where(Employee.id == (employee.id if employee else None))
        employees = db.execute(employees_stmt).scalars().all()
        return {
            "employees": [
                {
                    "id": employee.id,
                    "employee_code": employee.employee_code,
                    "full_name": employee.user.full_name if employee.user else employee.employee_code,
                }
                for employee in employees
            ]
        }

    @staticmethod
    def list_salary_structures(db: Session, auth: AuthContext) -> dict[str, object]:
        stmt = select(SalaryStructure).order_by(SalaryStructure.effective_from.desc())
        employee = UserScopeService.current_employee(auth)
        if not auth.access.is_super_admin and "payroll.manage" not in auth.access.permission_keys and "payroll.view.all" not in auth.access.permission_keys:
            stmt = stmt.where(SalaryStructure.employee_id == (employee.id if employee else None))
        structures = db.execute(stmt).scalars().all()
        employee_ids = {str(item.employee_id) for item in structures if item.employee_id}
        employees = db.execute(select(Employee).options(joinedload(Employee.user)).where(Employee.id.in_(employee_ids))).scalars().all() if employee_ids else []
        employee_map = {str(item.id): item for item in employees}
        items = [PayrollService.serialize_salary_structure(item, employee_map) for item in structures]
        return {"items": items, "total": len(items)}

    @staticmethod
    def upsert_salary_structure(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        employee_id = payload.get("employee_id")
        existing = None
        if employee_id:
            existing = db.execute(
                select(SalaryStructure).where(
                    SalaryStructure.employee_id == employee_id,
                    SalaryStructure.effective_from == payload["effective_from"],
                )
            ).scalar_one_or_none()

        structure = existing or SalaryStructure()
        structure.employee_id = employee_id
        structure.grade_name = payload.get("grade_name")
        structure.basic_salary = Decimal(str(payload["basic_salary"]))
        structure.allowances = payload.get("allowances") or {}
        structure.deductions = payload.get("deductions") or {}
        structure.effective_from = payload["effective_from"]
        structure.effective_to = payload.get("effective_to")
        db.add(structure)
        db.commit()
        db.refresh(structure)
        employee_map: dict[str, Employee] = {}
        if structure.employee_id:
            employee = db.execute(select(Employee).options(joinedload(Employee.user)).where(Employee.id == structure.employee_id)).scalar_one()
            employee_map[str(employee.id)] = employee
        return PayrollService.serialize_salary_structure(structure, employee_map)

    @staticmethod
    def run_payroll(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        month = int(payload["period_month"])
        year = int(payload["period_year"])
        employee_id = payload.get("employee_id")

        payroll_run = db.execute(select(PayrollRun).where(PayrollRun.period_month == month, PayrollRun.period_year == year)).scalar_one_or_none()
        if payroll_run and payroll_run.status == PayrollRunStatus.COMPLETED.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll is already completed for this period")
        if payroll_run is None:
            payroll_run = PayrollRun(period_month=month, period_year=year, status=PayrollRunStatus.PROCESSING.value, initiated_by_user_id=auth.user.id)
            db.add(payroll_run)
            db.flush()
        else:
            payroll_run.status = PayrollRunStatus.PROCESSING.value

        employee_stmt = select(Employee).options(joinedload(Employee.user)).where(Employee.is_deleted.is_(False), Employee.status == "active")
        if employee_id:
            employee_stmt = employee_stmt.where(Employee.id == employee_id)
        employees = db.execute(employee_stmt).scalars().all()
        run_results: list[dict[str, object]] = []

        for employee in employees:
            structure = PayrollService._resolve_salary_structure(db, employee, month, year)
            basic_salary = Decimal(str(structure.basic_salary if structure else (employee.base_salary or 0)))
            allowances = structure.allowances if structure else {}
            deductions = structure.deductions if structure else {}
            gross_reference = basic_salary + PayrollService._sum_components(allowances)
            deduction_amount = PayrollService._sum_components(deductions)

            paid_units, counters = PayrollService._paid_units_for_month(db, employee_id=str(employee.id), month=month, year=year)
            working_days = max(counters["working_days"], 1)
            gross_salary = (gross_reference * paid_units / Decimal(str(working_days))).quantize(Decimal("0.01"))
            net_salary = (gross_salary - deduction_amount).quantize(Decimal("0.01"))

            payslip = db.execute(
                select(Payslip).where(Payslip.payroll_run_id == payroll_run.id, Payslip.employee_id == employee.id)
            ).scalar_one_or_none()
            if payslip is None:
                payslip = Payslip(payroll_run_id=payroll_run.id, employee_id=employee.id)
                db.add(payslip)

            payslip.gross_salary = gross_salary
            payslip.deduction_amount = deduction_amount
            payslip.net_salary = net_salary
            payslip.paid_days = paid_units
            payslip.attendance_summary = counters

            if employee.user_id:
                NotificationService.create_user_notification(
                    db,
                    user_id=employee.user_id,
                    title="Payslip generated",
                    message=f"Your payslip for {month:02d}/{year} is now available.",
                    notification_type="payroll",
                    metadata_json={"period_month": month, "period_year": year},
                    employee_id=employee.id,
                    related_id=payslip.id,
                    target_url="/payroll",
                )

        payroll_run.status = PayrollRunStatus.COMPLETED.value
        payroll_run.processed_at = datetime.now(UTC)
        db.commit()

        run_results = PayrollService.list_payslips(db, auth, payroll_run_id=str(payroll_run.id))["items"]
        return {
            "message": "Payroll run completed successfully",
            "payroll_run_id": payroll_run.id,
            "payslips": run_results,
        }

    @staticmethod
    def list_runs(db: Session) -> dict[str, object]:
        runs = db.execute(select(PayrollRun).order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())).scalars().all()
        items = [
            {
                "id": run.id,
                "period_month": run.period_month,
                "period_year": run.period_year,
                "status": run.status,
                "processed_at": run.processed_at or run.updated_at,
            }
            for run in runs
        ]
        return {"items": items, "total": len(items)}

    @staticmethod
    def list_payslips(
        db: Session,
        auth: AuthContext,
        *,
        payroll_run_id: str | None = None,
    ) -> dict[str, object]:
        stmt = select(Payslip).order_by(Payslip.created_at.desc())
        if payroll_run_id:
            stmt = stmt.where(Payslip.payroll_run_id == payroll_run_id)

        if not auth.access.is_super_admin and "payroll.view.all" not in auth.access.permission_keys and "payroll.manage" not in auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None:
                return {"items": [], "total": 0}
            stmt = stmt.where(Payslip.employee_id == employee.id)

        payslips = db.execute(stmt).scalars().all()
        employee_ids = {str(item.employee_id) for item in payslips}
        run_ids = {str(item.payroll_run_id) for item in payslips}
        employees = db.execute(select(Employee).options(joinedload(Employee.user)).where(Employee.id.in_(employee_ids))).scalars().all() if employee_ids else []
        runs = db.execute(select(PayrollRun).where(PayrollRun.id.in_(run_ids))).scalars().all() if run_ids else []
        employee_map = {str(item.id): item for item in employees}
        run_map = {str(item.id): item for item in runs}
        items = [PayrollService.serialize_payslip(item, employee_map, run_map) for item in payslips]
        return {"items": items, "total": len(items)}

    @staticmethod
    def render_payslip_text(db: Session, auth: AuthContext, payslip_id: str) -> str:
        payslip = db.get(Payslip, payslip_id)
        if payslip is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
        if not auth.access.is_super_admin and "payroll.view.all" not in auth.access.permission_keys and "payroll.manage" not in auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None or str(employee.id) != str(payslip.employee_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this payslip")

        employee = db.execute(select(Employee).options(joinedload(Employee.user)).where(Employee.id == payslip.employee_id)).scalar_one()
        payroll_run = db.get(PayrollRun, payslip.payroll_run_id)
        lines = [
            "HRM Payslip",
            f"Employee: {employee.user.full_name if employee.user else employee.employee_code}",
            f"Employee Code: {employee.employee_code}",
            f"Period: {payroll_run.period_month:02d}/{payroll_run.period_year}" if payroll_run else "Period: N/A",
            f"Gross Salary: {payslip.gross_salary}",
            f"Deductions: {payslip.deduction_amount}",
            f"Net Salary: {payslip.net_salary}",
            f"Paid Days: {payslip.paid_days}",
            "",
            "Attendance Summary:",
        ]
        for key, value in (payslip.attendance_summary or {}).items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)
