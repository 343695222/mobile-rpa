# OpenClaw 移动端自动化插件 — 部署指南

> 本文档覆盖 **新增组件** 的部署：U2_Service（Python FastAPI）、AutoX.js、frp 隧道、数据采集器。
> 基础环境（ADB、Bun、SSH 隧道）请参考项目根目录的 [DEPLOY.md](../DEPLOY.md)。

---

## 环境信息

| 项目 | 值 |
|------|-----|
| 云服务器 | 腾讯云 101.32.242.14 (OpenCloudOS 9) |
| 登录 | root / `3,jyBg!Pc5%A2` |
| 手机设备 ID | a394960e (PJZ110) |
| 本地 Windows 项目 | D:\abnjd |
| 云端项目路径 | ~/.openclaw/workspace/skills/mobile-rpa |
| ADB 云端路径 | /opt/adb |
| GLM API Key | bbbeb98f39904758a4168fa1228fc33e.XyTbD6d7SNcqMJKa |
| GLM 模型 | glm-4.6v（付费版，非 flash） |

### 端口一览

| 服务 | 端口 | 运行位置 |
|------|------|---------|
| U2_Service (FastAPI) | 9400 | 云服务器 |
| AutoX_Service | 9500 | 手机 |
| AutoX_Service (frp 映射) | 9501 | 云服务器 localhost |
| frp 控制通道 | 7000 | 云服务器 |
| frp Web 管理面板 | 7500 | 云服务器 (admin/admin123) |
| ADB SSH 隧道 | 5037 | 云服务器 (反向隧道) |

---

## 一、云服务器部署

> 以下操作均在云服务器 (101.32.242.14) 上以 root 用户执行。
> OpenCloudOS 9 基于 CentOS/RHEL，使用 `dnf` 包管理器。

### 1.1 安装 uv（Python 环境管理）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

### 1.2 安装 Python 依赖

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server

# uv sync 会自动创建虚拟环境并安装 pyproject.toml 中的所有依赖
uv sync
```

依赖列表（来自 `u2-server/pyproject.toml`）：
- fastapi>=0.115
- uvicorn>=0.34
- uiautomator2>=3
- httpx>=0.28
- pillow>=11

### 1.3 启动 U2_Service

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server

# 前台运行（调试用）
uv run uvicorn server:app --host 0.0.0.0 --port 9400

# 后台运行（生产用）
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
```

验证服务启动：
```bash
curl http://localhost:9400/health
# 应返回: {"success":true,"message":"U2 Service is running","data":null}
```

### 1.4 安装并启动 frp 服务端

```bash
# 下载 frp（以 0.61.1 为例，根据实际最新版本调整）
cd /tmp
curl -LO https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_amd64.tar.gz
tar -xzf frp_0.61.1_linux_amd64.tar.gz
cp frp_0.61.1_linux_amd64/frps /usr/local/bin/
chmod +x /usr/local/bin/frps
```

使用项目中的配置文件启动：
```bash
cd ~/.openclaw/workspace/skills/mobile-rpa

# 前台运行（调试用）
frps -c deploy/frps.toml

# 后台运行（生产用）
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
```

frp 服务端配置（`deploy/frps.toml`）要点：
- 控制端口：7000
- 认证令牌：`openclaw-frp-2024`
- Web 管理面板：http://101.32.242.14:7500 (admin/admin123)

### 1.5 开放防火墙端口

```bash
# 如果使用 firewalld
firewall-cmd --permanent --add-port=9400/tcp   # U2_Service
firewall-cmd --permanent --add-port=7000/tcp   # frp 控制通道
firewall-cmd --permanent --add-port=7500/tcp   # frp Web 面板
firewall-cmd --permanent --add-port=9501/tcp   # frp 映射的 AutoX 端口
firewall-cmd --reload
```

> 同时需要在腾讯云安全组中放行以上端口。

---

## 二、手机端部署

### 2.1 安装 AutoX.js APK

