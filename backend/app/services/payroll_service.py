from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.attendance import AttendanceDailySummary, AttendanceLog
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, EmployeeStatus, LeaveRequestStatus, PayrollRunStatus
from app.models.leave import LeaveRequest
from app.models.payroll import PayrollRun, PayrollTransaction, Payslip, SalaryProfile, SalaryStructure
from app.models.utility import Holiday
from app.services.notification_service import NotificationService
from app.services.user_scope_service import UserScopeService


class PayrollService:
    TRANSACTION_TYPES = {"income", "expense", "salary", "amount"}
    MONEY = Decimal("0.01")

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
            "employee_name": transaction.employee_name or (employee.user.full_name if employee and employee.user else None),
            "employee_code": employee.employee_code if employee else None,
            "payroll_month": transaction.payroll_month,
            "payroll_year": transaction.payroll_year,
            "transaction_date": transaction.transaction_date,
            "description": transaction.description,
            "created_at": transaction.created_at,
            "updated_at": transaction.updated_at,
        }

    @staticmethod
    def _clean_text(value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _get_active_employee(db: Session, employee_id: str) -> Employee:
        employee = db.execute(
            select(Employee)
            .options(joinedload(Employee.user), joinedload(Employee.department), joinedload(Employee.designation))
            .where(
                Employee.id == employee_id,
                Employee.is_deleted.is_(False),
                Employee.status == EmployeeStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active employee not found")
        return employee

    @staticmethod
    def _transaction_period(transaction: PayrollTransaction) -> tuple[int | None, int | None]:
        if transaction.payroll_month and transaction.payroll_year:
            return int(transaction.payroll_month), int(transaction.payroll_year)
        if transaction.transaction_date:
            return transaction.transaction_date.month, transaction.transaction_date.year
        return None, None

    @staticmethod
    def _dedupe_salary_transactions(transactions: list[PayrollTransaction]) -> list[PayrollTransaction]:
        deduped_salary: dict[tuple[str, int, int], PayrollTransaction] = {}
        visible_transactions: list[PayrollTransaction] = []

        for transaction in transactions:
            if transaction.transaction_type != "salary" or not transaction.employee_id:
                visible_transactions.append(transaction)
                continue

            payroll_month, payroll_year = PayrollService._transaction_period(transaction)
            if not payroll_month or not payroll_year:
                visible_transactions.append(transaction)
                continue

            key = (str(transaction.employee_id), payroll_month, payroll_year)
            existing = deduped_salary.get(key)
            if existing is None or (transaction.updated_at, transaction.created_at) > (existing.updated_at, existing.created_at):
                deduped_salary[key] = transaction

        visible_transactions.extend(deduped_salary.values())
        visible_transactions.sort(key=lambda item: (item.transaction_date, item.created_at), reverse=True)
        return visible_transactions

    @staticmethod
    def _salary_transaction_exists(db: Session, *, employee_id: str, month: int, year: int, exclude_id: str | None = None) -> bool:
        stmt = select(PayrollTransaction.id).where(
            PayrollTransaction.transaction_type == "salary",
            PayrollTransaction.employee_id == employee_id,
            PayrollTransaction.payroll_month == month,
            PayrollTransaction.payroll_year == year,
        )
        if exclude_id:
            stmt = stmt.where(PayrollTransaction.id != exclude_id)
        return db.execute(stmt).first() is not None

    @staticmethod
    def _apply_salary_period(transaction: PayrollTransaction) -> None:
        if transaction.transaction_type == "salary" and transaction.transaction_date:
            transaction.payroll_month = transaction.transaction_date.month
            transaction.payroll_year = transaction.transaction_date.year
            return
        transaction.payroll_month = None
        transaction.payroll_year = None

    @staticmethod
    def _calculate_summary(transactions: list[PayrollTransaction]) -> dict[str, Decimal]:
        total_income = Decimal("0")
        total_expense = Decimal("0")
        total_salary = Decimal("0")

        for transaction in PayrollService._dedupe_salary_transactions(transactions):
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
    def _filter_transactions_for_period(transactions: list[PayrollTransaction], month: int, year: int) -> list[PayrollTransaction]:
        return [
            transaction
            for transaction in transactions
            if PayrollService._transaction_period(transaction) == (month, year)
        ]

    @staticmethod
    def get_transaction_summary(db: Session, auth: AuthContext, *, month: int | None = None, year: int | None = None) -> dict[str, object]:
        today = date.today()
        period_month = month or today.month
        period_year = year or today.year
        stmt = PayrollService._transaction_scope(select(PayrollTransaction), auth)
        transactions = PayrollService._filter_transactions_for_period(
            PayrollService._dedupe_salary_transactions(db.execute(stmt).scalars().all()),
            period_month,
            period_year,
        )
        return PayrollService._calculate_summary(transactions)

    @staticmethod
    def dashboard_summary(
        db: Session,
        auth: AuthContext,
        *,
        employee_ids: list[str] | None = None,
        month: int | None = None,
        year: int | None = None,
    ) -> dict[str, object]:
        today = date.today()
        period_month = month or today.month
        period_year = year or today.year
        stmt = PayrollService._transaction_scope(select(PayrollTransaction), auth)
        if employee_ids is not None:
            employee_id_set = [str(employee_id) for employee_id in employee_ids]
            stmt = stmt.where(
                (PayrollTransaction.employee_id.in_(employee_id_set))
                | (PayrollTransaction.employee_id.is_(None))
            )
        transactions = PayrollService._dedupe_salary_transactions(db.execute(stmt).scalars().all())
        period_transactions = PayrollService._filter_transactions_for_period(transactions, period_month, period_year)
        summary = PayrollService._calculate_summary(period_transactions)
        salary_employee_ids = {
            str(transaction.employee_id)
            for transaction in period_transactions
            if transaction.transaction_type == "salary"
            and transaction.employee_id
        }

        if employee_ids is None:
            employee_stmt = select(Employee).where(
                Employee.is_deleted.is_(False),
                Employee.status == EmployeeStatus.ACTIVE.value,
            )
            if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
                employee = UserScopeService.current_employee(auth)
                if employee is None:
                    return PayrollService._empty_dashboard_summary(period_month, period_year)
                employee_stmt = employee_stmt.where(Employee.id == employee.id)
            employees = db.execute(employee_stmt).scalars().all()
            active_employee_ids = [str(employee.id) for employee in employees]
        else:
            active_employee_ids = [str(employee_id) for employee_id in employee_ids]

        active_count = len(active_employee_ids)
        employees_without_salary_transaction = max(active_count - len(salary_employee_ids), 0)
        payroll_status = "updated" if period_transactions else PayrollRunStatus.DRAFT.value

        return {
            "period_month": period_month,
            "period_year": period_year,
            "active_employee_count": active_count,
            "total_income": summary["total_income"],
            "total_expense": summary["total_expense"],
            "total_salary": summary["total_salary"],
            "total_amount": summary["total_amount"],
            "employees_with_salary_setup": len(salary_employee_ids),
            "employees_missing_salary_setup": employees_without_salary_transaction,
            "employees_with_payslip": len(salary_employee_ids),
            "pending_payslips": employees_without_salary_transaction,
            "payroll_pending_tasks": employees_without_salary_transaction,
            "total_salary_processed": summary["total_salary"],
            "current_month_payroll_status": payroll_status,
            "current_month_payroll_status_label": payroll_status.replace("_", " ").title(),
            "payroll_run_id": None,
            "processed_at": max((transaction.updated_at for transaction in period_transactions), default=None),
        }

    @staticmethod
    def _empty_dashboard_summary(period_month: int, period_year: int) -> dict[str, object]:
        return {
            "period_month": period_month,
            "period_year": period_year,
            "active_employee_count": 0,
            "total_income": Decimal("0"),
            "total_expense": Decimal("0"),
            "total_salary": Decimal("0"),
            "total_amount": Decimal("0"),
            "employees_with_salary_setup": 0,
            "employees_missing_salary_setup": 0,
            "employees_with_payslip": 0,
            "pending_payslips": 0,
            "payroll_pending_tasks": 0,
            "total_salary_processed": Decimal("0"),
            "current_month_payroll_status": PayrollRunStatus.DRAFT.value,
            "current_month_payroll_status_label": "Draft",
            "payroll_run_id": None,
            "processed_at": None,
        }

    @staticmethod
    def list_transactions(db: Session, auth: AuthContext) -> dict[str, object]:
        stmt = PayrollService._transaction_scope(
            select(PayrollTransaction).order_by(PayrollTransaction.transaction_date.desc(), PayrollTransaction.created_at.desc()),
            auth,
        )
        transactions = PayrollService._dedupe_salary_transactions(db.execute(stmt).scalars().all())
        employee_ids = {str(item.employee_id) for item in transactions if item.employee_id}
        employees = db.execute(select(Employee).options(joinedload(Employee.user)).where(Employee.id.in_(employee_ids))).scalars().all() if employee_ids else []
        employee_map = {str(item.id): item for item in employees}
        items = [PayrollService._serialize_transaction(item, employee_map) for item in transactions]
        return {"items": items, "total": len(items), "summary": PayrollService.get_transaction_summary(db, auth)}

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

        transaction_date = payload["transaction_date"]
        if transaction_type == "salary" and PayrollService._salary_transaction_exists(
            db,
            employee_id=str(employee_id),
            month=transaction_date.month,
            year=transaction_date.year,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Salary already generated for this employee for this month.",
            )

        transaction = PayrollTransaction(
            transaction_type=transaction_type,
            amount=amount,
            employee_id=str(employee_id) if employee_id else None,
            employee_name=employee.user.full_name if employee and employee.user else None,
            transaction_date=transaction_date,
            description=(payload.get("description") or None),
        )
        PayrollService._apply_salary_period(transaction)
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        employee_map = {str(employee.id): employee} if employee else {}
        return {
            "transaction": PayrollService._serialize_transaction(transaction, employee_map),
            "summary": PayrollService.get_transaction_summary(db, auth),
        }

    @staticmethod
    def update_transaction(db: Session, auth: AuthContext, transaction_id: str, payload: dict[str, object]) -> dict[str, object]:
        transaction = db.get(PayrollTransaction, transaction_id)
        if transaction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll transaction not found")
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None or str(transaction.employee_id) != str(employee.id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this payroll transaction")

        transaction_type = str(payload.get("transaction_type") or transaction.transaction_type).lower()
        if transaction_type not in PayrollService.TRANSACTION_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payroll transaction type")

        employee_id = payload.get("employee_id") if "employee_id" in payload else transaction.employee_id
        employee = None
        if transaction_type == "salary" and not employee_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee selection is required for salary transactions")
        if transaction_type != "salary":
            employee_id = None
        if employee_id:
            employee = PayrollService._get_active_employee(db, str(employee_id))

        if "amount" in payload and payload.get("amount") is not None:
            amount = Decimal(str(payload["amount"])).quantize(Decimal("0.01"))
            if amount <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")
            transaction.amount = amount
        if "transaction_date" in payload and payload.get("transaction_date") is not None:
            transaction.transaction_date = payload["transaction_date"]
        if "description" in payload:
            transaction.description = payload.get("description") or None
        transaction.transaction_type = transaction_type
        transaction.employee_id = str(employee_id) if employee_id else None
        transaction.employee_name = employee.user.full_name if employee and employee.user else None
        PayrollService._apply_salary_period(transaction)
        if transaction.transaction_type == "salary" and PayrollService._salary_transaction_exists(
            db,
            employee_id=str(transaction.employee_id),
            month=int(transaction.payroll_month),
            year=int(transaction.payroll_year),
            exclude_id=str(transaction.id),
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Salary already generated for this employee for this month.",
            )

        db.commit()
        db.refresh(transaction)
        employee_map = {str(employee.id): employee} if employee else {}
        return {
            "transaction": PayrollService._serialize_transaction(transaction, employee_map),
            "summary": PayrollService.get_transaction_summary(db, auth),
        }

    @staticmethod
    def delete_transaction(db: Session, auth: AuthContext, transaction_id: str) -> dict[str, object]:
        transaction = db.get(PayrollTransaction, transaction_id)
        if transaction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll transaction not found")
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None or str(transaction.employee_id) != str(employee.id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this payroll transaction")

        db.delete(transaction)
        db.commit()
        return {"message": "Payroll transaction deleted successfully", "summary": PayrollService.get_transaction_summary(db, auth)}

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
    def _round_money(value: Decimal) -> Decimal:
        return value.quantize(PayrollService.MONEY, rounding=ROUND_HALF_UP)

    @staticmethod
    def _round_days(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _calendar_days_for_month(month: int, year: int) -> int:
        try:
            days_in_month = calendar.monthrange(year, month)[1]
        except calendar.IllegalMonthError:
            days_in_month = 30
        if days_in_month <= 0:
            return 30
        return days_in_month

    @staticmethod
    def _number_under_thousand_to_words(value: int) -> str:
        ones = [
            "",
            "One",
            "Two",
            "Three",
            "Four",
            "Five",
            "Six",
            "Seven",
            "Eight",
            "Nine",
            "Ten",
            "Eleven",
            "Twelve",
            "Thirteen",
            "Fourteen",
            "Fifteen",
            "Sixteen",
            "Seventeen",
            "Eighteen",
            "Nineteen",
        ]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        words: list[str] = []
        if value >= 100:
            words.extend([ones[value // 100], "Hundred"])
            value %= 100
        if value >= 20:
            words.append(tens[value // 10])
            value %= 10
        if value > 0:
            words.append(ones[value])
        return " ".join(words)

    @staticmethod
    def _amount_to_words(amount: Decimal) -> str:
        value = int(PayrollService._round_money(amount))
        if value == 0:
            return "Zero Rupees only"

        parts: list[str] = []
        crore, value = divmod(value, 10000000)
        lakh, value = divmod(value, 100000)
        thousand, value = divmod(value, 1000)
        if crore:
            parts.append(f"{PayrollService._number_under_thousand_to_words(crore)} Crore")
        if lakh:
            parts.append(f"{PayrollService._number_under_thousand_to_words(lakh)} Lakh")
        if thousand:
            parts.append(f"{PayrollService._number_under_thousand_to_words(thousand)} Thousand")
        if value:
            parts.append(PayrollService._number_under_thousand_to_words(value))
        return f"{' '.join(parts)} Rupees only"

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

        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date == target_date,
            )
        ).scalars().all()
        if any(log.status == AttendanceStatus.HALF_DAY.value for log in logs):
            return AttendanceStatus.HALF_DAY.value
        if any(log.check_in_at or log.status in {"online", "offline", AttendanceStatus.PRESENT.value} for log in logs):
            return AttendanceStatus.PRESENT.value
        if any(log.status == AttendanceStatus.ABSENT.value for log in logs):
            return AttendanceStatus.ABSENT.value
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
    def _worked_days_for_month(db: Session, *, employee_id: str, month: int, year: int, total_days: int) -> tuple[Decimal, dict[str, object]]:
        period_start = date(year, month, 1)
        period_end = date(year, month, total_days)
        summaries = db.execute(
            select(AttendanceDailySummary).where(
                AttendanceDailySummary.employee_id == employee_id,
                AttendanceDailySummary.summary_date >= period_start,
                AttendanceDailySummary.summary_date <= period_end,
            )
        ).scalars().all()
        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date >= period_start,
                AttendanceLog.attendance_date <= period_end,
            )
        ).scalars().all()

        statuses_by_date = {summary.summary_date: summary.status for summary in summaries}
        status_rank = {
            AttendanceStatus.PRESENT.value: 3,
            AttendanceStatus.HALF_DAY.value: 2,
            AttendanceStatus.LEAVE.value: 1,
            AttendanceStatus.ABSENT.value: 0,
        }
        for log in logs:
            log_status = AttendanceStatus.PRESENT.value if log.check_in_at or log.status in {"online", "offline"} else log.status
            current_status = statuses_by_date.get(log.attendance_date)
            if current_status is None or status_rank.get(log_status, 0) > status_rank.get(current_status, 0):
                statuses_by_date[log.attendance_date] = log_status

        worked_days = Decimal("0")
        counters: dict[str, object] = {
            "total_days": total_days,
            "worked_days": 0,
            "present_days": 0,
            "half_days": 0,
            "leave_days": 0,
            "absent_days": 0,
            "attendance_records": len(statuses_by_date),
        }
        for status_value in statuses_by_date.values():
            if status_value == AttendanceStatus.PRESENT.value:
                worked_days += Decimal("1")
                counters["present_days"] = int(counters["present_days"]) + 1
            elif status_value == AttendanceStatus.HALF_DAY.value:
                worked_days += Decimal("0.5")
                counters["half_days"] = int(counters["half_days"]) + 1
            elif status_value == AttendanceStatus.LEAVE.value:
                worked_days += Decimal("1")
                counters["leave_days"] = int(counters["leave_days"]) + 1
            else:
                counters["absent_days"] = int(counters["absent_days"]) + 1

        worked_days = min(worked_days, Decimal(str(total_days)))
        counters["worked_days"] = float(worked_days)
        return worked_days, counters

    @staticmethod
    def _current_month_salary_days(db: Session, *, employee_id: str, total_working_days: Decimal | None = None) -> dict[str, Decimal]:
        today = date.today()
        calendar_days = Decimal(str(PayrollService._calendar_days_for_month(today.month, today.year)))
        total_days = PayrollService._round_days(total_working_days if total_working_days is not None else calendar_days)
        present_days, _ = PayrollService._worked_days_for_month(
            db,
            employee_id=employee_id,
            month=today.month,
            year=today.year,
            total_days=int(calendar_days),
        )
        present_days = PayrollService._round_days(present_days)
        loss_of_pay = PayrollService._round_days(max(total_days - present_days, Decimal("0")))
        return {
            "total_working_days": total_days,
            "present_days": present_days,
            "loss_of_pay": loss_of_pay,
        }

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
    def serialize_salary_profile(profile: SalaryProfile, employee: Employee | None = None, salary_days: dict[str, Decimal] | None = None) -> dict[str, object]:
        return {
            "id": profile.id,
            "employee_id": profile.employee_id,
            "employee_name": employee.user.full_name if employee and employee.user else None,
            "employee_code": employee.employee_code if employee else None,
            "date_joined": profile.date_joined,
            "department": profile.department,
            "sub_department": profile.sub_department,
            "designation": profile.designation,
            "payment_mode": profile.payment_mode,
            "bank": profile.bank,
            "bank_ifsc": profile.bank_ifsc,
            "bank_account_number": profile.bank_account_number,
            "uan": profile.uan,
            "pf_number": profile.pf_number,
            "pan_number": profile.pan_number,
            "actual_payable_days": (salary_days or {}).get("actual_payable_days", profile.actual_payable_days),
            "total_working_days": (salary_days or {}).get("total_working_days", profile.total_working_days),
            "loss_of_pay": (salary_days or {}).get("loss_of_pay", profile.loss_of_pay),
            "present_days": (salary_days or {}).get("present_days", profile.present_days),
            "salary_amount": profile.salary_amount,
            "salary_transaction_id": profile.salary_transaction_id,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
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
            "monthly_salary": payslip.monthly_salary,
            "total_days": payslip.total_days,
            "worked_days": payslip.worked_days,
            "per_day_salary": payslip.per_day_salary,
            "basic": payslip.basic,
            "hra": payslip.hra,
            "special_allowance": payslip.special_allowance,
            "transport": payslip.transport,
            "medical": payslip.medical,
            "gross_salary": payslip.gross_salary,
            "deduction_amount": payslip.deduction_amount,
            "net_salary": payslip.net_salary,
            "paid_days": payslip.paid_days,
            "attendance_summary": payslip.attendance_summary or {},
            "created_at": payslip.created_at,
        }

    @staticmethod
    def _serialize_payslip_detail(
        payslip: Payslip,
        *,
        employee: Employee,
        profile: SalaryProfile,
        payroll_run: PayrollRun,
        total_earnings: Decimal,
        total_working_days: Decimal,
        loss_of_pay: Decimal,
    ) -> dict[str, object]:
        net_salary = PayrollService._round_money(Decimal(str(payslip.net_salary or 0)))
        return {
            "id": payslip.id,
            "payroll_run_id": payslip.payroll_run_id,
            "employee": {
                "id": employee.id,
                "employee_number": employee.employee_code,
                "employee_name": employee.user.full_name if employee.user else employee.employee_code,
                "date_joined": profile.date_joined or employee.joining_date,
                "department": profile.department or (employee.department.name if employee.department else None),
                "sub_department": profile.sub_department or "N/A",
                "designation": profile.designation or (employee.designation.name if employee.designation else None),
                "payment_mode": profile.payment_mode,
                "bank": profile.bank,
                "bank_ifsc": profile.bank_ifsc,
                "bank_account": profile.bank_account_number,
                "uan": profile.uan,
                "pf_number": profile.pf_number,
                "pan_number": profile.pan_number,
            },
            "salary_details": {
                "actual_payable_days": payslip.worked_days,
                "total_working_days": total_working_days,
                "loss_of_pay_days": loss_of_pay,
                "days_payable": payslip.worked_days,
                "per_day_salary": payslip.per_day_salary,
                "month": payroll_run.period_month,
                "year": payroll_run.period_year,
            },
            "earnings": {
                "basic": payslip.basic,
                "hra": payslip.hra,
                "medical_allowance": payslip.medical,
                "transport_allowance": payslip.transport,
                "special_allowance": payslip.special_allowance,
                "total_earnings": total_earnings,
            },
            "net_salary_payable": net_salary,
            "net_salary_words": PayrollService._amount_to_words(net_salary),
            "note": "All amounts displayed in this payslip are in INR",
            "footer": "This is computer generated statement, does not require signature.",
        }

    @staticmethod
    def get_meta(db: Session, auth: AuthContext) -> dict[str, object]:
        employees_stmt = (
            select(Employee)
            .options(joinedload(Employee.user), joinedload(Employee.department), joinedload(Employee.designation))
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
                    "date_joined": employee.joining_date,
                    "department": employee.department.name if employee.department else None,
                    "designation": employee.designation.name if employee.designation else None,
                }
                for employee in employees
            ]
        }

    @staticmethod
    def get_salary_profile_by_employee(db: Session, auth: AuthContext, employee_id: str) -> dict[str, object]:
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None or str(employee.id) != str(employee_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this salary profile")

        employee = PayrollService._get_active_employee(db, employee_id)
        profile = db.execute(select(SalaryProfile).where(SalaryProfile.employee_id == employee_id)).scalar_one_or_none()
        if profile is None:
            salary_days = PayrollService._current_month_salary_days(db, employee_id=employee_id)
            return {
                "profile": None,
                "defaults": {
                    "employee_id": employee.id,
                    "date_joined": employee.joining_date,
                    "department": employee.department.name if employee.department else None,
                    "sub_department": None,
                    "designation": employee.designation.name if employee.designation else None,
                    "actual_payable_days": salary_days["present_days"],
                    "total_working_days": salary_days["total_working_days"],
                    "present_days": salary_days["present_days"],
                    "loss_of_pay": salary_days["loss_of_pay"],
                    "salary_amount": None,
                },
            }
        return {"profile": PayrollService.serialize_salary_profile(profile, employee), "defaults": None}

    @staticmethod
    def list_salary_profiles(db: Session, auth: AuthContext) -> dict[str, object]:
        stmt = select(SalaryProfile).order_by(SalaryProfile.updated_at.desc(), SalaryProfile.created_at.desc())
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None:
                return {"items": [], "total": 0}
            stmt = stmt.where(SalaryProfile.employee_id == employee.id)

        profiles = db.execute(stmt).scalars().all()
        employee_ids = {str(item.employee_id) for item in profiles}
        employees = db.execute(
            select(Employee)
            .options(joinedload(Employee.user), joinedload(Employee.department), joinedload(Employee.designation))
            .where(Employee.id.in_(employee_ids))
        ).scalars().all() if employee_ids else []
        employee_map = {str(employee.id): employee for employee in employees}
        items = [PayrollService.serialize_salary_profile(profile, employee_map.get(str(profile.employee_id))) for profile in profiles]
        return {"items": items, "total": len(items)}

    @staticmethod
    def upsert_salary_profile(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        employee_id = str(payload["employee_id"])
        employee = PayrollService._get_active_employee(db, employee_id)
        profile = db.execute(select(SalaryProfile).where(SalaryProfile.employee_id == employee_id)).scalar_one_or_none()
        if profile is None:
            profile = SalaryProfile(employee_id=employee_id)
            db.add(profile)

        profile.date_joined = payload.get("date_joined")
        profile.department = PayrollService._clean_text(payload.get("department"))
        profile.sub_department = PayrollService._clean_text(payload.get("sub_department"))
        profile.designation = PayrollService._clean_text(payload.get("designation"))
        profile.payment_mode = PayrollService._clean_text(payload.get("payment_mode"))
        profile.bank = PayrollService._clean_text(payload.get("bank"))
        profile.bank_ifsc = PayrollService._clean_text(payload.get("bank_ifsc"))
        profile.bank_account_number = PayrollService._clean_text(payload.get("bank_account_number"))
        profile.uan = PayrollService._clean_text(payload.get("uan"))
        profile.pf_number = PayrollService._clean_text(payload.get("pf_number"))
        profile.pan_number = PayrollService._clean_text(payload.get("pan_number"))
        profile.actual_payable_days = Decimal(str(payload["actual_payable_days"])) if payload.get("actual_payable_days") not in {None, ""} else None
        profile.total_working_days = Decimal(str(payload["total_working_days"])) if payload.get("total_working_days") not in {None, ""} else None
        profile.present_days = Decimal(str(payload["present_days"])) if payload.get("present_days") not in {None, ""} else None
        profile.loss_of_pay = Decimal(str(payload["loss_of_pay"])) if payload.get("loss_of_pay") not in {None, ""} else None
        db.commit()
        db.refresh(profile)
        return {
            "profile": PayrollService.serialize_salary_profile(profile, employee),
            "summary": PayrollService.get_transaction_summary(db, auth),
            "message": "Salary profile saved successfully",
        }

    @staticmethod
    def get_attendance_summary(db: Session, auth: AuthContext, *, employee_id: str, month: int, year: int) -> dict[str, object]:
        if month < 1 or month > 12:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance month must be between 1 and 12")
        if year < 1900:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance year is invalid")
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee = UserScopeService.current_employee(auth)
            if employee is None or str(employee.id) != str(employee_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this attendance summary")

        PayrollService._get_active_employee(db, employee_id)
        total_days = PayrollService._calendar_days_for_month(month, year)
        worked_days, counters = PayrollService._worked_days_for_month(db, employee_id=employee_id, month=month, year=year, total_days=total_days)
        return {
            "employee_id": employee_id,
            "period_month": month,
            "period_year": year,
            "total_days": total_days,
            "worked_days": worked_days,
            "summary": counters,
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
    def calculate_payslip(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        employee_id = str(payload["employee_id"])
        month = int(payload["month"])
        year = int(payload["year"])
        monthly_salary = PayrollService._round_money(Decimal(str(payload["monthly_salary"])))
        if monthly_salary <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monthly salary must be positive")
        if not auth.access.is_super_admin and not {"payroll.manage", "payroll.view.all"} & auth.access.permission_keys:
            employee_scope = UserScopeService.current_employee(auth)
            if employee_scope is None or str(employee_scope.id) != employee_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this payslip")

        employee = PayrollService._get_active_employee(db, employee_id)
        profile = db.execute(select(SalaryProfile).where(SalaryProfile.employee_id == employee_id)).scalar_one_or_none()
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Salary employee details are missing. Save salary employee details before downloading payslip.",
            )

        if profile.present_days is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Present days are missing in salary employee details. Save present days before downloading payslip.",
            )

        if PayrollService._salary_transaction_exists(db, employee_id=employee_id, month=month, year=year):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Salary already generated for this employee for this month.",
            )

        calendar_days = Decimal(str(PayrollService._calendar_days_for_month(month, year)))
        saved_total_days = Decimal(str(profile.total_working_days)) if profile.total_working_days is not None else None
        total_days_decimal = saved_total_days if saved_total_days and saved_total_days > 0 else calendar_days
        total_days_decimal = PayrollService._round_days(total_days_decimal)

        worked_days = Decimal(str(profile.present_days))
        worked_days = PayrollService._round_days(min(max(worked_days, Decimal("0")), total_days_decimal))
        if profile.loss_of_pay is not None:
            loss_of_pay = PayrollService._round_days(max(Decimal(str(profile.loss_of_pay)), Decimal("0")))
        else:
            loss_of_pay = PayrollService._round_days(max(total_days_decimal - worked_days, Decimal("0")))
        payable_ratio = worked_days / total_days_decimal if total_days_decimal else Decimal("0")
        per_day_salary = PayrollService._round_money(monthly_salary / total_days_decimal) if total_days_decimal else Decimal("0.00")
        basic = PayrollService._round_money(monthly_salary * Decimal("0.40") * payable_ratio)
        hra = PayrollService._round_money(monthly_salary * Decimal("0.20") * payable_ratio)
        special_allowance = PayrollService._round_money(monthly_salary * Decimal("0.25") * payable_ratio)
        transport = PayrollService._round_money(monthly_salary * Decimal("0.10") * payable_ratio)
        medical = PayrollService._round_money(monthly_salary * Decimal("0.05") * payable_ratio)
        net_salary = PayrollService._round_money(monthly_salary * payable_ratio)
        total_earnings = PayrollService._round_money(basic + hra + medical + transport + special_allowance)

        payroll_run = db.execute(select(PayrollRun).where(PayrollRun.period_month == month, PayrollRun.period_year == year)).scalar_one_or_none()
        if payroll_run is None:
            payroll_run = PayrollRun(period_month=month, period_year=year, status=PayrollRunStatus.COMPLETED.value, initiated_by_user_id=auth.user.id)
            db.add(payroll_run)
            db.flush()
        else:
            payroll_run.status = PayrollRunStatus.COMPLETED.value
        payroll_run.processed_at = datetime.now(UTC)

        payslip = db.execute(
            select(Payslip).where(Payslip.payroll_run_id == payroll_run.id, Payslip.employee_id == employee.id)
        ).scalar_one_or_none()
        if payslip is None:
            payslip = Payslip(payroll_run_id=payroll_run.id, employee_id=employee.id)
            db.add(payslip)

        payslip.monthly_salary = monthly_salary
        payslip.total_days = int(total_days_decimal)
        payslip.worked_days = worked_days
        payslip.per_day_salary = per_day_salary
        payslip.basic = basic
        payslip.hra = hra
        payslip.special_allowance = special_allowance
        payslip.transport = transport
        payslip.medical = medical
        payslip.gross_salary = total_earnings
        payslip.deduction_amount = Decimal("0.00")
        payslip.net_salary = net_salary
        payslip.paid_days = worked_days
        payslip.attendance_summary = {
            "source": "salary_profile",
            "total_working_days": float(total_days_decimal),
            "present_days": float(worked_days),
            "loss_of_pay": float(loss_of_pay),
        }

        employee_name = employee.user.full_name if employee.user else employee.employee_code
        salary_transaction = PayrollTransaction(
            transaction_type="salary",
            employee_id=employee.id,
            employee_name=employee_name,
            payroll_month=month,
            payroll_year=year,
            amount=monthly_salary,
            transaction_date=date.today(),
            description=f"Payslip salary {employee_name} ({employee.employee_code}) {month:02d}/{year}",
        )
        db.add(salary_transaction)

        db.commit()
        db.refresh(payslip)
        db.refresh(salary_transaction)
        employee_map = {str(employee.id): employee}
        return {
            "payslip": PayrollService._serialize_payslip_detail(
                payslip,
                employee=employee,
                profile=profile,
                payroll_run=payroll_run,
                total_earnings=total_earnings,
                total_working_days=total_days_decimal,
                loss_of_pay=loss_of_pay,
            ),
            "transaction": PayrollService._serialize_transaction(salary_transaction, employee_map),
            "summary": PayrollService.get_transaction_summary(db, auth),
            "message": "Payslip calculated successfully",
        }

    @staticmethod
    def run_payroll(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        month = int(payload["period_month"])
        year = int(payload["period_year"])
        employee_id = payload.get("employee_id")
        if month < 1 or month > 12:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll month must be between 1 and 12")
        if year < 1900:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll year is invalid")
        total_days = max(PayrollService._calendar_days_for_month(month, year), 1)

        payroll_run = db.execute(select(PayrollRun).where(PayrollRun.period_month == month, PayrollRun.period_year == year)).scalar_one_or_none()
        if payroll_run and payroll_run.status == PayrollRunStatus.COMPLETED.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll is already completed for this period")
        if payroll_run is None:
            payroll_run = PayrollRun(period_month=month, period_year=year, status=PayrollRunStatus.PROCESSING.value, initiated_by_user_id=auth.user.id)
            db.add(payroll_run)
            db.flush()
        else:
            payroll_run.status = PayrollRunStatus.PROCESSING.value

        employee_stmt = select(Employee).options(joinedload(Employee.user)).where(Employee.is_deleted.is_(False), Employee.status == EmployeeStatus.ACTIVE.value)
        if employee_id:
            employee_stmt = employee_stmt.where(Employee.id == employee_id)
        employees = db.execute(employee_stmt).scalars().all()
        run_results: list[dict[str, object]] = []

        for employee in employees:
            structure = PayrollService._resolve_salary_structure(db, employee, month, year)
            monthly_salary = Decimal(str(structure.basic_salary if structure else (employee.base_salary or 0)))
            if monthly_salary <= 0:
                employee_name = employee.user.full_name if employee.user else employee.employee_code
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Monthly salary is missing for {employee_name}")

            worked_days, counters = PayrollService._worked_days_for_month(db, employee_id=str(employee.id), month=month, year=year, total_days=total_days)
            payable_ratio = worked_days / Decimal(str(total_days))
            per_day_salary = PayrollService._round_money(monthly_salary / Decimal(str(total_days)))
            basic = PayrollService._round_money(monthly_salary * Decimal("0.40") * payable_ratio)
            hra = PayrollService._round_money(monthly_salary * Decimal("0.20") * payable_ratio)
            special_allowance = PayrollService._round_money(monthly_salary * Decimal("0.25") * payable_ratio)
            transport = PayrollService._round_money(monthly_salary * Decimal("0.10") * payable_ratio)
            medical = PayrollService._round_money(monthly_salary * Decimal("0.05") * payable_ratio)
            net_salary = PayrollService._round_money(monthly_salary * payable_ratio)
            gross_salary = net_salary
            deduction_amount = Decimal("0.00")

            payslip = db.execute(
                select(Payslip).where(Payslip.payroll_run_id == payroll_run.id, Payslip.employee_id == employee.id)
            ).scalar_one_or_none()
            if payslip is None:
                payslip = Payslip(payroll_run_id=payroll_run.id, employee_id=employee.id)
                db.add(payslip)

            payslip.gross_salary = gross_salary
            payslip.deduction_amount = deduction_amount
            payslip.net_salary = net_salary
            payslip.monthly_salary = PayrollService._round_money(monthly_salary)
            payslip.total_days = total_days
            payslip.worked_days = worked_days
            payslip.per_day_salary = per_day_salary
            payslip.basic = basic
            payslip.hra = hra
            payslip.special_allowance = special_allowance
            payslip.transport = transport
            payslip.medical = medical
            payslip.paid_days = worked_days
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
            f"Monthly Salary: {payslip.monthly_salary}",
            f"Total Days: {payslip.total_days}",
            f"Worked Days: {payslip.worked_days}",
            f"Per Day Salary: {payslip.per_day_salary}",
            f"Basic: {payslip.basic}",
            f"HRA: {payslip.hra}",
            f"Special Allowance: {payslip.special_allowance}",
            f"Transport: {payslip.transport}",
            f"Medical: {payslip.medical}",
            f"Net Salary: {payslip.net_salary}",
            "",
            "Attendance Summary:",
        ]
        for key, value in (payslip.attendance_summary or {}).items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)
