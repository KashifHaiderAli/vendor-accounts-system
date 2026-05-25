@echo off
setlocal

set APP_ROOT=C:\VendorAccounts\LocalVersion
set WEB_APP_DIR=%APP_ROOT%\web_app
set PYTHON_EXE=%APP_ROOT%\runtime\python\python.exe
set PYTHONPATH=%APP_ROOT%\web_app;%APP_ROOT%\runtime\python\Lib\site-packages

set VENDOR_ACCOUNTS_DB_PATH=C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
set ENABLE_TAX=False
set DJANGO_DEBUG=False
set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.0.125

if not exist "%VENDOR_ACCOUNTS_DB_PATH%" (
    echo Database file not found:
    echo %VENDOR_ACCOUNTS_DB_PATH%
    echo.
    echo Please create/copy database using DB App first.
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo Bundled Python runtime was not found:
    echo %PYTHON_EXE%
    echo.
    echo Please reinstall Vendor Accounts Web App - Local Version.
    pause
    exit /b 1
)

if not exist "%WEB_APP_DIR%\manage.py" (
    echo Web App manage.py was not found:
    echo %WEB_APP_DIR%\manage.py
    echo.
    echo Please reinstall Vendor Accounts Web App - Local Version.
    pause
    exit /b 1
)

cd /d "%WEB_APP_DIR%"

echo Refreshing static files...
"%PYTHON_EXE%" manage.py collectstatic --noinput --clear
if errorlevel 1 (
    echo Failed to refresh static files.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m waitress --listen=0.0.0.0:8001 config.wsgi:application
