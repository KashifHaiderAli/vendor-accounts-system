# VendorAccountsDBApp

VendorAccountsDBApp is a Tkinter desktop utility for creating, resetting, initializing, and managing the local SQLite database for the Corporate Supplier Accounts System.

This project is intentionally limited to the database/admin utility. It does not create the Django web application, customer screens, quotation screens, invoice screens, or final commercial licensing security.

The database schema includes sales return and purchase return tables from day one so later application screens can support returns, linked source invoices/purchases, journal entries, branch reporting, and role-based permissions without reshaping the core database.

## Run

```powershell
cd db_app
python main.py
```

The development default database file name is `vendor_accounts.db`.

For MainVersion deployment, use:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

The future LocalVersion will use:

```text
C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
```

Default local database path:

```text
D:\Development\vendor-accounts-system\data\vendor_accounts.db
```

The app lets you browse to another local folder before creating the database. Folder mode keeps the development behavior and resolves to:

```text
selected folder\vendor_accounts.db
```

For deployment, use Database tab -> Browse Database File and select the exact SQLite file used by the Web App.

MainVersion must select:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

LocalVersion must select:

```text
C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
```

Do not save the license into `vendor_accounts.db` unless the Web App is also using `vendor_accounts.db`.
MainVersion and LocalVersion use separate SQLite files and separate `license_records` rows. Generate one license for the MainVersion DB and another license for the LocalVersion DB.

## Workflow

1. Run the DB App.
2. Login using DB App credentials:
   - Username: `admin`
   - Password: `infoline`
3. Create the database.
4. The placeholder company and Head Office branch are created automatically.
5. The default web app admin user is created automatically:
   - Username: `admin`
   - Password: `mdnuniball`
6. Edit company setup.
7. Add extra branches if needed.
8. Add users if needed.
9. Generate a trial, annual, or lifetime license.

Before generating or saving a license, confirm the Database tab shows the same database file that the Web App uses through `VENDOR_ACCOUNTS_DB_PATH`.

## Prepare Database for New Client

Before deploying a standalone SQLite database for a new client, use the Database tab button:

```text
Prepare Database for New Client
```

This creates a backup first, then removes testing/demo/business transaction data while keeping company setup, branches, users, roles, permissions, chart of accounts, numbering, settings, and license records. The confirmation dialog requires typing `RESET`.

Command line usage is also available:

```powershell
python ..\db_app_reset_for_new_client.py --db "C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db" --dry-run
python ..\db_app_reset_for_new_client.py --db "C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db"
```

Test the reset flow:

```powershell
python ..\db_app_test_reset_database.py
python ..\db_app_test_database_file_selection.py
python ..\db_app_test_local_version_db.py
```

Full details are documented in `docs/db_app_new_client_reset.md`.

## DB App Login

The DB App login protects this desktop database utility only. It is separate from the future web app users table.

- Username: `admin`
- Password: `infoline`

The app closes after 3 failed login attempts.

## Default Web App Admin User

- Username: `admin`
- Password: `mdnuniball`
- Full name: `Master Admin`
- Role: `Master Admin`

Passwords are salted and hashed with Python standard-library `hashlib`. Plain text passwords are not stored.

## SQLite Password Note

The requested application-level database protection password value, `infoline`, is stored in `app_settings.database_password_hint`.

Standard SQLite does not provide real password encryption by default. This app does not pretend the database is encrypted. If real encrypted SQLite storage is required later, SQLCipher can be introduced and the connection layer can be replaced accordingly.

## Migration Notes

The schema is designed to stay PostgreSQL-friendly:

- Lowercase table and field names with underscores
- ISO text date and datetime fields
- `company_id`, `branch_id`, user audit fields, and role/permission tables for future cloud and multi-user support
- Explicit foreign keys and useful indexes
- Sales return and purchase return transaction tables linked to invoices, purchases, customers, suppliers, items, and journals

Version 1 targets a local SQLite database on a single PC for a single company with one or more branches and users.

## Dependencies

No external Python packages are required for the current DB App. It uses Python 3.11+ standard libraries only.
