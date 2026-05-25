# Vendor Accounts Web App - Local Version Deployment

LocalVersion is the non-tax/local vendor edition.

## Install Structure

```text
C:\VendorAccounts\LocalVersion\
C:\VendorAccounts\LocalVersion\web_app\
C:\VendorAccounts\LocalVersion\runtime\python\
C:\VendorAccounts\LocalVersion\data\
C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
C:\VendorAccounts\LocalVersion\backups\
C:\VendorAccounts\LocalVersion\logs\
```

## Environment

```bat
set VENDOR_ACCOUNTS_DB_PATH=C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
set ENABLE_TAX=False
set DJANGO_DEBUG=False
```

LocalVersion runs on port `8001`:

```text
http://127.0.0.1:8001/
```

Start command:

```bat
"C:\VendorAccounts\LocalVersion\runtime\python\python.exe" -m waitress --listen=0.0.0.0:8001 config.wsgi:application
```

The installer uses the same portable Python runtime pattern as MainVersion and patches `python*._pth` automatically:

```text
python313.zip
.
Lib\site-packages
..\..\web_app
import site
```

## Database and License

Use DB App -> Browse Database File or Use LocalVersion DB and select:

```text
C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
```

Generate and save a separate license for this LocalVersion database. MainVersion and LocalVersion must not share one SQLite file.

## Build

```bat
deployment\prepare_python_runtime.bat
deployment\local\build_local_web_package.bat
```

Then compile:

```text
deployment\local\VendorAccountsWebApp_Local_Setup.iss
```

Installer output:

```text
VendorAccountsWebApp_Local_Setup.exe
```
