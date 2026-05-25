from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings


def data_folder() -> Path:
    db_name = settings.DATABASES["default"]["NAME"]
    return Path(db_name).resolve().parent


def settings_file() -> Path:
    return data_folder() / "system_settings.json"


def load_system_settings() -> dict:
    path = settings_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_system_settings(data: dict) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_setting(key, default=None):
    return load_system_settings().get(key, default)


def set_setting(key, value) -> None:
    data = load_system_settings()
    data[key] = value
    save_system_settings(data)
