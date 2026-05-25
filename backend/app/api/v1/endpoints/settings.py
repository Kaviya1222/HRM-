from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_super_admin
from app.schemas.settings import AppSettingItem, AppSettingUpsertRequest, BrandingSettings, PermissionCatalogItem, RoleListItem, RolePermissionMatrix, RolePermissionUpdateRequest
from app.services.permission_service import PermissionService
from app.services.settings_service import SettingsService

router = APIRouter()


@router.get("/branding", response_model=BrandingSettings)
def get_public_branding(db: Session = Depends(get_db)) -> dict[str, object]:
    return SettingsService.get_branding(db)


@router.get("/roles", response_model=list[RoleListItem])
def list_roles(_: AuthContext = Depends(require_super_admin), db: Session = Depends(get_db)) -> list[object]:
    return PermissionService.list_roles(db)


@router.get("/permissions/catalog", response_model=list[PermissionCatalogItem])
def list_permission_catalog(_: AuthContext = Depends(require_super_admin), db: Session = Depends(get_db)) -> list[object]:
    return PermissionService.list_permission_catalog(db)


@router.get("/roles/{role_id}/permissions", response_model=RolePermissionMatrix)
def get_role_permissions(role_id: UUID, _: AuthContext = Depends(require_super_admin), db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        role, permissions = PermissionService.get_role_permission_matrix(db, role_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {
        "role_id": role.id,
        "role_code": role.code,
        "role_name": role.name,
        "hierarchy_rank": role.hierarchy_rank,
        "permissions": permissions,
    }


@router.put("/roles/{role_id}/permissions", response_model=RolePermissionMatrix)
def update_role_permissions(
    role_id: UUID,
    payload: RolePermissionUpdateRequest,
    _: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        PermissionService.update_role_permissions(db, role_id, [item.model_dump() for item in payload.assignments])
        role, permissions = PermissionService.get_role_permission_matrix(db, role_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "role_id": role.id,
        "role_code": role.code,
        "role_name": role.name,
        "hierarchy_rank": role.hierarchy_rank,
        "permissions": permissions,
    }


@router.get("/app-settings", response_model=list[AppSettingItem])
def list_app_settings(_: AuthContext = Depends(require_super_admin), db: Session = Depends(get_db)) -> list[object]:
    return SettingsService.list_app_settings(db)


@router.put("/app-settings", response_model=list[AppSettingItem])
def upsert_app_settings(
    payload: AppSettingUpsertRequest,
    auth: AuthContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> list[object]:
    return SettingsService.upsert_app_settings(
        db,
        [item.model_dump() for item in payload.items],
        updated_by_user_id=str(auth.user.id),
    )
