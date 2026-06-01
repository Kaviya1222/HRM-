from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_permissions
from app.schemas.employee import (
    EmployeeCreateRequest,
    EmployeeDetail,
    EmployeeListResponse,
    EmployeeManagerUpdateRequest,
    EmployeeMetaResponse,
    EmployeeStatusUpdateRequest,
    EmployeeUpdateRequest,
)
from app.services.employee_service import EmployeeService
from app.services.permission_service import PermissionService

router = APIRouter()


@router.get("/meta", response_model=EmployeeMetaResponse)
def get_employee_meta(
    auth: AuthContext = Depends(require_permissions("employees.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return EmployeeService.get_employee_meta(db, auth)


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    department_id: UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _: AuthContext = Depends(require_permissions("employees.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return EmployeeService.list_employees(
        db,
        search=search,
        status=status_filter,
        department_id=department_id,
        is_active=is_active,
    )


@router.post("", response_model=EmployeeDetail, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreateRequest,
    auth: AuthContext = Depends(require_permissions("employees.create")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return EmployeeService.create_employee(db, auth, payload.model_dump())


@router.get("/{employee_id}", response_model=EmployeeDetail)
def get_employee(
    employee_id: UUID,
    _: AuthContext = Depends(require_permissions("employees.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return EmployeeService.get_employee_detail(db, employee_id)


@router.put("/{employee_id}", response_model=EmployeeDetail)
def update_employee(
    employee_id: UUID,
    payload: EmployeeUpdateRequest,
    auth: AuthContext = Depends(require_permissions("employees.edit")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return EmployeeService.update_employee(db, auth, employee_id, payload.model_dump())


@router.patch("/{employee_id}/status", response_model=EmployeeDetail)
def update_employee_status(
    employee_id: UUID,
    payload: EmployeeStatusUpdateRequest,
    auth: AuthContext = Depends(require_permissions("employees.deactivate")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    required_user_permission = "users.activate" if payload.is_active else "users.deactivate"
    if not PermissionService.has_permissions(auth.access, (required_user_permission,)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to change user activation state",
        )
    return EmployeeService.update_employee_status(db, auth, employee_id=employee_id, is_active=payload.is_active)


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: UUID,
    auth: AuthContext = Depends(require_permissions("employees.deactivate")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not PermissionService.has_permissions(auth.access, ("users.deactivate",)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to deactivate linked user accounts",
        )
    return EmployeeService.delete_employee(db, auth, employee_id)


@router.patch("/{employee_id}/manager", response_model=EmployeeDetail)
def assign_reporting_manager(
    employee_id: UUID,
    payload: EmployeeManagerUpdateRequest,
    auth: AuthContext = Depends(require_permissions("employees.assign_manager")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return EmployeeService.assign_manager(
        db,
        auth,
        employee_id=employee_id,
        manager_id=payload.manager_id,
        start_date=payload.start_date,
    )
