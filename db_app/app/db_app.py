from __future__ import annotations

from pathlib import Path

from app.config import DATABASE_FILE_NAME, DEFAULT_DATA_DIR, DEFAULT_DB_PATH
from app.database.connection import database_status, get_connection
from app.database.initializer import initialize_database
from app.database.resetter import reset_database
from app.logger import AppLogger
from app.services.reset_database_service import reset_database_for_new_client


class VendorAccountsDBAppController:
    def __init__(self, logger: AppLogger) -> None:
        self.logger = logger
        self.database_folder = DEFAULT_DATA_DIR
        self.database_path = DEFAULT_DB_PATH

    def set_database_folder(self, folder: str | Path) -> Path:
        self.database_folder = Path(folder)
        self.database_path = self.database_folder / DATABASE_FILE_NAME
        self.logger.info(f"Selected database path: {self.database_path}")
        return self.database_path

    def create_database(self) -> None:
        self.logger.info("Creating database schema and seed records.")
        initialize_database(self.database_path)
        self.logger.info("Database created and initialized successfully.")

    def reset_database(self) -> None:
        self.logger.info("Resetting database.")
        reset_database(self.database_path)
        self.logger.info("Database reset and initialized successfully.")

    def prepare_database_for_new_client(self, keep_logs: bool = False) -> dict[str, object]:
        self.logger.info("Preparing database for new client deployment.")
        result = reset_database_for_new_client(self.database_path, keep_logs=keep_logs)
        self.logger.info(
            f"Pre-client reset completed. cleaned={len(result['tables_cleaned'])}, backup={result['backup_path']}"
        )
        return result

    def check_status(self) -> dict[str, object]:
        status = database_status(self.database_path)
        self.logger.info(
            f"Database status: exists={status['exists']}, tables={status['tables']}, size={status['size_bytes']} bytes."
        )
        return status

    def connect(self):
        if not self.database_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.database_path}")
        return get_connection(self.database_path)

    def default_company_and_branch(self) -> tuple[int, int | None]:
        with self.connect() as connection:
            company = connection.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
            if not company:
                raise RuntimeError("No company record exists. Create or initialize the database first.")
            branch = connection.execute(
                "SELECT id FROM branches WHERE company_id = ? AND is_head_office = 1 ORDER BY id LIMIT 1",
                (company["id"],),
            ).fetchone()
            return company["id"], branch["id"] if branch else None
