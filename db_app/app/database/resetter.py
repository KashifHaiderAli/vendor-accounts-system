from __future__ import annotations

from pathlib import Path

from app.database.connection import get_connection
from app.database.schema import create_schema
from app.database.seed_data import seed_defaults


def reset_database(database_path: str | Path) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with get_connection(path) as connection:
        create_schema(connection)
        seed_defaults(connection, path)

