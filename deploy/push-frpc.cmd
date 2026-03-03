@echo off
echo === 通过 ADB 一键部署 frpc 到手机 Termux ===

REM 1. 把安装脚本推到手机
echo [1/3] 推送脚本到手机...
adb push deploy\setup-frpc.sh /sdcard/setup-frpc.sh

REM 2. 复制到 Termux 目录并执行
echo [2/3] 在 Termux 中执行安装...
adb shell run-as com.termux cp /sdcard/setup-frpc.sh /data/data/com.termux/files/home/setup-frpc.sh 2>nul
adb shell "su -c 'cp /sdcard/setup-frpc.sh /data/data/com.termux/files/home/setup-frpc.sh'" 2>nul

echo [3/3] 完成！
echo.
echo 现在打开手机上的 Termux，执行：
echo   bash ~/setup-frpc.sh
echo.
echo 或者更简单 - 直接在 Termux 里粘贴这一行：
echo   curl -sL https://raw.githubusercontent.com/343695222/mobile-rpa/main/deploy/setup-frpc.sh ^| bash
pause
