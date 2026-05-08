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

## Environment File

The app automatically loads environment values from:

```text
web_app/.env
```

Use `web_app/.env.example` as the template for local setup. The local `.env` file is ignored by Git so each machine can keep its own database path and development secret.

Current local example:

```text
VENDOR_ACCOUNTS_DB_PATH=D:\Development\vendor-accounts-system\data\vendor_accounts.db
DJANGO_SECRET_KEY=local-dev-secret-key-change-later
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

If `VENDOR_ACCOUNTS_DB_PATH` is missing, the app falls back to the repo-level database path:

```text
vendor-accounts-system/data/vendor_accounts.db
```

The database must be created first using the DB App. The web app will not create or alter the database schema.

## Run With Python

```powershell
python manage.py runserver
```

## Run With Script

From `web_app/` on Windows:

```powershell
.\run_web_app.bat
```

The script activates the repo virtual environment at `..\venv` when it exists, then starts Django at `127.0.0.1:8000`.

Git Bash users can run:

```bash
./run_web_app_gitbash.sh
```

Open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/login/

## Phase Notes

Phase 2 provides only the Django project foundation, shared layout, dashboard placeholder, login placeholder, and module route placeholders.

Authentication, permissions, custom user table integration, and license validation will be implemented in Phase 3. Business forms, quotation/invoice/purchase screens, and reports will be added in later phases.
