from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.utility import AppSetting


DEFAULT_BRANDING = {
    "organization_name": "HRM Suite",
    "tagline": "Workforce Portal",
    "logo_text": "HRM",
    "logo_data_url": None,
    "logo_url": None,
}


class SettingsService:
    @staticmethod
    def list_app_settings(db: Session) -> list[AppSetting]:
        settings = list(db.execute(select(AppSetting)).scalars().all())
        return sorted(settings, key=lambda item: (item.category, item.key))

    @staticmethod
    def get_setting_value(db: Session, key: str, default: object = None) -> object:
        setting = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
        if setting is None:
            return default
        return setting.value_json if setting.value_json is not None else default

    @staticmethod
    def get_numeric_setting(db: Session, key: str, nested_key: str, default: int) -> int:
        value = SettingsService.get_setting_value(db, key, default=None)
        if isinstance(value, dict):
            nested_value = value.get(nested_key)
            if isinstance(nested_value, (int, float)):
                return int(nested_value)
        return int(default)

    @staticmethod
    def get_object_setting(db: Session, key: str, default: dict[str, object]) -> dict[str, object]:
        value = SettingsService.get_setting_value(db, key, default=None)
        if isinstance(value, dict):
            return value
        return default

    @staticmethod
    def get_boolean_setting(db: Session, key: str, nested_key: str, default: bool) -> bool:
        value = SettingsService.get_setting_value(db, key, default=None)
        if isinstance(value, dict):
            nested_value = value.get(nested_key)
            if isinstance(nested_value, bool):
                return nested_value
        if isinstance(value, bool):
            return value
        return default

    @staticmethod
    def get_branding(db: Session) -> dict[str, object]:
        organization_setting = SettingsService.get_object_setting(
            db,
            "branding.organization_name",
            {"text": DEFAULT_BRANDING["organization_name"]},
        )
        tagline_setting = SettingsService.get_object_setting(
            db,
            "branding.portal_tagline",
            {"text": DEFAULT_BRANDING["tagline"]},
        )
        logo_setting = SettingsService.get_object_setting(
            db,
            "branding.logo",
            {
                "text": DEFAULT_BRANDING["logo_text"],
                "data_url": DEFAULT_BRANDING["logo_data_url"],
                "url": DEFAULT_BRANDING["logo_url"],
            },
        )
        logo_url = logo_setting.get("url") or logo_setting.get("path") or DEFAULT_BRANDING["logo_url"]
        logo_data_url = logo_setting.get("data_url") or logo_url or DEFAULT_BRANDING["logo_data_url"]

        return {
            "organization_name": str(organization_setting.get("text") or DEFAULT_BRANDING["organization_name"]),
            "tagline": str(tagline_setting.get("text") or DEFAULT_BRANDING["tagline"]),
            "logo_text": str(logo_setting.get("text") or DEFAULT_BRANDING["logo_text"]),
            "logo_data_url": logo_data_url,
            "logo_url": logo_url,
        }

    @staticmethod
    def upsert_app_settings(db: Session, items: list[dict[str, object]], updated_by_user_id: str | None = None) -> list[AppSetting]:
        existing_items = {setting.key: setting for setting in SettingsService.list_app_settings(db)}

        for item in items:
            setting = existing_items.get(str(item["key"]))
            if setting is None:
                setting = AppSetting(
                    key=str(item["key"]),
                    category=str(item["category"]),
                    name=str(item["name"]),
                    description=item.get("description"),
                    value_type=str(item.get("value_type", "json")),
                    value_json=item.get("value_json"),
                    is_public=bool(item.get("is_public", False)),
                    updated_by_user_id=updated_by_user_id,
                )
                db.add(setting)
                existing_items[setting.key] = setting
            else:
                setting.category = str(item["category"])
                setting.name = str(item["name"])
                setting.description = item.get("description")
                setting.value_type = str(item.get("value_type", setting.value_type))
                setting.value_json = item.get("value_json")
                setting.is_public = bool(item.get("is_public", setting.is_public))
                setting.updated_by_user_id = updated_by_user_id

        db.commit()
        return SettingsService.list_app_settings(db)
