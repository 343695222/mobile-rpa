@echo off
chcp 65001 >nul
echo 推送 autox-server-v2.js 到模拟器...

set ADB=D:\learning\Open-AutoGLM-main\platform-tools\adb.exe

%ADB% push "%~dp0\..\autox\autox-server-v2.js" /sdcard/Scripts/autox-server-v2.js
if errorlevel 1 (
    echo ❌ 推送失败，请确认模拟器已启动
) else (
    echo ✅ 脚本已推送到 /sdcard/Scripts/autox-server-v2.js
    echo    请在 AutoJS6 中打开并运行此脚本
)
pause
