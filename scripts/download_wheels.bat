@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================
REM   Download Embedding dependency wheel files
REM   for offline install in packaged app
REM
REM   IMPORTANT: Wheels must be compatible with
REM   the embedded Python 3.11, NOT the system Python.
REM ============================================

set "WHEELS_DIR=%~dp0..\wheels"
set "PYTHON_EXE="

REM Find any available Python (just for running pip download)
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
)

if "!PYTHON_EXE!"=="" (
    echo ERROR: Python not found. Please install Python first.
    pause
    exit /b 1
)

echo Using Python: !PYTHON_EXE!
"!PYTHON_EXE!" --version
echo.

REM Clean old wheels (they may be for wrong Python version)
if exist "!WHEELS_DIR!" (
    echo Cleaning old wheel files...
    del /q "!WHEELS_DIR!\*.whl" 2>nul
) else (
    mkdir "!WHEELS_DIR!"
)

echo ============================================
echo   Downloading wheels for Python 3.11 (cp311)
echo   Target: !WHEELS_DIR!
echo ============================================
echo.

set "REQ_FILE=%~dp0..\backend\requirements.txt"

if not exist "!REQ_FILE!" (
    echo ERROR: backend/requirements.txt not found at !REQ_FILE!
    pause
    exit /b 1
)

REM Common pip download flags for cp311-win_amd64 compatibility
set "PY_VER=--python-version 3.11 --implementation cp --abi cp311 --platform win_amd64 --only-binary=:all:"

REM Step 1: Download torch CPU version from PyTorch source
echo [1/2] Downloading torch CPU version for cp311...
"!PYTHON_EXE!" -m pip download "torch>=2.0.0" -d "!WHEELS_DIR!" --index-url https://download.pytorch.org/whl/cpu !PY_VER!
if errorlevel 1 (
    echo WARN: PyTorch CPU source failed, trying aliyun mirror...
    "!PYTHON_EXE!" -m pip download "torch>=2.0.0" -d "!WHEELS_DIR!" -i https://mirrors.aliyun.com/pypi/simple --trusted-host mirrors.aliyun.com !PY_VER!
)
if errorlevel 1 (
    echo WARN: Aliyun mirror also failed, trying default source...
    "!PYTHON_EXE!" -m pip download "torch>=2.0.0" -d "!WHEELS_DIR!" !PY_VER!
)
echo.

REM Step 2: Download remaining deps (pure Python wheels don't need platform flags)
echo [2/2] Downloading remaining dependencies for cp311...
"!PYTHON_EXE!" -m pip download -r "!REQ_FILE!" -d "!WHEELS_DIR!" --find-links "!WHEELS_DIR!" --python-version 3.11 --implementation cp --abi cp311 --platform win_amd64 --only-binary=:all: -i https://mirrors.aliyun.com/pypi/simple --trusted-host mirrors.aliyun.com
if errorlevel 1 (
    echo WARN: Some packages failed with strict platform, retrying with relaxed flags...
    "!PYTHON_EXE!" -m pip download -r "!REQ_FILE!" -d "!WHEELS_DIR!" --find-links "!WHEELS_DIR!" --python-version 3.11 -i https://mirrors.aliyun.com/pypi/simple --trusted-host mirrors.aliyun.com
)
if errorlevel 1 (
    echo WARN: Aliyun mirror failed, trying default source...
    "!PYTHON_EXE!" -m pip download -r "!REQ_FILE!" -d "!WHEELS_DIR!" --find-links "!WHEELS_DIR!" --python-version 3.11
)
echo.

echo ============================================
echo   Download complete! Wheel files:
echo ============================================
dir /b "!WHEELS_DIR!\*.whl" 2>nul
echo.
echo Verify: all .whl files should contain cp311 in filename.
echo If you see cp314 or other versions, they are incompatible!
echo.
pause
