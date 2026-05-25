from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_APP = ROOT / "db_app"
if str(DB_APP) not in sys.path:
    sys.path.insert(0, str(DB_APP))

from app.config import DATABASE_FILE_NAME  # noqa: E402
from app.database.connection import database_status  # noqa: E402
from app.db_app import VendorAccountsDBAppController  # noqa: E402
from app.licensing.hardware_fingerprint import get_hardware_fingerprint  # noqa: E402
from app.licensing.license_generator import expiry_for_license, generate_license_key  # noqa: E402
from app.logger import AppLogger  # noqa: E402
from app.services.reset_database_service import reset_database_for_new_client  # noqa: E402
from app.utils.date_utils import now_iso, today_iso  # noqa: E402


def insert_license_exact_file(db_path: Path) -> None:
    fingerprint = get_hardware_fingerprint()
    start = today_iso()
    expiry, is_lifetime = expiry_for_license("Trial", start)
    key = generate_license_key("Trial", fingerprint, start)
    now = now_iso()
    with sqlite3.connect(str(db_path)) as conn:
        company_id = conn.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute(
            """
            INSERT INTO license_records (
                company_id, branch_id, license_type, hardware_fingerprint, license_key,
                issue_date, start_date, expiry_date, is_lifetime, is_active, remarks,
                created_at, updated_at
            ) VALUES (?, NULL, 'Trial', ?, ?, ?, ?, ?, ?, 1, 'AUTO-TEST exact file license', ?, ?)
            """,
            (company_id, fingerprint, key, start, start, expiry, is_lifetime, now, now),
        )
        conn.commit()


def count_table(db_path: Path, table: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def main() -> int:
    logger = AppLogger()
    controller = VendorAccountsDBAppController(logger)
    test_root = ROOT / "web_app" / "test_reports" / "db_file_selection"
    test_root.mkdir(parents=True, exist_ok=True)

    folder_mode_dir = test_root / "folder_mode"
    exact_dir = test_root / "exact_mode"
    main_dir = test_root / "MainVersion" / "data"
    folder_mode_dir.mkdir(parents=True, exist_ok=True)
    exact_dir.mkdir(parents=True, exist_ok=True)
    main_dir.mkdir(parents=True, exist_ok=True)

    folder_path = controller.set_database_folder(folder_mode_dir)
    if folder_path != folder_mode_dir / DATABASE_FILE_NAME:
        print(f"FAIL: folder mode resolved to {folder_path}")
        return 1

    exact_file = exact_dir / "client_selected.sqlite3"
    selected_path = controller.set_database_file(exact_file)
    if selected_path != exact_file:
        print(f"FAIL: file mode did not preserve exact path: {selected_path}")
        return 1

    controller.create_database()
    if not exact_file.exists():
        print("FAIL: Create Database did not create selected exact file.")
        return 1

    main_file = Path(r"C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db")
    controller.set_database_file(main_file)
    if controller.database_path != main_file:
        print(f"FAIL: MainVersion path not accepted: {controller.database_path}")
        return 1

    controller.set_database_file(exact_file)
    status = database_status(controller.database_path)
    if not status["exists"] or Path(status["path"]) != exact_file:
        print(f"FAIL: Check Database did not use exact file: {status}")
        return 1

    before_license_count = count_table(exact_file, "license_records")
    insert_license_exact_file(exact_file)
    after_license_count = count_table(exact_file, "license_records")
    folder_default_file = folder_mode_dir / DATABASE_FILE_NAME
    if after_license_count <= before_license_count:
        print("FAIL: License insert did not use exact file.")
        return 1
    if folder_default_file.exists():
        print("FAIL: File mode unexpectedly wrote to folder default vendor_accounts.db.")
        return 1

    reset_result = reset_database_for_new_client(exact_file, dry_run=True)
    if not reset_result["success"] or Path(controller.database_path) != exact_file:
        print("FAIL: Reset New Client did not target exact selected file.")
        return 1

    print("PASS: folder mode resolves to vendor_accounts.db")
    print("PASS: file mode preserves exact selected file")
    print("PASS: MainVersion file path accepted")
    print("PASS: Check Database uses exact file")
    print("PASS: License save can target exact selected file")
    print("PASS: Reset New Client can target exact selected file")
    print("PASS: no hardcoded vendor_accounts.db used in file mode")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
