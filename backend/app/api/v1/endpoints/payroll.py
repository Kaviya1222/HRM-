from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_any_permissions, require_permissions
from app.schemas.payroll import (
    PayrollRunRequest,
    PayrollTransactionCreateRequest,
    PayrollTransactionUpdateRequest,
    PayslipCalculateRequest,
    SalaryProfileUpsertRequest,
    SalaryStructureUpsertRequest,
)
from app.services.payroll_service import PayrollService

router = APIRouter()


@router.get("/meta")
def get_payroll_meta(
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.get_meta(db, auth)


@router.get("/summary")
def get_payroll_summary(
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.get_transaction_summary(db, auth)


@router.get("/dashboard-summary")
def get_payroll_dashboard_summary(
    period_month: int | None = None,
    period_year: int | None = None,
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.dashboard_summary(db, auth, month=period_month, year=period_year)


@router.get("/transactions")
def list_payroll_transactions(
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.list_transactions(db, auth)


@router.post("/transactions")
def add_payroll_transaction(
    payload: PayrollTransactionCreateRequest,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.add_transaction(db, auth, payload.model_dump())


@router.put("/transactions/{transaction_id}")
def update_payroll_transaction(
    transaction_id: UUID,
    payload: PayrollTransactionUpdateRequest,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.update_transaction(db, auth, str(transaction_id), payload.model_dump(exclude_unset=True))


@router.delete("/transactions/{transaction_id}")
def delete_payroll_transaction(
    transaction_id: UUID,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.delete_transaction(db, auth, str(transaction_id))


@router.get("/salary-structures")
def list_salary_structures(
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.list_salary_structures(db, auth)


@router.post("/salary-structures")
def upsert_salary_structure(
    payload: SalaryStructureUpsertRequest,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.upsert_salary_structure(db, auth, payload.model_dump())


@router.get("/salary-profiles")
def list_salary_profiles(
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.list_salary_profiles(db, auth)


@router.get("/salary-profiles/{employee_id}")
def get_salary_profile(
    employee_id: UUID,
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.get_salary_profile_by_employee(db, auth, str(employee_id))


@router.post("/salary-profiles")
def upsert_salary_profile(
    payload: SalaryProfileUpsertRequest,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.upsert_salary_profile(db, auth, payload.model_dump())


@router.put("/salary-profiles/{employee_id}")
def update_salary_profile(
    employee_id: UUID,
    payload: SalaryProfileUpsertRequest,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    data = payload.model_dump()
    data["employee_id"] = str(employee_id)
    return PayrollService.upsert_salary_profile(db, auth, data)


@router.get("/attendance-summary")
def get_payroll_attendance_summary(
    employee_id: UUID,
    period_month: int,
    period_year: int,
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.get_attendance_summary(
        db,
        auth,
        employee_id=str(employee_id),
        month=period_month,
        year=period_year,
    )


@router.get("/runs")
def list_payroll_runs(
    _: AuthContext = Depends(require_any_permissions("payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.list_runs(db)


@router.post("/run")
def run_payroll(
    payload: PayrollRunRequest,
    auth: AuthContext = Depends(require_permissions("payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.run_payroll(db, auth, payload.model_dump())


@router.get("/payslips")
def list_payslips(
    payroll_run_id: UUID | None = None,
    auth: AuthContext = Depends(require_any_permissions("payroll.view.own", "payroll.view.all", "payroll.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.list_payslips(db, auth, payroll_run_id=str(payroll_run_id) if payroll_run_id else None)


@router.post("/payslips/calculate")
def calculate_payslip(
    payload: PayslipCalculateRequest,
    auth: AuthContext = Depends(require_permissions("payroll.download")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PayrollService.calculate_payslip(db, auth, payload.model_dump())


@router.get("/payslips/{payslip_id}/download", response_class=PlainTextResponse)
def download_payslip(
    payslip_id: UUID,
    auth: AuthContext = Depends(require_permissions("payroll.download")),
    db: Session = Depends(get_db),
) -> str:
    return PayrollService.render_payslip_text(db, auth, str(payslip_id))
