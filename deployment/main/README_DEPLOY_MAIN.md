# Vendor Accounts Web App - Main Version Deployment

MainVersion is the current TAX/main version and the required deployment folder/package name.

## Install Structure

```text
C:\VendorAccounts\MainVersion\
C:\VendorAccounts\MainVersion\web_app\
C:\VendorAccounts\MainVersion\runtime\
C:\VendorAccounts\MainVersion\runtime\python\
C:\VendorAccounts\MainVersion\runtime\python\python.exe
C:\VendorAccounts\MainVersion\runtime\python\Lib\
C:\VendorAccounts\MainVersion\runtime\python\Lib\site-packages\
C:\VendorAccounts\MainVersion\data\
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
C:\VendorAccounts\MainVersion\backups\
C:\VendorAccounts\MainVersion\logs\
```

The installer creates empty `data`, `backups`, and `logs` folders. It does not include the development SQLite database unless someone explicitly copies a prepared database into the package.

## Portable Python Runtime

The installer uses a portable Python runtime in:

```text
C:\VendorAccounts\MainVersion\runtime\python\
```

Do not copy a Windows virtual environment into the installer. Windows venv folders are not portable and can keep references to the development PC base interpreter, for example `C:\python3x\python.exe`.

The server does not need manual Python installation and does not need `pip install -r requirements.txt` after installation. Django, Waitress, WhiteNoise, and dependencies must already be present inside:

```text
deployment\python_runtime\Lib\site-packages\
```

The runtime `python*._pth` file is patched automatically during runtime preparation and package build. The packaged file contains:

```text
python313.zip
.
Lib\site-packages
..\..\web_app
import site
```

This lets the portable Python runtime import both installed packages and the Web App package without manual edits on the server.

## Environment

```bat
set VENDOR_ACCOUNTS_DB_PATH=C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
set ENABLE_TAX=True
set DJANGO_DEBUG=False
```

The Web App connects to the database using `VENDOR_ACCOUNTS_DB_PATH`.

If an older database file is named `vendor_accounts.db`, copy or rename it to:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

When using DB App for setup, reset, or license activation, use Browse Database File and select this exact file:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

Do not save the license into `vendor_accounts.db` unless the Web App is also configured to use `vendor_accounts.db`.

## Port

MainVersion runs on:

```text
8000
```

Open:

```text
http://127.0.0.1:8000/
```

## Start Command

`start_main_web.bat` runs:

```bat
"C:\VendorAccounts\MainVersion\runtime\python\python.exe" -m waitress --listen=0.0.0.0:8000 config.wsgi:application
```

## Build Package

First prepare the portable runtime:

```bat
deployment\prepare_python_runtime.bat
```

The prepare script expects either:

- `deployment\python_runtime_source\python.exe`, or
- `deployment\python_embed.zip`, or
- `PYTHON_EMBED_ZIP=C:\path\python-embedded-amd64.zip`

It installs `web_app\requirements.txt` plus `waitress` and `whitenoise` into `deployment\python_runtime\Lib\site-packages\` and validates:

```bat
deployment\python_runtime\python.exe -c "import django; import waitress; import whitenoise; print('runtime ok')"
```

The `config` import is validated after package build, because `..\..\web_app` is correct once Python is located under `MainVersion\runtime\python`.

Run:

```bat
deployment\main\build_main_web_package.bat
```

Then build the installer with Inno Setup:

```text
deployment\main\VendorAccountsWebApp_Main_Setup.iss
```

Installer output name:

```text
VendorAccountsWebApp_Main_Setup.exe
```

Display name:

```text
Vendor Accounts Web App - Main Version
```

## Static Files Troubleshooting

With `DJANGO_DEBUG=False`, Waitress does not serve Django static files by itself. This package uses WhiteNoise and collected static files.

If the app appears as plain text or without styling, open:

```text
http://127.0.0.1:8000/static/css/app.css
```

If that returns 404:

1. Run:

```bat
C:\VendorAccounts\MainVersion\test_installed_main_web.bat
```

2. Confirm runtime import works:

```bat
C:\VendorAccounts\MainVersion\runtime\python\python.exe -c "import whitenoise; print('whitenoise ok')"
C:\VendorAccounts\MainVersion\runtime\python\python.exe -c "import config; print('config ok')"
```

3. Confirm collected CSS exists:

```text
C:\VendorAccounts\MainVersion\web_app\staticfiles\css\app.css
```

`start_main_web.bat` automatically runs:

```bat
"%PYTHON_EXE%" manage.py collectstatic --noinput
```

when `staticfiles\css\app.css` is missing.

## Future LocalVersion

The future non-tax/local vendor version will use:

```text
C:\VendorAccounts\LocalVersion\
C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
Port: 8001
ENABLE_TAX=False
```
