from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


KEEP_TABLES = {
    "companies",
    "branches",
    "users",
    "user_roles",
    "permissions",
    "role_permissions",
    "user_branches",
    "license_records",
    "numbering_settings",
    "company_settings",
    "tax_settings",
    "accounts",
    "system_pages",
    "app_state",
    "app_settings",
    "sqlite_sequence",
}


CLEAN_TABLES_IN_ORDER = [
    "customer_receipt_allocations",
    "supplier_payment_allocations",
    "quotation_items",
    "customer_confirmation_items",
    "delivery_challan_items",
    "sales_invoice_items",
    "sales_return_items",
    "supplier_purchase_items",
    "purchase_return_items",
    "service_contract_items",
    "stock_adjustment_items",
    "expense_voucher_items",
    "journal_entry_lines",
    "stock_movements",
    "stock_adjustments",
    "sales_returns",
    "purchase_returns",
    "customer_receipts",
    "supplier_payments",
    "sales_invoices",
    "supplier_purchases",
    "delivery_challans",
    "customer_confirmations",
    "quotations",
    "service_contracts",
    "expense_vouchers",
    "journal_entries",
    "customers",
    "suppliers",
    "item_services",
    "user_activity_log",
    "audit_logs",
    "print_logs",
    "export_logs",
]


LOG_TABLES = {
    "user_activity_log",
    "audit_logs",
    "print_logs",
    "export_logs",
}


TEST_PATTERNS = ["AUTO-", "AUTO TEST", "AUTO-TEST", "SMOKE", "MOCK", "DEMO", "TEST"]


def create_pre_reset_backup(db_path: str | Path) -> Path:
    source = Path(db_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"pre_client_reset_{timestamp}.db"
    shutil.copy2(source, backup_path)
    return backup_path


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def get_existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()]


def reset_database_for_new_client(db_path: str | Path, keep_logs: bool = False, dry_run: bool = False) -> dict[str, object]:
    path = Path(db_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database file not found: {path}")

    backup_path = None if dry_run else create_pre_reset_backup(path)
    result = {
        "success": False,
        "dry_run": dry_run,
        "backup_path": str(backup_path) if backup_path else None,
        "tables_cleaned": [],
        "rows_deleted_by_table": {},
        "tables_skipped": [],
        "tables_kept": sorted(KEEP_TABLES),
        "errors": [],
    }

    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        existing = get_existing_tables(conn)
        clean_tables = [table for table in CLEAN_TABLES_IN_ORDER if table in existing]
        if keep_logs:
            clean_tables = [table for table in clean_tables if table not in LOG_TABLES]

        for table in CLEAN_TABLES_IN_ORDER:
            if table not in existing:
                result["tables_skipped"].append(table)

        if dry_run:
            for table in clean_tables:
                result["rows_deleted_by_table"][table] = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                result["tables_cleaned"].append(table)
            result["success"] = True
            return result

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            for table in clean_tables:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                conn.execute(f'DELETE FROM "{table}"')
                result["rows_deleted_by_table"][table] = count
                result["tables_cleaned"].append(table)

            if table_exists(conn, "sqlite_sequence") and clean_tables:
                placeholders = ",".join("?" for _ in clean_tables)
                conn.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", clean_tables)

            conn.commit()
            result["success"] = True
        except Exception as exc:
            conn.rollback()
            result["errors"].append(str(exc))
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.close()
    return result
