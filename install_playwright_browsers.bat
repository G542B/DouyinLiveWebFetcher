@echo off
echo ========================================
echo   Install Playwright Browsers
echo ========================================
echo.

REM Try to find Python
set PYTHON_EXE=
if exist "python\python.exe" (
    set PYTHON_EXE=python\python.exe
    echo [1/3] Using project Python: %PYTHON_EXE%
) else (
    echo [1/3] Checking system Python...
    python --version >nul 2>&1
    if errorlevel 1 (
        echo Python not found! Please run install.bat first
        pause
        exit /b 1
    )
    set PYTHON_EXE=python
)

echo.
echo [2/3] Checking Playwright module...
%PYTHON_EXE% -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo Playwright module not found, installing...
    %PYTHON_EXE% -m pip install playwright
    if errorlevel 1 (
        echo Failed to install Playwright module!
        pause
        exit /b 1
    )
)

echo.
echo [3/3] Downloading Chromium browser...
echo This may take a few minutes, please wait...
echo.
%PYTHON_EXE% -m playwright install chromium
if errorlevel 1 (
    echo.
    echo Failed to download Chromium!
    echo Please check network or run: %PYTHON_EXE% -m playwright install chromium
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Installation complete!
echo ========================================
echo.
echo You can now use the automated output feature!
echo.
pause
