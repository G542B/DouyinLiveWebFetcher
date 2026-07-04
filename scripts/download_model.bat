@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================
REM   Download BAAI/bge-small-zh-v1.5 model
REM   for offline use in packaged app
REM
REM   Usage: download_model.bat [/auto]
REM ============================================

set "AUTO_MODE=0"
if /i "%~1"=="/auto" set "AUTO_MODE=1"

set "PROJECT_DIR=%~dp0.."
set "MODEL_DIR=%PROJECT_DIR%\backend\models\bge-small-zh-v1.5"
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

REM Check if model already exists
if exist "%MODEL_DIR%\config.json" (
    if exist "%MODEL_DIR%\modules.json" (
        if exist "%MODEL_DIR%\sentence_bert_config.json" (
            if exist "%MODEL_DIR%\pytorch_model.bin" (
                echo [INFO] Model already exists at: %MODEL_DIR%
                echo [INFO] Skip download.
                goto :done
            )
        )
    )
)

echo ============================================
echo   Downloading BGE-small-zh-v1.5 model
echo   Target: %MODEL_DIR%
echo ============================================
echo.

REM Ensure huggingface-hub is installed
"!PYTHON_EXE!" -c "import huggingface_hub" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing huggingface-hub...
    "!PYTHON_EXE!" -m pip install huggingface-hub --no-warn-script-location -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    if errorlevel 1 (
        echo [ERROR] Failed to install huggingface-hub
        if "%AUTO_MODE%"=="0" pause
        exit /b 1
    )
)

REM Download model using huggingface_hub
echo [INFO] Starting download (this may take a few minutes)...
"!PYTHON_EXE!" -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='BAAI/bge-small-zh-v1.5', local_dir=r'%MODEL_DIR%', local_dir_use_symlinks=False)"
if errorlevel 1 (
    echo [ERROR] Model download failed!
    echo [INFO] You can manually download from: https://huggingface.co/BAAI/bge-small-zh-v1.5
    if "%AUTO_MODE%"=="0" pause
    exit /b 1
)

echo.
echo ============================================
echo   Model downloaded successfully!
echo   Path: %MODEL_DIR%
echo ============================================
dir /b "%MODEL_DIR%" 2>nul

:done
echo.
exit /b 0
