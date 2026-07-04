@echo off
setlocal enabledelayedexpansion

set "PYTHON_VERSION=3.11.9"
set "PYTHON_EMBED_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "PYTHON_EMBED_URL_MIRROR=https://repo.huaweicloud.com/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "GET_PIP_URL_MIRROR=https://raw.githubusercontent.com/pypa/get-pip/main/public/get-pip.py"
set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn"

REM Use script location to robustly resolve project root (avoid hardcoded path)
set "PROJECT_DIR=%~dp0.."
set "PYTHON_DIR=%PROJECT_DIR%\python"
set "ZIP_FILE=%PROJECT_DIR%\python-embed.zip"

echo ============================================
echo   Python Embedded Setup Script
echo   Python %PYTHON_VERSION% Embedded (amd64)
echo ============================================
echo.

if exist "%PYTHON_DIR%\python.exe" (
    echo [INFO] Found existing Python embedded environment
    "%PYTHON_DIR%\python.exe" --version 2>nul
    echo.
    choice /c YN /m "Rebuild? (Y/N)"
    if errorlevel 2 (
        echo [INFO] Skip rebuild, using existing environment
        goto :install_deps
    )
    echo [INFO] Removing old Python environment...
    rmdir /s /q "%PYTHON_DIR%"
)

echo [1/5] Downloading Python %PYTHON_VERSION% embedded...
set "ZIP_VALID=0"
if exist "%ZIP_FILE%" (
    echo [INFO] Zip file exists, validating...
    powershell -Command "try { Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::OpenRead('%ZIP_FILE%').Dispose(); exit 0 } catch { exit 1 }"
    if !errorlevel! equ 0 (
        set "ZIP_VALID=1"
        echo [INFO] Zip file is valid, skip download
    ) else (
        echo [WARN] Zip file is corrupted, will re-download
        del /f /q "%ZIP_FILE%" 2>nul
    )
)
if !ZIP_VALID! equ 0 goto :download_python_zip_start
goto :download_python_zip_done

:download_python_zip_start
set "ZIP_MAX_RETRY=3"
set "ZIP_RETRY=0"
set "CURRENT_PYTHON_URL=%PYTHON_EMBED_URL%"
:download_python_zip
set /a "ZIP_RETRY+=1"
setlocal disabledelayedexpansion
echo [INFO] Downloading %CURRENT_PYTHON_URL% (attempt %ZIP_RETRY%/%ZIP_MAX_RETRY%) ...
powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%CURRENT_PYTHON_URL%' -OutFile '%ZIP_FILE%' -TimeoutSec 300"
endlocal
if not exist "%ZIP_FILE%" (
    echo [WARN] Download failed on attempt %ZIP_RETRY%
    if %ZIP_RETRY% lss %ZIP_MAX_RETRY% (
        if %ZIP_RETRY% equ 2 (
            echo [INFO] Switching to mirror: %PYTHON_EMBED_URL_MIRROR%
            set "CURRENT_PYTHON_URL=%PYTHON_EMBED_URL_MIRROR%"
        )
        goto :download_python_zip
    )
    echo [ERROR] Download failed after %ZIP_MAX_RETRY% attempts! Check network connection.
    pause
    exit /b 1
)
:download_python_zip_done

echo [2/5] Extracting Python embedded...
if exist "%PYTHON_DIR%" (
    echo [INFO] Cleaning existing python directory...
    rmdir /s /q "%PYTHON_DIR%"
)
mkdir "%PYTHON_DIR%"
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%PYTHON_DIR%' -Force"
if not exist "%PYTHON_DIR%\python.exe" (
    echo [ERROR] Extraction failed!
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
    echo [INFO] Configured %%f
)

if not exist "%PYTHON_DIR%\Lib" mkdir "%PYTHON_DIR%\Lib"
if not exist "%PYTHON_DIR%\Lib\site-packages" mkdir "%PYTHON_DIR%\Lib\site-packages"

echo [4/5] Installing pip...
set "GET_PIP_FILE=%PYTHON_DIR%\get-pip.py"
set "PIP_INSTALLED=0"
"%PYTHON_DIR%\python.exe" -m pip --version >nul 2>&1
if !errorlevel! equ 0 (
    echo [INFO] pip is already installed
    set "PIP_INSTALLED=1"
    goto :pip_done
)

