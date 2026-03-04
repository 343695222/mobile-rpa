@echo off
chcp 65001 >nul
title 本地 Midscene + frp → 云端

set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"

echo === 启动 Midscene + frp 隧道 ===
echo.

REM 杀掉已有进程
taskkill /f /fi "WINDOWTITLE eq Midscene*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq frpc*" >nul 2>&1

REM 修复 source-map bug
node -e "const fs=require('fs');const f='node_modules/source-map/lib/source-map-consumer.js';let c=fs.readFileSync(f,'utf8');c=c.replace('if (aNeedle[aColumnName] < 0)','if (aNeedle[aColumnName] < -1)');fs.writeFileSync(f,c);" 2>nul

REM 启动 Midscene（后台窗口）
start "Midscene Service" /min bun run src/midscene-client.ts
echo [1/3] Midscene 启动中...
timeout /t 4 /nobreak >nul

REM 连接模拟器
echo [2/3] 连接模拟器...
curl -s -X POST http://localhost:9401/connect | findstr "success" >nul
if errorlevel 1 (
    echo X 连接失败，确认模拟器已启动
) else (
    echo OK 模拟器已连接
)
echo.

REM 启动 frpc（前台运行，Ctrl+C 退出）
echo [3/3] 启动 frp 隧道 (本地:9401 → 云端:9401)
echo.
echo ========================================
echo   Midscene:  http://localhost:9401
echo   云端测试:  curl http://localhost:9401/health
echo   按 Ctrl+C 停止
echo ========================================
echo.
frpc -c deploy/frpc-local.toml
