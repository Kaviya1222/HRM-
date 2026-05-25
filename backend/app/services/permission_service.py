from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import is_super_admin_role
from app.models.auth import Permission, Role, RolePermission, User, UserPermission


MODULE_PERMISSION_OVERRIDES = {
    "users": "settings",
}


@dataclass(slots=True)
class EffectiveAccess:
    permission_keys: set[str]
    is_super_admin: bool


class PermissionService:
    @staticmethod
    def get_effective_access(db: Session, user: User) -> EffectiveAccess:
        if is_super_admin_role(
            code=user.role.code if user.role else None,
            name=user.role.name if user.role else None,
        ):
            return EffectiveAccess(permission_keys={"*"}, is_super_admin=True)

        role_permission_rows = db.execute(
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == user.role_id, RolePermission.is_allowed.is_(True))
        ).scalars()
        effective_permissions = set(role_permission_rows)

        user_permission_rows = db.execute(
            select(Permission.key, UserPermission.is_allowed)
            .join(UserPermission, UserPermission.permission_id == Permission.id)
            .where(UserPermission.user_id == user.id)
        ).all()

        for permission_key, is_allowed in user_permission_rows:
            if is_allowed:
                effective_permissions.add(permission_key)
            else:
                effective_permissions.discard(permission_key)

        return EffectiveAccess(permission_keys=effective_permissions, is_super_admin=False)

    @staticmethod
    def has_permissions(access: EffectiveAccess, required_permissions: tuple[str, ...]) -> bool:
        if access.is_super_admin or "*" in access.permission_keys:
            return True
        return all(permission in access.permission_keys for permission in required_permissions)

    @staticmethod
    def module_name_for_permission(permission_key: str) -> str | None:
        if not permission_key or permission_key == "*":
            return None
        parts = permission_key.split(".")
        if len(parts) < 2:
            return None
        if parts[0] in {"module", "menu", "page"}:
            return parts[1]
        return MODULE_PERMISSION_OVERRIDES.get(parts[0], parts[0])

    @staticmethod
    def has_module_access(access: EffectiveAccess, permission_key: str) -> bool:
        if access.is_super_admin or "*" in access.permission_keys:
            return True
        module_name = PermissionService.module_name_for_permission(permission_key)
        if not module_name:
            return True
        module_permission = f"module.{module_name}.access"
        return module_permission in access.permission_keys

    @staticmethod
    def has_permission_with_module(access: EffectiveAccess, permission_key: str) -> bool:
        if access.is_super_admin or "*" in access.permission_keys:
            return True
        return permission_key in access.permission_keys and PermissionService.has_module_access(access, permission_key)

    @staticmethod
    def has_any_permission_with_module(access: EffectiveAccess, permission_keys: tuple[str, ...]) -> bool:
        if access.is_super_admin or "*" in access.permission_keys:
            return True
        return any(PermissionService.has_permission_with_module(access, permission) for permission in permission_keys)

    @staticmethod
    def list_roles(db: Session) -> list[Role]:
        return list(db.execute(select(Role).order_by(Role.hierarchy_rank.asc())).scalars().all())

    @staticmethod
    def list_permission_catalog(db: Session) -> list[Permission]:
        return list(db.execute(select(Permission).order_by(Permission.module.asc(), Permission.category.asc(), Permission.key.asc())).scalars().all())

    @staticmethod
    def get_role_permission_matrix(db: Session, role_id: UUID | str) -> tuple[Role, list[dict[str, object]]]:
        role = db.get(Role, str(role_id))
        if not role:
            raise ValueError("Role not found")

        permissions = PermissionService.list_permission_catalog(db)
        mapping_rows = db.execute(
            select(RolePermission.permission_id, RolePermission.is_allowed).where(RolePermission.role_id == role.id)
        ).all()
        mapping = {permission_id: is_allowed for permission_id, is_allowed in mapping_rows}

        items: list[dict[str, object]] = []
        for permission in permissions:
            items.append(
                {
                    "permission_id": permission.id,
                    "permission_key": permission.key,
                    "permission_name": permission.name,
                    "module": permission.module,
                    "category": permission.category,
                    "action": permission.action,
                    "is_allowed": True if is_super_admin_role(code=role.code, name=role.name) else mapping.get(permission.id, False),
                }
            )

        return role, items

    @staticmethod
    def update_role_permissions(db: Session, role_id: UUID | str, assignments: list[dict[str, object]]) -> Role:
        role = db.get(Role, str(role_id))
        if not role:
            raise ValueError("Role not found")
        if is_super_admin_role(code=role.code, name=role.name):
            raise ValueError("Super Admin permissions are always full access and cannot be reduced")

        permissions = PermissionService.list_permission_catalog(db)
        permission_by_key = {permission.key: permission for permission in permissions}
        existing_rows = db.execute(select(RolePermission).where(RolePermission.role_id == role.id)).scalars().all()
        role_permission_by_permission_id = {row.permission_id: row for row in existing_rows}

        for item in assignments:
            permission_key = str(item["permission_key"])
            is_allowed = bool(item["is_allowed"])
            permission = permission_by_key.get(permission_key)
            if not permission:
                raise ValueError(f"Unknown permission: {permission_key}")

            role_permission = role_permission_by_permission_id.get(permission.id)
            if role_permission is None:
                role_permission = RolePermission(role_id=role.id, permission_id=permission.id, is_allowed=is_allowed)
                db.add(role_permission)
                role_permission_by_permission_id[permission.id] = role_permission
            else:
                role_permission.is_allowed = is_allowed

        db.commit()
        db.refresh(role)
        return role
