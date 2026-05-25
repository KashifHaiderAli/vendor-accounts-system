from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "db_app"))

from app.db_app import VendorAccountsDBAppController
from app.logger import AppLogger


def main():
    logger = AppLogger()
    controller = VendorAccountsDBAppController(logger)
    local_path = Path(r"C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db")
    selected = controller.set_database_file(local_path)
    checks = [
        ("selects exact LocalVersion DB", selected == local_path),
        ("folder tracks LocalVersion data folder", controller.database_folder == local_path.parent),
        ("does not force vendor_accounts.db", controller.database_path.name == "vendor_accounts_local.db"),
    ]
    status = controller.check_status()
    checks.append(("status checks exact path", status["path"] == str(local_path)))

    failed = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print(("PASS" if ok else "FAIL") + " - " + label)
    if failed:
        raise SystemExit("FAIL: " + ", ".join(failed))
    print("PASS")


if __name__ == "__main__":
    main()
