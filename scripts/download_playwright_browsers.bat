@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================
REM   Download Playwright Chromium browser
REM   to project's playwright-browsers/ dir
REM   for offline use in packaged app
REM
REM   Usage: download_playwright_browsers.bat [/auto]
REM ============================================

set "AUTO_MODE=0"
if /i "%~1"=="/auto" set "AUTO_MODE=1"

set "PROJECT_DIR=%~dp0.."
set "BROWSERS_DIR=%PROJECT_DIR%\playwright-browsers"
set "PYTHON_EXE="

REM Prefer embedded Python, fall back to system Python
if exist "%PROJECT_DIR%\python\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%\python\python.exe"
) else (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if "!PYTHON_EXE!"=="" (
    echo [ERROR] Python not found. Please run setup_embedded_python.bat first.
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo Using Python: !PYTHON_EXE!
"!PYTHON_EXE!" --version
echo.

REM Ensure playwright is installed
"!PYTHON_EXE!" -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing playwright...
    "!PYTHON_EXE!" -m pip install playwright --no-warn-script-location -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    if errorlevel 1 (
        echo [ERROR] Failed to install playwright
        if "%AUTO_MODE%"=="0" pause
        exit /b 1
    )
)

REM Create target directory
if not exist "%BROWSERS_DIR%" mkdir "%BROWSERS_DIR%"

REM Check if Chromium already downloaded
set "CHROMIUM_FOUND=0"
for /d %%D in ("%BROWSERS_DIR%\chromium-*") do (
    set "CHROMIUM_FOUND=1"
)
if "!CHROMIUM_FOUND!"=="1" (
    echo [INFO] Playwright Chromium already exists at: %BROWSERS_DIR%
    dir /b "%BROWSERS_DIR%" 2>nul
    echo.
    echo [INFO] Skip download. To re-download, delete the directory first.
    goto :done
)

echo ============================================
echo   Downloading Playwright Chromium
echo   Target: %BROWSERS_DIR%
echo   This may take a few minutes (about 150 MB)...
echo ============================================
echo.

set "PLAYWRIGHT_BROWSERS_PATH=%BROWSERS_DIR%"
"!PYTHON_EXE!" -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Playwright Chromium download failed!
    echo [INFO] You can manually run: set PLAYWRIGHT_BROWSERS_PATH=%BROWSERS_DIR%
    echo          "!PYTHON_EXE!" -m playwright install chromium
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo ============================================
echo   Playwright Chromium downloaded successfully!
echo   Path: %BROWSERS_DIR%
echo ============================================
dir /b "%BROWSERS_DIR%" 2>nul

:done
echo.
exit /b 0