set "GET_PIP_MAX_RETRY=3"
set "GET_PIP_RETRY=0"
set "CURRENT_GET_PIP_URL=%GET_PIP_URL%"

:download_get_pip
if exist "%GET_PIP_FILE%" del /f /q "%GET_PIP_FILE%" 2>nul
set /a "GET_PIP_RETRY+=1"
setlocal disabledelayedexpansion
echo [INFO] Downloading get-pip.py (attempt %GET_PIP_RETRY%/%GET_PIP_MAX_RETRY%) from %CURRENT_GET_PIP_URL%
powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%CURRENT_GET_PIP_URL%' -OutFile '%GET_PIP_FILE%' -TimeoutSec 120"
endlocal
if not exist "%GET_PIP_FILE%" (
    echo [WARN] Download get-pip.py failed on attempt %GET_PIP_RETRY%
    if %GET_PIP_RETRY% lss %GET_PIP_MAX_RETRY% (
        if %GET_PIP_RETRY% equ 2 (
            echo [INFO] Switching to GitHub mirror: %GET_PIP_URL_MIRROR%
            set "CURRENT_GET_PIP_URL=%GET_PIP_URL_MIRROR%"
        )
        goto :download_get_pip
    )
    echo [ERROR] Download get-pip.py failed after %GET_PIP_MAX_RETRY% attempts!
    echo [INFO] You can manually download get-pip.py from %GET_PIP_URL% or %GET_PIP_URL_MIRROR% and save to %GET_PIP_FILE%
    pause
    exit /b 1
)
for %%A in ("%GET_PIP_FILE%") do set "GET_PIP_SIZE=%%~zA"
if %GET_PIP_SIZE% lss 1000 (
    echo [WARN] Downloaded get-pip.py is too small (%GET_PIP_SIZE% bytes), maybe corrupted
    del /f /q "%GET_PIP_FILE%" 2>nul
    if %GET_PIP_RETRY% lss %GET_PIP_MAX_RETRY% (
        if %GET_PIP_RETRY% equ 2 (
            echo [INFO] Switching to GitHub mirror: %GET_PIP_URL_MIRROR%
            set "CURRENT_GET_PIP_URL=%GET_PIP_URL_MIRROR%"
        )
        goto :download_get_pip
    )
    echo [ERROR] get-pip.py download keeps failing!
    pause
    exit /b 1
)

"%PYTHON_DIR%\python.exe" "%GET_PIP_FILE%" --no-warn-script-location -i "%PIP_INDEX_URL%" --trusted-host "%PIP_TRUSTED_HOST%"
if errorlevel 1 (
    echo [WARN] get-pip.py execution failed, deleting corrupted file...
    del /f /q "%GET_PIP_FILE%" 2>nul
    if %GET_PIP_RETRY% lss %GET_PIP_MAX_RETRY% goto :download_get_pip
    echo [ERROR] pip install failed after %GET_PIP_MAX_RETRY% attempts!
    pause
    exit /b 1
)

:pip_done

:install_deps
echo [5/5] Installing Python dependencies...
if not exist "%PROJECT_DIR%\requirements.txt" (
    echo [ERROR] requirements.txt not found
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
    echo [5.5/5] Installing backend Embedding dependencies...
    "%PYTHON_DIR%\python.exe" -m pip install -r "%PROJECT_DIR%\backend\requirements.txt" --no-warn-script-location -i "%PIP_INDEX_URL%" --trusted-host "%PIP_TRUSTED_HOST%"
    if errorlevel 1 (
        echo [WARN] Backend dependencies install failed! Embedding features will be unavailable.
        echo [WARN] You can retry later: %PYTHON_DIR%\python.exe -m pip install -r "%PROJECT_DIR%\backend\requirements.txt"
    )
)

echo.
echo ============================================
echo   Python embedded environment ready!
echo   Path: %PYTHON_DIR%
echo ============================================
"%PYTHON_DIR%\python.exe" --version
echo.
echo [INFO] Playwright browsers will be installed on first use
echo [INFO] To manually install Playwright browsers, run:
echo   %PYTHON_DIR%\python.exe -m playwright install chromium
echo.

if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" 2>nul

pause
