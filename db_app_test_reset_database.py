from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_APP = ROOT / "db_app"
if str(DB_APP) not in sys.path:
    sys.path.insert(0, str(DB_APP))

from app.config import DEFAULT_DB_PATH  # noqa: E402
from app.database.initializer import initialize_database  # noqa: E402
from app.services.reset_database_service import reset_database_for_new_client, table_exists  # noqa: E402
from app.utils.date_utils import now_iso, today_iso  # noqa: E402


SETUP_TABLES = ["companies", "branches", "users", "user_roles", "permissions", "role_permissions", "accounts"]
CLEAN_TABLES = ["customers", "suppliers", "item_services", "sales_invoices", "supplier_purchases", "journal_entries", "stock_movements"]


def count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def insert_sample_data(db_path: Path) -> None:
    now = now_iso()
    today = today_iso()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        company_id = conn.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()["id"]
        branch_id = conn.execute("SELECT id FROM branches ORDER BY id LIMIT 1").fetchone()["id"]
        user_id = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()["id"]
        account_id = conn.execute("SELECT id FROM accounts ORDER BY id LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO customers (company_id, branch_id, customer_code, company_name, is_active, created_by_id, updated_by_id, created_at, updated_at)
            VALUES (?, ?, 'AUTO-TEST-CUST', 'AUTO-TEST Customer', 1, ?, ?, ?, ?)
            """,
            (company_id, branch_id, user_id, user_id, now, now),
        )
        customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO suppliers (company_id, branch_id, supplier_code, supplier_name, is_active, created_by_id, updated_by_id, created_at, updated_at)
            VALUES (?, ?, 'AUTO-TEST-SUP', 'AUTO-TEST Supplier', 1, ?, ?, ?, ?)
            """,
            (company_id, branch_id, user_id, user_id, now, now),
        )
        supplier_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO item_services (company_id, branch_id, item_code, item_name, item_type, is_active, created_by_id, updated_by_id, created_at, updated_at)
            VALUES (?, ?, 'AUTO-TEST-ITEM', 'AUTO-TEST Item', 'Product', 1, ?, ?, ?, ?)
            """,
            (company_id, branch_id, user_id, user_id, now, now),
        )
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO journal_entries (company_id, branch_id, entry_no, entry_date, reference_type, description, created_by_id, created_at, updated_at)
            VALUES (?, ?, 'AUTO-TEST-JE', ?, 'AUTO-TEST', 'AUTO-TEST Journal', ?, ?, ?)
            """,
            (company_id, branch_id, today, user_id, now, now),
        )
        journal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO journal_entry_lines (journal_entry_id, account_id, debit, credit, description, created_at, updated_at) VALUES (?, ?, 10, 0, 'AUTO-TEST', ?, ?)",
            (journal_id, account_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO sales_invoices (company_id, branch_id, invoice_no, invoice_date, customer_id, grand_total, balance_amount, status, journal_entry_id, created_by_id, updated_by_id, created_at, updated_at)
            VALUES (?, ?, 'AUTO-TEST-INV', ?, ?, 10, 10, 'Printed', ?, ?, ?, ?, ?)
            """,
            (company_id, branch_id, today, customer_id, journal_id, user_id, user_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO supplier_purchases (company_id, branch_id, purchase_no, purchase_date, supplier_id, grand_total, balance_amount, status, journal_entry_id, created_by_id, updated_by_id, created_at, updated_at)
            VALUES (?, ?, 'AUTO-TEST-PUR', ?, ?, 10, 10, 'Posted', ?, ?, ?, ?, ?)
            """,
            (company_id, branch_id, today, supplier_id, journal_id, user_id, user_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO stock_movements (company_id, branch_id, item_service_id, movement_date, movement_type, source_type, source_no, quantity_in, created_by_id, created_at)
            VALUES (?, ?, ?, ?, 'purchase_in', 'AUTO-TEST', 'AUTO-TEST-STOCK', 1, ?, ?)
            """,
            (company_id, branch_id, item_id, today, user_id, now),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    tmp_parent = ROOT / "web_app" / "test_reports" / "db_app_reset_tests"
    tmp_dir = tmp_parent / f"vendor_reset_test_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        test_db = tmp_dir / "reset_test.db"
        initialize_database(test_db)
        insert_sample_data(test_db)

        dry = reset_database_for_new_client(test_db, dry_run=True)
        if not dry["success"] or dry["rows_deleted_by_table"].get("customers", 0) < 1:
            print("FAIL: dry-run did not detect sample rows.")
            return 1

        result = reset_database_for_new_client(test_db)
        if not result["success"] or not result["backup_path"] or not Path(result["backup_path"]).exists():
            print("FAIL: reset did not complete with backup.")
            return 1

        conn = sqlite3.connect(str(test_db))
        try:
            for table in SETUP_TABLES:
                if table_exists(conn, table) and count(conn, table) < 1:
                    print(f"FAIL: required setup table is empty: {table}")
                    return 1
            for table in CLEAN_TABLES:
                if table_exists(conn, table) and count(conn, table) != 0:
                    print(f"FAIL: business table not cleaned: {table}")
                    return 1
        finally:
            conn.close()

        print("PASS: dry-run detected rows")
        print(f"PASS: backup created at {result['backup_path']}")
        print("PASS: required setup remains")
        print("PASS: business/demo data removed")
        print("PASS")
        return 0
    finally:
        for _ in range(5):
            try:
                shutil.rmtree(tmp_dir)
                break
            except PermissionError:
                time.sleep(0.2)
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
