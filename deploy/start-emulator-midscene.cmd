@echo off
chcp 65001 >nul
title 本地模拟器 + Midscene 全栈调试

echo ========================================
echo   模拟器 + Midscene + U2_Service
echo   全部本地运行，无需云服务器
echo ========================================
echo.

REM --- 配置 ---
set ADB=D:\learning\Open-AutoGLM-main\platform-tools\adb.exe
set PROJECT_DIR=%~dp0..

REM --- 1. 检查模拟器 ---
echo [1/5] 检查模拟器连接...
%ADB% devices 2>nul | findstr /R "emulator device$" >nul
if errorlevel 1 (
    echo X 没有检测到 Android 设备
    echo   请先启动 Android Studio 模拟器:
    echo   Android Studio → Virtual Device Manager → 启动模拟器
    echo.
    echo   或者连接实体手机（USB 调试已开启）
    pause
    exit /b 1
)
echo OK 设备已连接:
%ADB% devices
echo.

REM --- 2. 端口转发（AutoX.js）---
echo [2/5] 设置 ADB 端口转发 (AutoX.js 9500)...
%ADB% forward tcp:9500 tcp:9500
echo OK 端口转发 9500 已建立
echo.

REM --- 3. 检查 .env ---
echo [3/5] 检查环境配置...
cd /d "%PROJECT_DIR%"
if not exist .env (
    echo X 未找到 .env 文件
    echo   请执行: copy .env.example .env 并填入 DashScope API Key
    pause
    exit /b 1
)
echo OK .env 已就绪
echo.

REM --- 4. 启动 Midscene 服务 ---
echo [4/5] 启动 Midscene 服务 (:9401)...
cd /d "%PROJECT_DIR%"

REM 关闭已有的 Midscene 进程
taskkill /f /fi "WINDOWTITLE eq Midscene*" >nul 2>&1

REM 后台启动
start "Midscene Service" /min bun run src/midscene-client.ts
timeout /t 4 /nobreak >nul

REM 健康检查
curl -s http://localhost:9401/health | findstr "success" >nul
if errorlevel 1 (
    echo X Midscene 启动失败
    echo   检查 Midscene 窗口的日志
    pause
    exit /b 1
)
echo OK Midscene 服务已启动

REM 连接设备
echo     连接 Midscene 到模拟器...
curl -s -X POST http://localhost:9401/connect | findstr "success" >nul
if errorlevel 1 (
    echo X Midscene 连接设备失败
    echo   确认 adb devices 能看到设备
) else (
    echo OK Midscene 已连接设备
)
echo.

REM --- 5. 启动 U2_Service ---
echo [5/5] 启动 U2_Service (:9400)...
echo.
echo ========================================
echo   所有服务已启动:
echo   - Midscene:    http://localhost:9401
echo   - U2_Service:  http://localhost:9400
echo ========================================
echo.
echo   测试命令:
echo   curl http://localhost:9401/health
echo   curl -X POST http://localhost:9401/connect
echo   curl -X POST http://localhost:9401/ai/query -H "Content-Type: application/json" -d "{\"dataDemand\": \"屏幕上所有可见的文字\"}"
echo.
echo   按 Ctrl+C 停止 U2_Service
echo ========================================
echo.

set AUTOX_URL=http://localhost:9500
set MIDSCENE_URL=http://localhost:9401
cd /d "%PROJECT_DIR%\u2-server"
uv run uvicorn server:app --host 0.0.0.0 --port 9400
