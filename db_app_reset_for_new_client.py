from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_APP = ROOT / "db_app"
if str(DB_APP) not in sys.path:
    sys.path.insert(0, str(DB_APP))

from app.services.reset_database_service import reset_database_for_new_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare/reset a SQLite database for a new client deployment.")
    parser.add_argument("--db", required=True, help="Path to SQLite database file.")
    parser.add_argument("--keep-logs", action="store_true", help="Keep audit/log tables instead of clearing them.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting data.")
    args = parser.parse_args()

    result = reset_database_for_new_client(args.db, keep_logs=args.keep_logs, dry_run=args.dry_run)
    print("Prepare Database for New Client")
    print(f"Database: {Path(args.db).expanduser().resolve()}")
    print(f"Dry run: {result['dry_run']}")
    print(f"Success: {result['success']}")
    print(f"Backup: {result['backup_path'] or 'not created for dry-run'}")
    print("")
    print("Rows to delete/deleted:")
    for table, count in result["rows_deleted_by_table"].items():
        print(f"- {table}: {count}")
    print("")
    print(f"Tables cleaned: {len(result['tables_cleaned'])}")
    print(f"Tables skipped: {len(result['tables_skipped'])}")
    if result["errors"]:
        print("Errors:")
        for error in result["errors"]:
            print(f"- {error}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
