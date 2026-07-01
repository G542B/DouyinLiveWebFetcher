@echo off
setlocal

set "PYTHON_VERSION=3.11.9"
set "PYTHON_EMBED_URL=https://repo.huaweicloud.com/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "GET_PIP_URL=https://raw.githubusercontent.com/pypa/get-pip/main/public/get-pip.py"
set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn"

set "PROJECT_DIR=E:\LQ\dyproject"
if not exist "%PROJECT_DIR%" set "PROJECT_DIR=%~dp0.."
set "PYTHON_DIR=%PROJECT_DIR%\python"
set "ZIP_FILE=%PROJECT_DIR%\python-embed.zip"

echo ============================================
echo   Python Embedded Setup Script
echo   Python %PYTHON_VERSION% Embedded (amd64)
echo ============================================
echo.

if exist "%PYTHON_DIR%\python.exe" (
    echo Found existing Python embedded environment
    "%PYTHON_DIR%\python.exe" --version 2>nul
    echo.
    echo Rebuild? (Y/N)
    choice /c YN
    if errorlevel 2 (
        echo Skip rebuild, using existing environment
        goto install_deps
    )
    echo Removing old Python environment...
    rmdir /s /q "%PYTHON_DIR%"
)

echo [1/5] Downloading Python %PYTHON_VERSION% embedded...
if not exist "%ZIP_FILE%" (
    echo Downloading from %PYTHON_EMBED_URL%...
    powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYTHON_EMBED_URL%' -OutFile '%ZIP_FILE%' -TimeoutSec 300"
    if not exist "%ZIP_FILE%" (
        echo ERROR: Download failed!
        pause
        exit /b 1
    )
)

echo [2/5] Extracting Python embedded...
if exist "%PYTHON_DIR%" rmdir /s /q "%PYTHON_DIR%"
mkdir "%PYTHON_DIR%"
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%PYTHON_DIR%' -Force"
if not exist "%PYTHON_DIR%\python.exe" (
    echo ERROR: Extraction failed!
    pause
    exit /b 1
)

echo [3/5] Configuring Python embedded...
for %%f in ("%PYTHON_DIR%\python*._pth") do (
    echo python311.zip> "%%f"
    echo .>> "%%f"
    echo Lib>> "%%f"
    echo Lib\site-packages>> "%%f"
    echo import site>> "%%f"
    echo Configured %%f
)
if not exist "%PYTHON_DIR%\Lib" mkdir "%PYTHON_DIR%\Lib"
if not exist "%PYTHON_DIR%\Lib\site-packages" mkdir "%PYTHON_DIR%\Lib\site-packages"

echo [4/5] Installing pip...
set "GET_PIP_FILE=%PYTHON_DIR%\get-pip.py"
"%PYTHON_DIR%\python.exe" -m pip --version >nul 2>&1
if not errorlevel 1 (
    echo pip is already installed
    goto pip_done
)

echo Downloading get-pip.py from %GET_PIP_URL%...
powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile '%GET_PIP_FILE%' -TimeoutSec 120"
if not exist "%GET_PIP_FILE%" (
    echo ERROR: Download get-pip.py failed!
    pause
    exit /b 1
)

"%PYTHON_DIR%\python.exe" "%GET_PIP_FILE%" --no-warn-script-location -i "%PIP_INDEX_URL%" --trusted-host "%PIP_TRUSTED_HOST%"
if errorlevel 1 (
    echo ERROR: pip install failed!
    pause
    exit /b 1
)

:pip_done
echo [5/5] Installing Python dependencies...
if not exist "%PROJECT_DIR%\requirements.txt" (
    echo ERROR: requirements.txt not found
    pause
    exit /b 1
)

"%PYTHON_DIR%\python.exe" -m pip install -r "%PROJECT_DIR%\requirements.txt" --no-warn-script-location -i "%PIP_INDEX_URL%" --trusted-host "%PIP_TRUSTED_HOST%"
if errorlevel 1 (
    echo [ERROR] Python dependencies install failed!
    pause
    exit /b 1
)

REM 安装 backend (Embedding) 依赖
if exist "%PROJECT_DIR%\backend\requirements.txt" (
    echo.
    echo [INFO] Installing backend Embedding dependencies...
    "%PYTHON_DIR%\python.exe" -m pip install -r "%PROJECT_DIR%\backend\requirements.txt" --no-warn-script-location -i "%PIP_INDEX_URL%" --trusted-host "%PIP_TRUSTED_HOST%"
    if errorlevel 1 (
        echo [WARN] Backend dependencies install failed! Embedding features will be unavailable.
    )
)

:install_deps
echo.
echo ============================================
echo   Python embedded environment ready!
echo   Path: %PYTHON_DIR%
echo ============================================
"%PYTHON_DIR%\python.exe" --version
echo.
echo Playwright browsers will be installed on first use
echo To manually install Playwright browsers, run:
echo   "%PYTHON_DIR%\python.exe" -m playwright install chromium
echo.

if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" 2>nul
pause
