# Run the Web App

From the repository root:

```powershell
cd web_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:VENDOR_ACCOUNTS_DB_PATH = "C:\VendorAccounts\data\vendor_accounts.db"
python manage.py runserver
```

Open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/login/

The database file must already exist. Create it first from the DB App.
