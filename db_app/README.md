# VendorAccountsDBApp

VendorAccountsDBApp is a Tkinter desktop utility for creating, resetting, initializing, and managing the local SQLite database for the Corporate Supplier Accounts System.

This project is intentionally limited to the database/admin utility. It does not create the Django web application, customer screens, quotation screens, invoice screens, or final commercial licensing security.

The database schema includes sales return and purchase return tables from day one so later application screens can support returns, linked source invoices/purchases, journal entries, branch reporting, and role-based permissions without reshaping the core database.

## Run

```powershell
cd db_app
python main.py
```

The default database file name is `vendor_accounts.db`.

Default local database path:

```text
D:\Development\vendor-accounts-system\data\vendor_accounts.db
```

The app lets you browse to another local folder before creating the database.

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
