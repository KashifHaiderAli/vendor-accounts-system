@echo off
setlocal

set APP_ROOT=C:\VendorAccounts\MainVersion
set WEB_APP_DIR=%APP_ROOT%\web_app
set PYTHON_EXE=%APP_ROOT%\runtime\python\python.exe
set PYTHONPATH=%APP_ROOT%\web_app;%APP_ROOT%\runtime\python\Lib\site-packages

set VENDOR_ACCOUNTS_DB_PATH=C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
set ENABLE_TAX=True
set DJANGO_DEBUG=False

if not exist "%PYTHON_EXE%" (
    echo Bundled Python runtime was not found:
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%WEB_APP_DIR%\manage.py" (
    echo Web App manage.py was not found:
    echo %WEB_APP_DIR%\manage.py
    pause
    exit /b 1
)

if not exist "%VENDOR_ACCOUNTS_DB_PATH%" (
    echo Database file not found:
    echo %VENDOR_ACCOUNTS_DB_PATH%
    echo.
    echo Please create/copy database using DB App first.
    pause
    exit /b 1
)

cd /d "%WEB_APP_DIR%"

"%PYTHON_EXE%" -c "import django; import waitress; import whitenoise; print('runtime ok')"
if errorlevel 1 (
    echo Runtime import check failed.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -c "import config; print('config ok')"
if errorlevel 1 (
    echo Web App config import failed.
    echo Check:
    echo C:\VendorAccounts\MainVersion\runtime\python\python313._pth
    pause
    exit /b 1
)

"%PYTHON_EXE%" manage.py check
if errorlevel 1 (
    echo manage.py check failed.
    pause
    exit /b 1
)

"%PYTHON_EXE%" manage.py collectstatic --noinput
if errorlevel 1 (
    echo collectstatic failed.
    pause
    exit /b 1
)

if not exist "%WEB_APP_DIR%\staticfiles\css\app.css" (
    echo Static CSS was not collected:
    echo %WEB_APP_DIR%\staticfiles\css\app.css
    pause
    exit /b 1
)

"%PYTHON_EXE%" manage.py test_license_page

pause
