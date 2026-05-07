from pathlib import Path

APP_NAME = "VendorAccountsDBApp"
WINDOW_TITLE = "Vendor Accounts DB App"
SYSTEM_NAME = "Corporate Supplier Accounts System"
DATABASE_FILE_NAME = "vendor_accounts.db"
DATABASE_PASSWORD_HINT = "infoline"

APP_DIR = Path(__file__).resolve().parent
DB_APP_ROOT = APP_DIR.parent
REPOSITORY_ROOT = DB_APP_ROOT.parent
PROJECT_ROOT = DB_APP_ROOT
DEFAULT_DATA_DIR = REPOSITORY_ROOT / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / DATABASE_FILE_NAME

WINDOW_SIZE = "1200x720"