1. 从 [AutoX.js GitHub Releases](https://github.com/kkevsekk1/AutoX/releases) 下载最新 APK
2. 将 APK 传输到手机并安装
3. 首次打开 AutoX.js，授予存储权限

### 2.2 开启无障碍权限

这是 AutoX.js 正常工作的**必要条件**：

1. 打开手机 **设置** → **无障碍** (或 **辅助功能**)
2. 找到 **AutoX.js** 并开启无障碍服务
3. 确认弹窗中选择 **允许**

> 部分手机品牌路径不同：
> - OPPO/realme: 设置 → 其他设置 → 无障碍
> - 小米: 设置 → 更多设置 → 无障碍
> - 华为: 设置 → 辅助功能 → 无障碍

### 2.3 运行 AutoX.js HTTP 服务

1. 将 `autox/autox-server.js` 脚本传输到手机
2. 在 AutoX.js 中打开并运行该脚本
3. 脚本会在手机端启动 HTTP 服务，监听端口 9500

### 2.4 安装 Termux 并配置 frp 客户端

#### 安装 Termux

从 [F-Droid](https://f-droid.org/packages/com.termux/) 下载安装 Termux（不要用 Play Store 版本）。

#### 在 Termux 中安装 frp 客户端

```bash
# 下载 frp ARM64 版本（根据手机架构选择）
cd ~
curl -LO https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_arm64.tar.gz
tar -xzf frp_0.61.1_linux_arm64.tar.gz
cp frp_0.61.1_linux_arm64/frpc ~/frpc
chmod +x ~/frpc
```

#### 创建客户端配置文件

将项目中的 `deploy/frpc.toml` 内容复制到手机 Termux 中：

```bash
cat > ~/frpc.toml << 'EOF'
serverAddr = "101.32.242.14"
serverPort = 7000
auth.token = "openclaw-frp-2024"

log.to = "./frpc.log"
log.level = "info"
log.maxDays = 3

[[proxies]]
name = "autox-http"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9500
remotePort = 9501
EOF
```

#### 启动 frp 客户端

```bash
cd ~
./frpc -c frpc.toml
```

> 保持 Termux 在前台运行，或使用 `nohup ./frpc -c frpc.toml &` 后台运行。

---

## 三、uiautomator2 初始化

uiautomator2 需要向手机推送 agent APK 才能工作。此步骤需要 ADB 连接已建立。

### 前提条件

- ADB SSH 隧道已建立（参考根目录 [DEPLOY.md](../DEPLOY.md)）
- 云服务器上 `adb devices` 能看到手机 `a394960e`

### 执行初始化

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server

# 推送 uiautomator2 agent 到手机
uv run python -m uiautomator2 init
```

此命令会：
1. 向手机安装 `uiautomator2` 的 ATX agent APK
2. 安装 `uiautomator2-server` APK
3. 启动 atx-agent 守护进程

验证初始化成功：
```bash
# 在 Python 中测试连接
uv run python -c "
import uiautomator2 as u2
d = u2.connect('a394960e')
print(d.info)
"
```

应输出设备信息（屏幕分辨率、SDK 版本等）。

---

## 四、健康检查

部署完成后，逐一检查各组件状态：

### 4.1 ADB 连接

```bash
adb devices
# 预期: a394960e    device
```

### 4.2 U2_Service

```bash
curl http://localhost:9400/health
# 预期: {"success":true,"message":"U2 Service is running","data":null}

# 测试设备列表
curl http://localhost:9400/devices
# 预期: 返回包含 a394960e 的设备列表
```

### 4.3 uiautomator2 设备操作

```bash
# 测试截图
curl -X POST http://localhost:9400/device/a394960e/screenshot
# 预期: {"success":true,"message":"Screenshot captured","data":"<base64>..."}
```

### 4.4 frp 隧道

```bash
# 检查 frp 服务端状态
curl http://localhost:7500/api/proxy/tcp -u admin:admin123
# 预期: 返回包含 autox-http 代理的 JSON

# 或直接测试 AutoX 服务连通性
curl http://localhost:9501/health
# 预期: AutoX.js 服务返回健康状态
```

### 4.5 AutoX_Service（通过 frp）

```bash
curl -X POST http://localhost:9501/ocr
# 预期: 返回 OCR 识别结果
```

### 4.6 Bun 入口层

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa

# 测试设备列表（走 U2_Service）
echo '{"type": "list_devices"}' | bun run src/skill-cli.ts

# 测试数据采集
echo '{"type": "collect_data", "deviceId": "a394960e", "app": "微信", "dataType": "联系人"}' | bun run src/skill-cli.ts

# 测试 AutoX 执行
echo '{"type": "autox_execute", "action": "ocr"}' | bun run src/skill-cli.ts
```

### 4.7 GLM-4.6V 视觉分析

```bash
curl -X POST http://localhost:9400/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "prompt": "请描述屏幕上的内容"}'
# 预期: 返回 GLM 对当前屏幕的分析结果
```

---

## 五、日常启动顺序

每次服务器重启或服务中断后，按以下顺序恢复所有组件：

### 步骤 1：建立 ADB SSH 隧道

在本地 Windows CMD 中执行（窗口保持不关）：

```cmd
ssh -R 5037:127.0.0.1:5037 root@101.32.242.14
```

密码：`3,jyBg!Pc5%A2`

> 如果提示 `remote port forwarding failed`，先在云服务器上执行 `adb kill-server`，再重试。

验证：
```bash
adb devices
# 应看到: a394960e    device
```

### 步骤 2：启动 frp 服务端（云服务器）

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
```

### 步骤 3：启动 U2_Service（云服务器）

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
```

### 步骤 4：手机端启动 AutoX.js 服务

1. 打开 AutoX.js App
2. 确认无障碍权限已开启
3. 运行 `autox-server.js` 脚本

### 步骤 5：手机端启动 frp 客户端

在 Termux 中执行：
```bash
cd ~
./frpc -c frpc.toml
```

### 步骤 6：验证所有服务

```bash
# 在云服务器上依次检查
curl http://localhost:9400/health          # U2_Service
curl http://localhost:9501/health          # AutoX (via frp)
adb devices                                # ADB 连接

cd ~/.openclaw/workspace/skills/mobile-rpa
echo '{"type": "list_devices"}' | bun run src/skill-cli.ts
```

### 快速启动脚本（云服务器端）

可将以下内容保存为 `deploy/start-all.sh`：

```bash
#!/bin/bash
echo "=== 启动 frp 服务端 ==="
cd ~/.openclaw/workspace/skills/mobile-rpa
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
echo "frps PID: $!"

echo "=== 启动 U2_Service ==="
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
echo "U2_Service PID: $!"

sleep 2
echo "=== 健康检查 ==="
curl -s http://localhost:9400/health
echo ""
echo "=== 等待手机端 frp 客户端连接... ==="
echo "请在手机 Termux 中执行: ./frpc -c frpc.toml"
```

---

## 六、三种设备访问方式共存

部署完成后，系统支持三种并行的设备访问方式：

| 方式 | 通道 | 适用场景 |
|------|------|---------|
| ADB SSH 隧道 | 本地 USB → SSH 反向隧道 → 云服务器 adb | 基础 shell 命令、文件传输 |
| uiautomator2 | ADB 隧道 → u2 agent (手机) → U2_Service (云) | 高速截图、元素操作、中文输入 |
| AutoX.js | 手机 HTTP 9500 → frp 隧道 → 云服务器 9501 | 无障碍服务、OCR、自定义 JS 脚本 |

Bun 入口层 (`skill-cli.ts`) 会自动路由：
- 设备操作指令 → 优先 U2_Service，不可用时回退 ADB
- AutoX 指令 → frp 映射端口 (9501)
- 数据采集指令 → U2_Service 的 DataCollector

---

## 七、常见问题

### Q: `uv sync` 报错找不到 Python

```bash
# 安装 Python 3.10+（OpenCloudOS 9）
dnf install -y python3.11
# uv 会自动检测系统 Python
```

### Q: `uiautomator2 init` 失败

确保 ADB 隧道已建立且 `adb devices` 能看到手机。如果手机弹出安装确认，请在手机上点击允许。

### Q: frp 客户端连不上服务端

1. 检查云服务器防火墙是否放行 7000 端口
2. 检查腾讯云安全组是否放行 7000 端口
3. 确认 `auth.token` 两端一致：`openclaw-frp-2024`
4. 查看 frp 日志：`cat frpc.log`

### Q: AutoX.js 无障碍权限被系统关闭

部分手机系统会在后台自动关闭无障碍权限。解决方法：
- 将 AutoX.js 加入电池优化白名单
- 锁定 AutoX.js 后台（在最近任务中锁定）
- 部分品牌需要在"自启动管理"中允许 AutoX.js

### Q: U2_Service 报 `Device not connected`

```bash
# 检查 ADB 连接
adb devices

# 重新初始化 uiautomator2
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
uv run python -m uiautomator2 init
```

### Q: 云服务器重启后所有服务都停了

按照"五、日常启动顺序"重新启动所有服务。建议将 `deploy/start-all.sh` 加入 systemd 或 crontab 实现开机自启。
