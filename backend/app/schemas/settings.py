from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PermissionCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    module: str
    category: str
    resource: str
    action: str
    description: str | None = None


class RoleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    hierarchy_rank: int


class RolePermissionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    permission_id: UUID
    permission_key: str
    permission_name: str
    module: str
    category: str
    action: str
    is_allowed: bool


class RolePermissionMatrix(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: UUID
    role_code: str
    role_name: str
    hierarchy_rank: int
    permissions: list[RolePermissionItem]


class RolePermissionUpdateItem(BaseModel):
    permission_key: str
    is_allowed: bool


class RolePermissionUpdateRequest(BaseModel):
    assignments: list[RolePermissionUpdateItem] = Field(default_factory=list)


class RoleAccessControlItem(BaseModel):
    module_name: str
    module_label: str
    can_view: bool
    can_add: bool
    can_edit: bool
    can_delete: bool


class RoleAccessControlMatrix(BaseModel):
    role_id: UUID
    role_code: str
    role_name: str
    hierarchy_rank: int
    modules: list[RoleAccessControlItem]


class RoleAccessControlUpdateItem(BaseModel):
    module_name: str
    can_view: bool = False
    can_add: bool = False
    can_edit: bool = False
    can_delete: bool = False


class RoleAccessControlUpdateRequest(BaseModel):
    assignments: list[RoleAccessControlUpdateItem] = Field(default_factory=list)


class CurrentUserPermissionsResponse(BaseModel):
    user_id: UUID
    role_code: str
    role_name: str
    permission_keys: list[str]


class AppSettingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    category: str
    name: str
    description: str | None = None
    value_type: str = "json"
    value_json: dict | list | str | int | float | bool | None = None
    is_public: bool = False


class AppSettingUpsertRequest(BaseModel):
    items: list[AppSettingItem]


class BrandingSettings(BaseModel):
    organization_name: str
    tagline: str
    logo_text: str
    logo_data_url: str | None = None
    logo_url: str | None = None
