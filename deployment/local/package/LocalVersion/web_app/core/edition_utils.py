from __future__ import annotations

import os

from django.conf import settings

from core.system_settings import get_setting, set_setting


TAX_SETTING_KEY = "tax_enabled"


def env_tax_enabled() -> bool:
    return str(os.getenv("ENABLE_TAX", "True")).strip().lower() in {"1", "true", "yes", "on"}


def is_tax_enabled(request=None, company_id=None) -> bool:
    if not env_tax_enabled():
        return False
    value = get_setting(TAX_SETTING_KEY, None)
    if value is None:
        return True
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def set_tax_enabled(value: bool) -> None:
    if not env_tax_enabled() and value:
        set_setting(TAX_SETTING_KEY, False)
        return
    set_setting(TAX_SETTING_KEY, bool(value))


def can_change_tax_enabled(request) -> bool:
    return str(request.session.get("username") or "").strip().lower() == "admin"


def require_tax_enabled(request=None, company_id=None) -> None:
    if not is_tax_enabled(request=request, company_id=company_id):
        raise ValueError("This feature is disabled in this edition.")


def get_edition_name() -> str:
    return "MainVersion" if env_tax_enabled() else "LocalVersion"


def get_app_version_label() -> str:
    return "Main Version" if env_tax_enabled() else "Local Version"


def database_file_name() -> str:
    return str(settings.DATABASES["default"]["NAME"]).replace("\\", "/").split("/")[-1]
