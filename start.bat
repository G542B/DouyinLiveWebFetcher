@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

echo ========================================
echo   Douyin Live Danmaku - Start
echo ========================================
echo.

REM 切到 bat 所在目录，避免被外部 cwd 影响
cd /d "%~dp0"

echo [1/4] Checking Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Failed to install ROOT Python dependencies!
    echo     Please check the pip output above for the real error.
    echo     Common causes: network issue / mini_racer needs VS Build Tools / pip version too old.
    pause
    exit /b 1
)

echo.
echo [2/4] Checking backend (Embedding) dependencies...
pip install -r backend/requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Failed to install BACKEND Python dependencies!
    echo     torch / sentence-transformers are heavy. Check network & disk space.
    pause
    exit /b 1
)

echo.
echo [3/4] Checking frontend dependencies...
cd /d frontend
if not exist "node_modules" (
    echo     node_modules not found, running npm install...
    call npm install
    if errorlevel 1 (
        echo.
        echo [X] npm install failed! See output above.
        echo     Common causes: Node.js not installed / network / npm registry.
        cd /d "%~dp0"
        pause
        exit /b 1
    )
) else (
    echo     node_modules exists, skip npm install.
)

echo.
echo [4/4] Building frontend...
call npm run build
if errorlevel 1 (
    echo.
    echo [X] npm run build failed! See output above.
    cd /d "%~dp0"
    pause
    exit /b 1
)
cd /d "%~dp0"

echo.
echo ========================================
echo   Stopping previous service on :8000...
echo ========================================
echo.
set "KILLED=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo     Killing PID %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
    set "KILLED=1"
)
if "!KILLED!"=="1" timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   Starting service...
echo ========================================
echo.
echo     URL: http://localhost:8000
echo     Press Ctrl+C to stop.
echo.

python run.py --serve
set "RC=%errorlevel%"

echo.
if not "%RC%"=="0" (
    echo [X] python run.py --serve exited with code %RC%.
    echo     Check the traceback above. Common causes:
    echo       - Port 8000 still occupied
    echo       - Missing Python module (run: pip install -r requirements.txt)
    echo       - mini_racer / protobuf build error
)

endlocal & exit /b %RC%
