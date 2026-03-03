# 模拟器本地调试环境搭建

不需要实体手机、不需要隧道、不需要 USB 线。全部在本地 Windows 电脑上完成。

## 架构

```
server_autox.py:9400 → adb forward → 模拟器:9500 (AutoJS6)
mitmproxy:8080 ← 模拟器 WiFi 代理 ← App 流量
```

## 第1步：安装 Android Studio

1. 下载：https://developer.android.com/studio
2. 安装时勾选 "Android Virtual Device"
3. 安装完成后打开 Android Studio，等它下载 SDK（默认装到 `%LOCALAPPDATA%\Android\Sdk`）

## 第2步：创建模拟器 (AVD)

打开 Android Studio → More Actions → Virtual Device Manager → Create Device

选择配置：
- Device: **Pixel 7**（或任意手机，分辨率选 1080x2400 最佳）
- System Image: **API 30 (Android 11)** → 选 **Google APIs** 版本（不要选 Google Play 版，方便 root）
- 点 Download 下载镜像，然后 Next → Finish

## 第3步：启动模拟器并配置

```cmd
:: 启动模拟器（命令行方式，也可以在 Android Studio 里点启动）
%LOCALAPPDATA%\Android\Sdk\emulator\emulator -avd Pixel_7_API_30

:: 等模拟器完全启动后，确认 adb 能连上
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe devices
```

应该看到类似 `emulator-5554  device`。

## 第4步：安装 AutoJS6

1. 下载 AutoJS6 APK：https://github.com/niceSaber/AutoJs6/releases
   - 选最新版的 `AutoJs6-v7.x.x-arm64-v8a.apk`（模拟器用 x86_64 版本）
   - 注意：如果模拟器是 x86 架构，选 `x86_64` 版本；如果找不到，arm64 版本在大部分模拟器上也能跑（有 ARM 翻译层）

2. 安装：
```cmd
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe install AutoJs6-v7.x.x.apk
```

3. 在模拟器里打开 AutoJS6 → 设置 → 开启无障碍服务

## 第5步：推送并运行 autox-server-v2.js

```cmd
:: 推送脚本到模拟器
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe push autox\autox-server-v2.js /sdcard/Scripts/autox-server-v2.js

:: 在 AutoJS6 里：
:: 1. 点左上角菜单 → 文件 → 打开 /sdcard/Scripts/autox-server-v2.js
:: 2. 点运行按钮 ▶
```

## 第6步：端口转发 + 启动 server_autox

```cmd
:: 把模拟器的 9500 端口映射到本地
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe forward tcp:9500 tcp:9500

:: 测试 AutoJS 是否可达
curl -s -X POST http://localhost:9500/health

:: 启动 server_autox（在项目 u2-server 目录下）
set AUTOX_URL=http://localhost:9500
cd u2-server
uv run uvicorn server_autox:app --host 0.0.0.0 --port 9400
```

验证：
```cmd
curl -s http://localhost:9400/health
curl -s -X POST http://localhost:9400/screenshot
```

## 第7步：配置抓包（mitmproxy）

1. 安装 mitmproxy：
```cmd
pip install mitmproxy
```

2. 启动 mitmproxy：
```cmd
mitmweb --listen-port 8080
```
浏览器会自动打开 http://localhost:8081 查看抓包界面。

3. 模拟器设置代理：
   - 模拟器里：设置 → 网络和互联网 → WiFi → 长按已连接的网络 → 修改网络
   - 代理：手动
   - 主机名：`10.0.2.2`（这是模拟器访问宿主机的特殊 IP）
   - 端口：`8080`

4. 安装 CA 证书（HTTPS 抓包需要）：
   - 模拟器浏览器打开 `http://mitm.it`
   - 下载 Android 证书
   - 设置 → 安全 → 加密与凭据 → 安装证书

   如果 App 不信任用户证书（Android 7+），用 root 方式装系统证书：
```cmd
:: 获取 mitmproxy CA 证书
:: 证书在 %USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer

:: 转换格式并推送到系统证书目录
openssl x509 -inform PEM -subject_hash_old -in %USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem -noout
:: 假设输出 c8750f0d，则：
copy %USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem c8750f0d.0
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe root
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe remount
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe push c8750f0d.0 /system/etc/security/cacerts/
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe shell chmod 644 /system/etc/security/cacerts/c8750f0d.0
D:\learning\Open-AutoGLM-main\platform-tools\adb.exe reboot
```

## 日常使用

每次调试只需要：
1. 启动模拟器
2. 确认 AutoJS6 脚本在运行
3. `adb forward tcp:9500 tcp:9500`
4. `set AUTOX_URL=http://localhost:9500 && cd u2-server && uv run uvicorn server_autox:app --port 9400`
5. 如果要抓包：`mitmweb --listen-port 8080`

## 一键启动脚本

用 `deploy\start-emulator-debug.cmd` 一键启动（模拟器需要先手动打开）。
