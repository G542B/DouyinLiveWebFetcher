@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo    Playwright 环境检测脚本
echo ========================================
echo.

REM 1. 检测 Python
set "PYTHON_EXE="
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
) else (
    where python3 >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python3"
    )
)

if "!PYTHON_EXE!"=="" (
    echo [错误] 未检测到 Python，请先安装 Python 3.7+
    echo 下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/4] 检测 Python 版本...
!PYTHON_EXE! --version
if !errorlevel! neq 0 (
    echo [错误] Python 执行失败
    pause
    exit /b 1
)
echo.

echo [2/4] 检测 Playwright 模块...
!PYTHON_EXE! -c "from playwright.sync_api import sync_playwright; print('Playwright 模块已安装')" 2>nul
if !errorlevel! neq 0 (
    echo [警告] Playwright 模块未安装，正在安装...
    !PYTHON_EXE! -m pip install playwright
    if !errorlevel! neq 0 (
        echo [错误] Playwright 安装失败，请检查网络
        pause
        exit /b 1
    )
)
echo.

echo [3/4] 检测 Chromium 浏览器...
!PYTHON_EXE! -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); b.close(); p.stop(); print('Chromium 已就绪')" 2>nul
if !errorlevel! neq 0 (
    echo [警告] Chromium 未安装或启动失败，正在下载...
    echo 提示: 下载约 150MB，请耐心等待
    echo.
    !PYTHON_EXE! -m playwright install chromium
    if !errorlevel! neq 0 (
        echo.
        echo [错误] Chromium 下载失败，请检查网络或代理设置
        echo.
        echo 如果你使用代理，可以尝试:
        echo   set HTTP_PROXY=http://your-proxy:port
        echo   set HTTPS_PROXY=http://your-proxy:port
        echo   %~nx0
        pause
        exit /b 1
    )
)
echo.

echo [4/4] 检查浏览器路径...
set "BROWSERS_PATH=%LOCALAPPDATA%\ms-playwright"
if exist "!BROWSERS_PATH!" (
    echo 浏览器路径: !BROWSERS_PATH!
    dir /b "!BROWSERS_PATH!" 2>nul | findstr /R "chromium" >nul
    if !errorlevel! equ 0 (
        echo [OK] 检测到 Chromium 目录
    ) else (
        echo [警告] 路径存在但未找到 chromium-* 目录
    )
) else (
    echo [警告] 路径不存在: !BROWSERS_PATH!
    echo 提示: 首次运行应用时会自动创建
)
echo.

echo ========================================
echo    Playwright 环境就绪 ✓
echo ========================================
echo.
echo 提示: 启动应用后，弹幕输出自动化的"打开网站"功能
echo       首次冷启动可能需要 30-60 秒，请耐心等待。
echo.
pause
endlocal
