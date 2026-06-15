@echo off
setlocal

set PACKAGE_ROOT=%~dp0package
set MAIN_ROOT=%PACKAGE_ROOT%\MainVersion
set WEB_APP_SOURCE=%~dp0..\..\web_app
set PORTABLE_RUNTIME_SOURCE=%~dp0..\python_runtime
set RUNTIME_PYTHON=%MAIN_ROOT%\runtime\python
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
    echo Validate with:
    echo %PORTABLE_RUNTIME_SOURCE%\python.exe -c "import django; import waitress; import whitenoise; print('runtime ok')"
    echo.
    echo Prepare it first:
    echo deployment\prepare_python_runtime.bat
    exit /b 1
)

if exist "%PACKAGE_ROOT%" rmdir /s /q "%PACKAGE_ROOT%"

mkdir "%MAIN_ROOT%\web_app"
mkdir "%RUNTIME_PYTHON%"
mkdir "%MAIN_ROOT%\data"
mkdir "%MAIN_ROOT%\backups"
mkdir "%MAIN_ROOT%\logs"
mkdir "%WEB_APP_SOURCE%\DigitalSignature" 2>nul

robocopy "%WEB_APP_SOURCE%" "%MAIN_ROOT%\web_app" /E /XD __pycache__ test_reports /XF *.pyc *.sqlite *.db DigitalSignature.png
if errorlevel 8 (
    echo ERROR: Failed to copy web_app.
    exit /b 1
)

if not exist "%MAIN_ROOT%\web_app\DigitalSignature" mkdir "%MAIN_ROOT%\web_app\DigitalSignature"

robocopy "%PORTABLE_RUNTIME_SOURCE%" "%RUNTIME_PYTHON%" /E /XD __pycache__ /XF *.pyc
if errorlevel 8 (
    echo ERROR: Failed to copy portable Python runtime.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$pths = Get-ChildItem -LiteralPath '%RUNTIME_PYTHON%' -Filter 'python*._pth'; foreach ($pth in $pths) { Set-Content -LiteralPath $pth.FullName -Value @('python313.zip', '.', 'Lib\site-packages', '..\..\web_app', 'import site') -Encoding ASCII }"

if not exist "%PACKAGE_PYTHON_EXE%" (
    echo ERROR: Package runtime python.exe was not copied:
    echo %PACKAGE_PYTHON_EXE%
    exit /b 1
)

set PYTHONPATH=%RUNTIME_PYTHON%\Lib\site-packages
"%PACKAGE_PYTHON_EXE%" -c "import django; import waitress; import whitenoise" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Packaged runtime validation failed.
    echo Expected Django, Waitress, and WhiteNoise inside:
    echo %RUNTIME_PYTHON%\Lib\site-packages
    exit /b 1
)

"%PACKAGE_PYTHON_EXE%" -c "import config; print('config ok')" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Packaged runtime cannot import web_app config.
    echo Check python*._pth contains:
    echo python313.zip
    echo .
    echo Lib\site-packages
    echo ..\..\web_app
    echo import site
    exit /b 1
)

copy "%~dp0start_main_web.bat" "%MAIN_ROOT%\start_main_web.bat"
copy "%~dp0open_firewall_port_8000.bat" "%MAIN_ROOT%\open_firewall_port_8000.bat"
copy "%~dp0test_installed_main_web.bat" "%MAIN_ROOT%\test_installed_main_web.bat"

if not exist "%MAIN_ROOT%\web_app\static\css\app.css" (
    echo ERROR: Package missing static CSS:
    echo %MAIN_ROOT%\web_app\static\css\app.css
    exit /b 1
)

if not exist "%MAIN_ROOT%\web_app\static\css\print.css" (
    echo ERROR: Package missing print CSS:
    echo %MAIN_ROOT%\web_app\static\css\print.css
    exit /b 1
)

if not exist "%MAIN_ROOT%\web_app\static\css\print_classic.css" (
    echo ERROR: Package missing classic print CSS:
    echo %MAIN_ROOT%\web_app\static\css\print_classic.css
    exit /b 1
)

if not exist "%MAIN_ROOT%\web_app\templates\sales\quotation_print_classic.html" (
    echo ERROR: Package missing classic quotation template:
    echo %MAIN_ROOT%\web_app\templates\sales\quotation_print_classic.html
    exit /b 1
)

if not exist "%MAIN_ROOT%\web_app\templates\sales\invoice_print_classic.html" (
    echo ERROR: Package missing classic invoice template:
    echo %MAIN_ROOT%\web_app\templates\sales\invoice_print_classic.html
    exit /b 1
)

if exist "%WEB_APP_SOURCE%\static\favicon.ico" if not exist "%MAIN_ROOT%\web_app\static\favicon.ico" (
    echo ERROR: Source favicon exists but was not copied:
    echo %MAIN_ROOT%\web_app\static\favicon.ico
    exit /b 1
)

echo.
echo MainVersion package build summary
echo ---------------------------------
echo Package path:
echo %MAIN_ROOT%
echo Web app copied: yes
echo app.css included: yes
echo print.css included: yes
echo print_classic.css included: yes
echo DigitalSignature folder included: yes
if exist "%MAIN_ROOT%\web_app\static\favicon.ico" (echo favicon.ico included: yes) else (echo favicon.ico included: no source file)
echo classic print templates included: yes
echo Portable Python runtime copied: yes
if exist "%RUNTIME_PYTHON%\python.exe" (
    echo python.exe found: yes
) else (
    echo python.exe found: no
)
set PYTHONPATH=%RUNTIME_PYTHON%\Lib\site-packages
"%RUNTIME_PYTHON%\python.exe" -c "import waitress" >nul 2>nul
if errorlevel 1 (echo waitress found: no) else (echo waitress found: yes)
"%RUNTIME_PYTHON%\python.exe" -c "import whitenoise" >nul 2>nul
if errorlevel 1 (echo whitenoise found: no) else (echo whitenoise found: yes)
echo Database included: no, by design
echo Development SQLite databases are not included. Copy/rename a prepared DB to:
echo C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
pause
