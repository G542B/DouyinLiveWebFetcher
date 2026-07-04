@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================
REM   DouyinLiveWebFetcher - One-Click Release Builder
REM   Builds a complete offline-installable Windows package
REM   Includes: Embedded Python, Wheels, Model, Playwright, Frontend, Electron
REM
REM   Usage:
REM     build_release.bat          Interactive mode (pauses for confirmation)
REM     build_release.bat /auto    Non-interactive mode (skip all pauses)
REM ============================================

cd /d "%~dp0"

set "AUTO_MODE=0"
if /i "%~1"=="/auto" set "AUTO_MODE=1"

set "PROJECT_DIR=%CD%"
set "PYTHON_DIR=%PROJECT_DIR%\python"
set "WHEELS_DIR=%PROJECT_DIR%\wheels"
set "MODEL_DIR=%PROJECT_DIR%\backend\models\bge-small-zh-v1.5"
set "BROWSERS_DIR=%PROJECT_DIR%\playwright-browsers"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"
set "ELECTRON_DIR=%PROJECT_DIR%\electron"
set "DIST_DIR=%ELECTRON_DIR%\dist_build"

echo ============================================
echo   DouyinLiveWebFetcher Release Builder
echo   Project: %PROJECT_DIR%
echo ============================================
echo.
echo This script will:
echo   1. Check environment (Node.js, Python)
echo   2. Setup embedded Python 3.11
echo   3. Download offline wheels (Embedding deps)
echo   4. Download BGE-small-zh-v1.5 model
echo   5. Download Playwright Chromium
echo   6. Build frontend (Vite production)
echo   7. Install Electron dependencies
echo   8. Package as Windows NSIS installer
echo.
if "%AUTO_MODE%"=="0" (
    echo Press any key to start, or Ctrl+C to cancel...
    pause >nul
)
echo.

