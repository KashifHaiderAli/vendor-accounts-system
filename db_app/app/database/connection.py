from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def database_status(database_path: str | Path) -> dict[str, object]:
    path = Path(database_path)
    if not path.exists():
        return {"exists": False, "path": str(path), "size_bytes": 0, "tables": 0}
    with get_connection(path) as connection:
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "tables": table_count,
    }

