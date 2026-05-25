@echo off
setlocal

set PACKAGE_ROOT=%~dp0package
set LOCAL_ROOT=%PACKAGE_ROOT%\LocalVersion
set WEB_APP_SOURCE=%~dp0..\..\web_app
set PORTABLE_RUNTIME_SOURCE=%~dp0..\python_runtime
set RUNTIME_PYTHON=%LOCAL_ROOT%\runtime\python
set PACKAGE_PYTHON_EXE=%RUNTIME_PYTHON%\python.exe

if not exist "%PORTABLE_RUNTIME_SOURCE%\python.exe" (
    echo ERROR: Portable Python runtime was not found.
    echo Expected:
    echo %PORTABLE_RUNTIME_SOURCE%\python.exe
    echo.
    echo Prepare it first:
    echo deployment\prepare_python_runtime.bat
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$pths = Get-ChildItem -LiteralPath '%PORTABLE_RUNTIME_SOURCE%' -Filter 'python*._pth'; foreach ($pth in $pths) { Set-Content -LiteralPath $pth.FullName -Value @('python313.zip', '.', 'Lib\site-packages', '..\..\web_app', 'import site') -Encoding ASCII }"

set PYTHONPATH=%PORTABLE_RUNTIME_SOURCE%\Lib\site-packages
"%PORTABLE_RUNTIME_SOURCE%\python.exe" -c "import django; import waitress; import whitenoise" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Portable runtime is missing Django, Waitress, or WhiteNoise.
    echo Prepare it first:
    echo deployment\prepare_python_runtime.bat
    exit /b 1
)

if exist "%PACKAGE_ROOT%" rmdir /s /q "%PACKAGE_ROOT%"

mkdir "%LOCAL_ROOT%\web_app"
mkdir "%RUNTIME_PYTHON%"
mkdir "%LOCAL_ROOT%\data"
mkdir "%LOCAL_ROOT%\backups"
mkdir "%LOCAL_ROOT%\logs"

robocopy "%WEB_APP_SOURCE%" "%LOCAL_ROOT%\web_app" /E /XD __pycache__ test_reports /XF *.pyc *.sqlite *.db
if errorlevel 8 exit /b 1

robocopy "%PORTABLE_RUNTIME_SOURCE%" "%RUNTIME_PYTHON%" /E /XD __pycache__ /XF *.pyc
if errorlevel 8 exit /b 1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$pths = Get-ChildItem -LiteralPath '%RUNTIME_PYTHON%' -Filter 'python*._pth'; foreach ($pth in $pths) { Set-Content -LiteralPath $pth.FullName -Value @('python313.zip', '.', 'Lib\site-packages', '..\..\web_app', 'import site') -Encoding ASCII }"

if not exist "%PACKAGE_PYTHON_EXE%" (
    echo ERROR: Package runtime python.exe was not copied:
    echo %PACKAGE_PYTHON_EXE%
    exit /b 1
)

set PYTHONPATH=%RUNTIME_PYTHON%\Lib\site-packages
"%PACKAGE_PYTHON_EXE%" -c "import django; import waitress; import whitenoise" >nul 2>nul
if errorlevel 1 exit /b 1

"%PACKAGE_PYTHON_EXE%" -c "import config; print('config ok')" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Packaged runtime cannot import web_app config.
    exit /b 1
)

copy "%~dp0start_local_web.bat" "%LOCAL_ROOT%\start_local_web.bat"
copy "%~dp0open_firewall_port_8001.bat" "%LOCAL_ROOT%\open_firewall_port_8001.bat"
copy "%~dp0test_installed_local_web.bat" "%LOCAL_ROOT%\test_installed_local_web.bat"

if not exist "%LOCAL_ROOT%\web_app\static\css\app.css" (
    echo ERROR: Package missing static CSS:
    echo %LOCAL_ROOT%\web_app\static\css\app.css
    exit /b 1
)

if not exist "%LOCAL_ROOT%\web_app\static\css\print_classic.css" (
    echo ERROR: Package missing classic print CSS:
    echo %LOCAL_ROOT%\web_app\static\css\print_classic.css
    exit /b 1
)

if not exist "%LOCAL_ROOT%\web_app\templates\sales\quotation_print_classic.html" (
    echo ERROR: Package missing classic quotation template:
    echo %LOCAL_ROOT%\web_app\templates\sales\quotation_print_classic.html
    exit /b 1
)

if not exist "%LOCAL_ROOT%\web_app\templates\sales\invoice_print_classic.html" (
    echo ERROR: Package missing classic invoice template:
    echo %LOCAL_ROOT%\web_app\templates\sales\invoice_print_classic.html
    exit /b 1
)

echo.
echo LocalVersion package build summary
echo ----------------------------------
echo Package path:
echo %LOCAL_ROOT%
echo Web app copied: yes
echo app.css included: yes
echo print_classic.css included: yes
echo classic print templates included: yes
echo Portable Python runtime copied: yes
echo Database included: no, by design
echo Copy/create a prepared DB to:
echo C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
pause
