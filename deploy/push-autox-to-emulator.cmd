@echo off
REM ============================================
REM 推送 AutoJS 脚本到模拟器
REM ============================================

echo 推送 autox-server-v2.js 到模拟器...
adb push "%~dp0\..\autox\autox-server-v2.js" /sdcard/autox-server-v2.js
if errorlevel 1 (
    echo ❌ 推送失败，请确认模拟器已启动
    pause
    exit /b 1
)

echo ✅ 推送成功！
echo.
echo 接下来在模拟器里：
echo   1. 打开 AutoJS6
echo   2. 点 + → 导入 → 选择 autox-server-v2.js
echo   3. 点 ▶ 运行
echo.
pause
