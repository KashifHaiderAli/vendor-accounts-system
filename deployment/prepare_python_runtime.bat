@echo off
setlocal

set DEPLOYMENT_ROOT=%~dp0
set RUNTIME_DIR=%DEPLOYMENT_ROOT%python_runtime
set SOURCE_DIR=%DEPLOYMENT_ROOT%python_runtime_source
set DEFAULT_EMBED_ZIP=%DEPLOYMENT_ROOT%python_embed.zip
set REQUIREMENTS_FILE=%DEPLOYMENT_ROOT%..\web_app\requirements.txt

if "%PYTHON_EMBED_ZIP%"=="" set PYTHON_EMBED_ZIP=%DEFAULT_EMBED_ZIP%

if exist "%RUNTIME_DIR%" rmdir /s /q "%RUNTIME_DIR%"
mkdir "%RUNTIME_DIR%"

if exist "%SOURCE_DIR%\python.exe" (
    echo Copying portable Python source folder:
    echo %SOURCE_DIR%
    robocopy "%SOURCE_DIR%" "%RUNTIME_DIR%" /E /XD __pycache__ /XF *.pyc
    if errorlevel 8 exit /b 1
) else if exist "%PYTHON_EMBED_ZIP%" (
    echo Extracting Python embeddable zip:
    echo %PYTHON_EMBED_ZIP%
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%PYTHON_EMBED_ZIP%' -DestinationPath '%RUNTIME_DIR%' -Force"
    if errorlevel 1 exit /b 1
) else (
    echo ERROR: No portable Python source found.
    echo.
    echo Provide one of:
    echo 1. Folder: deployment\python_runtime_source\ with python.exe
    echo 2. Zip: deployment\python_embed.zip
    echo 3. Env var: PYTHON_EMBED_ZIP=C:\path\python-embedded-amd64.zip
    echo.
    echo Then rerun:
    echo deployment\prepare_python_runtime.bat
    exit /b 1
)

if not exist "%RUNTIME_DIR%\python.exe" (
    echo ERROR: python.exe was not found after runtime preparation.
    exit /b 1
)

mkdir "%RUNTIME_DIR%\Lib\site-packages" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$pths = Get-ChildItem -LiteralPath '%RUNTIME_DIR%' -Filter 'python*._pth'; foreach ($pth in $pths) { Set-Content -LiteralPath $pth.FullName -Value @('python313.zip', '.', 'Lib\site-packages', '..\..\web_app', 'import site') -Encoding ASCII }"

echo Installing web_app requirements into portable runtime site-packages...
python -m pip install --upgrade --target "%RUNTIME_DIR%\Lib\site-packages" -r "%REQUIREMENTS_FILE%" waitress whitenoise
if errorlevel 1 (
    echo ERROR: Failed to install packages into portable runtime.
    echo Make sure build machine has Python and pip available.
    exit /b 1
)

set PYTHONPATH=%RUNTIME_DIR%\Lib\site-packages
"%RUNTIME_DIR%\python.exe" -c "import django; import waitress; import whitenoise; print('runtime ok')"
if errorlevel 1 (
    echo ERROR: Runtime validation failed.
    exit /b 1
)

echo.
echo Portable runtime prepared:
echo %RUNTIME_DIR%
echo.
echo Note: config import is validated by deployment\main\build_main_web_package.bat
echo after the runtime is copied under MainVersion\runtime\python.
echo.
echo Next:
echo deployment\main\build_main_web_package.bat
pause
