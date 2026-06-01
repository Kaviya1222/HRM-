from __future__ import annotations

from pathlib import Path
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_any_permissions, require_permissions
from app.core.config import ROOT_DIR
from app.schemas.settings import AppSettingItem, AppSettingUpsertRequest, BrandingSettings, PermissionCatalogItem, RoleListItem, RolePermissionMatrix, RolePermissionUpdateRequest
from app.services.permission_service import PermissionService
from app.services.settings_service import SettingsService

router = APIRouter()

LOGO_STORAGE_DIR = ROOT_DIR / "backend" / "storage" / "branding"
ALLOWED_LOGO_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/svg+xml": ".svg",
}
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}


@router.get("/branding", response_model=BrandingSettings)
def get_public_branding(db: Session = Depends(get_db)) -> dict[str, object]:
    return SettingsService.get_branding(db)


@router.get("/roles", response_model=list[RoleListItem])
def list_roles(
    _: AuthContext = Depends(require_any_permissions("settings.permissions.manage", "settings.roles.manage", "settings.app.manage")),
    db: Session = Depends(get_db),
) -> list[object]:
    return PermissionService.list_roles(db)


@router.get("/permissions/catalog", response_model=list[PermissionCatalogItem])
def list_permission_catalog(
    _: AuthContext = Depends(require_any_permissions("settings.permissions.manage", "settings.roles.manage", "settings.app.manage")),
    db: Session = Depends(get_db),
) -> list[object]:
    return PermissionService.list_permission_catalog(db)


@router.get("/roles/{role_id}/permissions", response_model=RolePermissionMatrix)
def get_role_permissions(
    role_id: UUID,
    _: AuthContext = Depends(require_any_permissions("settings.permissions.manage", "settings.roles.manage", "settings.app.manage")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
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
    _: AuthContext = Depends(require_permissions("settings.permissions.manage")),
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
def list_app_settings(
    _: AuthContext = Depends(require_any_permissions("settings.permissions.manage", "settings.roles.manage", "settings.app.manage")),
    db: Session = Depends(get_db),
) -> list[object]:
    return SettingsService.list_app_settings(db)


@router.put("/app-settings", response_model=list[AppSettingItem])
def upsert_app_settings(
    payload: AppSettingUpsertRequest,
    auth: AuthContext = Depends(require_permissions("settings.app.manage")),
    db: Session = Depends(get_db),
) -> list[object]:
    return SettingsService.upsert_app_settings(
        db,
        [item.model_dump() for item in payload.items],
        updated_by_user_id=str(auth.user.id),
    )


@router.post("/branding/logo")
async def upload_branding_logo(
    request: Request,
    logo: UploadFile = File(...),
    _: AuthContext = Depends(require_permissions("settings.app.manage")),
) -> dict[str, str]:
    content_type = (logo.content_type or "").lower()
    original_suffix = Path(logo.filename or "").suffix.lower()
    if content_type not in ALLOWED_LOGO_TYPES and original_suffix not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Logo must be a PNG, JPG, or SVG file.")

    suffix = ALLOWED_LOGO_TYPES.get(content_type) or original_suffix
    if suffix == ".jpeg":
        suffix = ".jpg"
    file_name = f"{uuid4().hex}{suffix}"
    LOGO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    target_path = LOGO_STORAGE_DIR / file_name

    contents = await logo.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded logo file is empty.")
    target_path.write_bytes(contents)

    logo_path = f"/media/branding/{file_name}"
    logo_url = str(request.base_url).rstrip("/") + logo_path
    return {"logo_path": logo_path, "logo_url": logo_url}
