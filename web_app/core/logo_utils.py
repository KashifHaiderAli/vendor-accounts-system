from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse

from authentication.auth_utils import dictfetchone


ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_LOGO_SIZE = 2 * 1024 * 1024


def database_folder() -> Path:
    db_name = settings.DATABASES["default"]["NAME"]
    return Path(db_name).resolve().parent


def logo_storage_folder() -> Path:
    return database_folder() / "company_assets" / "logo"


def validate_logo_file(uploaded_file) -> str:
    if not uploaded_file:
        raise ValidationError("Please select a logo file.")
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_LOGO_EXTENSIONS:
        raise ValidationError("Logo must be a PNG, JPG, JPEG, WEBP, or BMP file.")
    if uploaded_file.size > MAX_LOGO_SIZE:
        raise ValidationError("Logo file size must be 2 MB or less.")
    return extension


def save_company_logo(uploaded_file) -> str:
    extension = validate_logo_file(uploaded_file)
    folder = logo_storage_folder()
    folder.mkdir(parents=True, exist_ok=True)

    for old_file in folder.glob("company_logo.*"):
        if old_file.is_file():
            old_file.unlink(missing_ok=True)

    target = folder / f"company_logo{extension}"
    with target.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    return str(target)


def get_company_logo_path(company_id) -> str | None:
    if not company_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT logo_path FROM companies WHERE id = %s LIMIT 1", [company_id])
        row = dictfetchone(cursor)
    logo_path = (row or {}).get("logo_path")
    if not logo_path:
        return None
    path = Path(logo_path)
    if not path.is_absolute():
        path = database_folder() / path
    try:
        resolved = path.resolve()
    except OSError:
        return None
    return str(resolved) if resolved.exists() and resolved.is_file() else None


def get_company_logo_url(company_id) -> str | None:
    return reverse("company_logo") if get_company_logo_path(company_id) else None