REM ===== Step 0: Environment check =====
echo [0/8] Checking environment...
where node >nul 2>&1
if errorlevel 1 (
    echo [X] Node.js not found. Please install Node.js 16+ first.
    echo     https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do set "NODE_VER=%%v"
echo     Node.js: %NODE_VER%

where python >nul 2>&1
if errorlevel 1 (
    echo [X] System Python not found. Please install Python 3.10+ first.
    echo     https://www.python.org/downloads/
    echo     (Required only for building, the final package uses embedded Python)
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do set "PY_VER=%%v"
echo     System Python: %PY_VER%
echo.

REM ===== Step 1: Setup embedded Python =====
echo ============================================
echo   [1/8] Setting up embedded Python 3.11
echo ============================================
if exist "%PYTHON_DIR%\python.exe" (
    echo [INFO] Embedded Python already exists, skip.
    "%PYTHON_DIR%\python.exe" --version
) else (
    if "%AUTO_MODE%"=="1" (
        call "%PROJECT_DIR%\scripts\setup_embedded_python_simple.bat" /auto
    ) else (
        call "%PROJECT_DIR%\scripts\setup_embedded_python_simple.bat"
    )
    if not exist "%PYTHON_DIR%\python.exe" (
        echo [X] Embedded Python setup failed!
        if "%AUTO_MODE%"=="0" pause
        exit /b 1
    )
)
echo.

REM ===== Step 2: Download offline wheels =====
echo ============================================
echo   [2/8] Downloading offline wheels
echo ============================================
set "WHEELS_COUNT=0"
if exist "%WHEELS_DIR%" (
    for /f %%a in ('dir /b "%WHEELS_DIR%\*.whl" 2^>nul ^| find /c /v ""') do set "WHEELS_COUNT=%%a"
)
if !WHEELS_COUNT! gtr 0 (
    echo [INFO] Wheels already downloaded (!WHEELS_COUNT! files), skip.
) else (
    if "%AUTO_MODE%"=="1" (
        call "%PROJECT_DIR%\scripts\download_wheels.bat" /auto
    ) else (
        call "%PROJECT_DIR%\scripts\download_wheels.bat"
    )
    set "WHEELS_COUNT=0"
    if exist "%WHEELS_DIR%" (
        for /f %%a in ('dir /b "%WHEELS_DIR%\*.whl" 2^>nul ^| find /c /v ""') do set "WHEELS_COUNT=%%a"
    )
    if !WHEELS_COUNT! equ 0 (
        echo [X] Wheels download failed!
        if "%AUTO_MODE%"=="0" pause
        exit /b 1
    )
    echo [INFO] Downloaded !WHEELS_COUNT! wheel files.
)
echo.

REM ===== Step 3: Download BGE model =====
echo ============================================
echo   [3/8] Ensuring BGE-small-zh-v1.5 model
echo ============================================
if exist "%MODEL_DIR%\config.json" (
    if exist "%MODEL_DIR%\pytorch_model.bin" (
        echo [INFO] Model already exists, skip.
        dir /b "%MODEL_DIR%" 2>nul
    ) else (
        call "%PROJECT_DIR%\scripts\download_model.bat" /auto
    )
) else (
    call "%PROJECT_DIR%\scripts\download_model.bat" /auto
)
if not exist "%MODEL_DIR%\config.json" (
    echo [X] Model setup failed!
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
echo.

REM ===== Step 4: Download Playwright Chromium =====
echo ============================================
echo   [4/8] Downloading Playwright Chromium
echo ============================================
set "CHROMIUM_FOUND=0"
if exist "%BROWSERS_DIR%" (
    for /d %%D in ("%BROWSERS_DIR%\chromium-*") do set "CHROMIUM_FOUND=1"
)
if "!CHROMIUM_FOUND!"=="1" (
    echo [INFO] Playwright Chromium already exists, skip.
    dir /b "%BROWSERS_DIR%" 2>nul
) else (
    call "%PROJECT_DIR%\scripts\download_playwright_browsers.bat" /auto
)
echo.

REM ===== Step 5: Install frontend dependencies =====
echo ============================================
echo   [5/8] Installing frontend dependencies
echo ============================================
cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo Running npm install...
    call npm install
    if errorlevel 1 (
        echo [X] npm install failed!
        cd /d "%PROJECT_DIR%"
        if "%AUTO_MODE%"=="0" pause
        exit /b 1
    )
) else (
    echo [INFO] node_modules exists, skip npm install.
)
echo.

REM ===== Step 6: Build frontend =====
echo ============================================
echo   [6/8] Building frontend (Vite production)
echo ============================================
cd /d "%FRONTEND_DIR%"
call npm run build
if errorlevel 1 (
    echo [X] Frontend build failed!
    cd /d "%PROJECT_DIR%"
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo [X] Frontend dist/index.html not found after build!
    cd /d "%PROJECT_DIR%"
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
echo [INFO] Frontend build OK.
cd /d "%PROJECT_DIR%"
echo.

REM ===== Step 7: Install Electron dependencies =====
echo ============================================
echo   [7/8] Installing Electron dependencies
echo ============================================
cd /d "%ELECTRON_DIR%"
if not exist "node_modules" (
    echo Running npm install...
    call npm install
    if errorlevel 1 (
        echo [X] Electron npm install failed!
        cd /d "%PROJECT_DIR%"
        if "%AUTO_MODE%"=="0" pause
        exit /b 1
    )
) else (
    echo [INFO] electron node_modules exists, skip npm install.
)
echo.

REM ===== Step 8: Build NSIS installer =====
echo ============================================
echo   [8/8] Building Windows NSIS installer
echo ============================================
cd /d "%ELECTRON_DIR%"

REM Clean old dist
if exist "dist_build" rmdir /s /q "dist_build"

echo Running electron-builder...
call npm run build:win
if errorlevel 1 (
    echo [X] electron-builder failed!
    cd /d "%PROJECT_DIR%"
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)
cd /d "%PROJECT_DIR%"
echo.

REM ===== Done =====
echo ============================================
echo   BUILD COMPLETE
echo ============================================
echo.
echo Installer location:
if exist "%DIST_DIR%" (
    dir /b "%DIST_DIR%\*.exe" 2>nul
    echo.
    echo Full path: %DIST_DIR%
)
echo.
echo The installer is a self-contained NSIS .exe that includes:
echo   - Embedded Python 3.11 runtime
echo   - All Python dependencies (offline wheels)
echo   - BGE-small-zh-v1.5 Embedding model
echo   - Playwright Chromium browser
echo   - Pre-built Vue frontend
echo   - Electron shell
echo.
echo End users just need to:
echo   1. Double-click the .exe installer
echo   2. Follow the setup wizard
echo   3. Launch the app from Start Menu / Desktop shortcut
echo.
echo No internet connection required after install.
echo.
if "%AUTO_MODE%"=="0" pause
endlocal & exit /b 0
