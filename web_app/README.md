# Corporate Supplier Accounts System Web App

This folder contains the Phase 2 Django web application foundation for the Corporate Supplier Accounts System.

The web app uses Django Templates, Bootstrap 5, and the SQLite database created by the existing DB App. It does not create or modify database tables in this phase.

## Setup

Create and activate a virtual environment:

```powershell
cd web_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Database Path

The app reads the SQLite database path from:

```powershell
$env:VENDOR_ACCOUNTS_DB_PATH = "C:\VendorAccounts\data\vendor_accounts.db"
```

If the environment variable is missing, the app defaults to:

```text
C:\VendorAccounts\data\vendor_accounts.db
```

The database must be created first using the DB App.

## Run

```powershell
python manage.py runserver
```

Open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/login/

## Phase Notes

Phase 2 provides only the Django project foundation, shared layout, dashboard placeholder, login placeholder, and module route placeholders.

Authentication, permissions, custom user table integration, and license validation will be implemented in Phase 3. Business forms, quotation/invoice/purchase screens, and reports will be added in later phases.
