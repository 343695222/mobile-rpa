@echo off
chcp 65001 >nul
echo ========================================
echo   模拟器调试环境 一键启动
echo ========================================

set ADB=D:\learning\Open-AutoGLM-main\platform-tools\adb.exe

:: 检查 adb 连接
echo.
echo [1/4] 检查模拟器连接...
%ADB% devices | findstr "emulator" >nul
if errorlevel 1 (
    echo ❌ 没有检测到模拟器，请先启动 Android Studio 模拟器
    echo    打开 Android Studio → Virtual Device Manager → 启动模拟器
    pause
    exit /b 1
)
echo ✅ 模拟器已连接

:: 端口转发
echo.
echo [2/4] 设置端口转发 9500...
%ADB% forward tcp:9500 tcp:9500
echo ✅ 端口转发已设置

:: 测试 AutoJS
echo.
echo [3/4] 测试 AutoJS 连接...
curl -s -X POST http://localhost:9500/health >nul 2>&1
if errorlevel 1 (
    echo ⚠️  AutoJS 未响应，请确认：
    echo    1. 模拟器里 AutoJS6 已打开
    echo    2. autox-server-v2.js 脚本正在运行
    echo    继续启动 server_autox...
) else (
    echo ✅ AutoJS 已连接
)

:: 启动 server_autox
echo.
echo [4/4] 启动 server_autox (端口 9400)...
echo      按 Ctrl+C 停止
echo ========================================
set AUTOX_URL=http://localhost:9500
cd /d %~dp0\..\u2-server
uv run uvicorn server_autox:app --host 0.0.0.0 --port 9400
