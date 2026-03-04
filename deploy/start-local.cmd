@echo off
chcp 65001 >nul
title Midscene Local Service

echo ============================================
echo   Midscene 本地服务启动器
echo   手机通过 USB 直连，无需 ADB 隧道
echo ============================================
echo.

REM --- 配置 ---
set SERVER=101.32.242.14
set PROJECT_DIR=%~dp0..

REM --- 1. 确认手机连接 ---
echo [1/4] 检查手机连接...
adb devices | findstr /R "device$" >nul
if errorlevel 1 (
    echo ✗ 未检测到手机，请确认 USB 连接和 USB 调试已开启
    pause
    exit /b 1
)
echo ✓ 手机已连接
echo.

REM --- 2. ADB 端口转发（AutoX.js）---
echo [2/4] 设置 ADB 端口转发...
adb forward tcp:9500 tcp:9500
echo ✓ AutoX.js 端口转发 9500 已建立
echo.

REM --- 3. 启动 Midscene 服务 ---
echo [3/4] 启动 Midscene 服务 (:9401)...
cd /d "%PROJECT_DIR%"

REM 检查 .env 文件
if not exist .env (
    echo ✗ 未找到 .env 文件
    echo   请执行: copy .env.example .env 并填入 DashScope API Key
    pause
    exit /b 1
)

REM 后台启动 Midscene
start "Midscene" /min bun run src/midscene-client.ts
timeout /t 3 /nobreak >nul

REM 健康检查
curl -s http://localhost:9401/health | findstr "success" >nul
if errorlevel 1 (
    echo ✗ Midscene 启动失败，查看窗口日志
    pause
    exit /b 1
)
echo ✓ Midscene 服务已启动
echo.

REM --- 4. SSH 隧道 ---
echo [4/4] 建立 SSH 隧道到云服务器...
echo   转发: 9401(Midscene) + 9501(AutoX.js)
echo   密码: 见部署文档
echo.
echo *** 此窗口保持打开，关闭则隧道断开 ***
echo.

ssh -R 9401:127.0.0.1:9401 -R 9501:127.0.0.1:9500 %SERVER%
