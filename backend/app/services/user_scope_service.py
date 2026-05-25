from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models.employee import Employee
from app.services.permission_service import PermissionService


class UserScopeService:
    @staticmethod
    def current_employee(auth: AuthContext) -> Employee | None:
        return auth.user.employee_profile

    @staticmethod
    def current_employee_id(auth: AuthContext) -> str | None:
        employee = UserScopeService.current_employee(auth)
        return str(employee.id) if employee else None

    @staticmethod
    def get_team_employee_ids(db: Session, auth: AuthContext, include_self: bool = True) -> set[str]:
        employee = UserScopeService.current_employee(auth)
        if employee is None:
            return set()

        team_rows = db.execute(
            select(Employee.id).where(
                Employee.manager_id == employee.id,
                Employee.is_deleted.is_(False),
            )
        ).scalars().all()
        team_ids = {str(item) for item in team_rows}
        if include_self:
            team_ids.add(str(employee.id))
        return team_ids

    @staticmethod
    def resolve_employee_scope(
        db: Session,
        auth: AuthContext,
        *,
        own_permission: str | None = None,
        team_permission: str | None = None,
        all_permission: str | None = None,
        include_self_in_team: bool = True,
    ) -> set[str] | None:
        if auth.access.is_super_admin:
            return None
        if all_permission and PermissionService.has_permissions(auth.access, (all_permission,)):
            return None

        scope_ids: set[str] = set()
        if own_permission and PermissionService.has_permissions(auth.access, (own_permission,)):
            employee_id = UserScopeService.current_employee_id(auth)
            if employee_id:
                scope_ids.add(employee_id)

        if team_permission and PermissionService.has_permissions(auth.access, (team_permission,)):
            scope_ids.update(UserScopeService.get_team_employee_ids(db, auth, include_self=include_self_in_team))

        return scope_ids

    @staticmethod
    def ensure_employee_in_scope(employee_id: str, scope_ids: set[str] | None) -> None:
        if scope_ids is not None and employee_id not in scope_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this employee's data",
            )
