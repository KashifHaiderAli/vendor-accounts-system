from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection

from .system_settings import data_folder, get_setting, set_setting


SYNC_FOLDER_MARKERS = ("onedrive", "google drive", "dropbox")
CORE_TABLES = {"companies", "branches", "users", "accounts", "journal_entries"}
BACKUP_HISTORY_FILE = "backup_history.json"
BACKUP_FOLDER_KEY = "backup_folder"


class BackupError(Exception):
    pass


def live_db_path() -> Path:
    return Path(settings.DATABASES["default"]["NAME"]).resolve()


def default_backup_folder() -> Path:
    return data_folder() / "backups"


def get_backup_folder() -> Path:
    configured = get_setting(BACKUP_FOLDER_KEY)
    return Path(configured).expanduser().resolve() if configured else default_backup_folder()


def set_backup_folder(path_value: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    set_setting(BACKUP_FOLDER_KEY, str(path))
    return path


def is_synced_path(path: Path) -> bool:
    lowered = str(path).lower()
    return any(marker in lowered for marker in SYNC_FOLDER_MARKERS)


def same_folder_warning(folder: Path) -> bool:
    try:
        return folder.resolve() == live_db_path().parent.resolve()
    except OSError:
        return False


def history_path() -> Path:
    return data_folder() / BACKUP_HISTORY_FILE


def load_history() -> list[dict]:
    path = history_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_history(history: list[dict]) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history[:200], indent=2), encoding="utf-8")


def add_history(record: dict) -> None:
    history = load_history()
    history.insert(0, record)
    save_history(history)


def create_backup(request=None) -> dict:
    source = live_db_path()
    if not source.exists():
        raise BackupError("Live database file was not found.")
    folder = get_backup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = folder / f"vendor_accounts_backup_{timestamp}.db"
    metadata_path = folder / f"vendor_accounts_backup_{timestamp}.json"
    connection.close()
    shutil.copy2(source, backup_path)
    metadata = {
        "db_path": str(source),
        "backup_path": str(backup_path),
        "folder": str(folder),
        "timestamp": timestamp,
        "user_id": request.session.get("user_id") if request else None,
        "company_id": request.session.get("company_id") if request else None,
        "branch_id": request.session.get("current_branch_id") if request else None,
        "file_size": backup_path.stat().st_size,
        "status": "SUCCESS",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    add_history({"metadata_path": str(metadata_path), **metadata})
    apply_retention(folder)
    return metadata


def apply_retention(folder: Path, keep=30) -> None:
    backups = sorted(folder.glob("vendor_accounts_backup_*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_file in backups[keep:]:
        try:
            old_file.unlink()
            meta = old_file.with_suffix(".json")
            if meta.exists():
                meta.unlink()
        except OSError:
            continue


def validate_backup_file(path_value: str) -> dict:
    if not path_value:
        raise BackupError("Select a backup database file.")
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise BackupError("Selected backup file was not found.")
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise BackupError("Backup file must be a .db, .sqlite, or .sqlite3 file.")
    try:
        with sqlite3.connect(str(path)) as db:
            found = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error as exc:
        raise BackupError(f"Selected file is not a readable SQLite database: {exc}")
    missing = sorted(CORE_TABLES - found)
    if missing:
        raise BackupError(f"Backup is missing required tables: {', '.join(missing)}.")
    return {"path": str(path), "file_size": path.stat().st_size, "tables": sorted(found)}


def safety_backup_before_restore() -> Path:
    source = live_db_path()
    folder = get_backup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = folder / f"safety_before_restore_{timestamp}.db"
    connection.close()
    shutil.copy2(source, target)
    return target


def restore_backup(path_value: str) -> dict:
    validation = validate_backup_file(path_value)
    source = Path(validation["path"])
    target = live_db_path()
    safety = safety_backup_before_restore()
    connection.close()
    shutil.copy2(source, target)
    return {"restored_from": str(source), "live_db": str(target), "safety_backup": str(safety)}
