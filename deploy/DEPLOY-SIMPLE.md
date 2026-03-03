# AutoJS 部署方案

## 架构

```
Agent → Python (云:9400) → localhost:9501 → [隧道] → AutoJS (手机:9500)
```

隧道有三种方案，选择其一即可。

---

## 手机端配置（所有方案通用）

### 1. 安装 AutoJS App

选择其一：
- AutoX.js: https://github.com/kkevsekk1/AutoX/releases
- AutoJs6: https://github.com/SuperMonster003/AutoJs6/releases

### 2. 开启权限

1. 无障碍服务：设置 → 无障碍 → AutoJS → 开启
2. 悬浮窗权限：设置 → 应用管理 → AutoJS → 悬浮窗 → 允许
3. 后台运行：设置 → 电池 → AutoJS → 不限制后台

### 3. 运行服务脚本

1. 将 `autox/autox-server-v2.js` 传到手机
2. 在 AutoJS App 中导入并运行
3. 看到 `[v2] HTTP 服务已启动，端口: 9500` 表示成功

---

## 方案 A：ADB + SSH 隧道（推荐）

手机 USB 连本地电脑，不需要在手机装 Termux。

### 本地电脑执行

```cmd
adb forward tcp:9500 tcp:9500
ssh -R 9501:127.0.0.1:9500 root@101.32.242.14
```

> SSH 窗口保持不关闭

### 云服务器执行

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
nohup uv run uvicorn server_autox:app --host 0.0.0.0 --port 9400 > server.log 2>&1 &
```

### 验证

```bash
curl -X POST http://localhost:9501/health
```

---

## 方案 B：frp 隧道（无线）

手机不用 USB 连接，但需要在手机装 Termux + frp。

### 手机端（Termux）

```bash
pkg update && pkg install wget
wget https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_arm64.tar.gz
tar -xzf frp_0.61.1_linux_arm64.tar.gz
cp frp_0.61.1_linux_arm64/frpc ~/frpc
chmod +x ~/frpc

cat > ~/frpc.toml << 'EOF'
serverAddr = "101.32.242.14"
serverPort = 7000
auth.token = "openclaw-frp-2024"

[[proxies]]
name = "autox-http"
type = "tcp"
localIP = "127.0.0.1"
localPort = 9500
remotePort = 9501
EOF

./frpc -c frpc.toml
```

### 云服务器执行

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
nohup frps -c deploy/frps.toml > frps.log 2>&1 &

cd u2-server
nohup uv run uvicorn server_autox:app --host 0.0.0.0 --port 9400 > server.log 2>&1 &
```

---

## 方案 C：WiFi 直连（同一内网）

手机和云服务器在同一内网，或手机有公网 IP 时可用。

### 配置步骤

1. 手机连 WiFi，获取 IP（设置 → WLAN → 查看 IP，如 192.168.1.100）
2. 确保云服务器能访问手机 IP（同一内网或手机有公网 IP）
3. 启动时指定手机 IP：

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
AUTOX_URL=http://192.168.1.100:9500 uv run uvicorn server_autox:app --host 0.0.0.0 --port 9400
```

或修改 `autox_device.py` 中的默认值：
```python
AUTOX_BASE_URL = "http://192.168.1.100:9500"
```

### 验证

```bash
# 直接测试手机
curl -X POST http://192.168.1.100:9500/health
```

### 避免 IP 变化

在路由器里给手机 MAC 地址绑定静态 IP，这样手机重连 WiFi 后 IP 不会变。

---

## 方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: ADB+SSH | 配置最简单，IP 固定 | 需要 USB 连接 |
| B: frp | 无线，手机可移动 | 需要装 Termux |
| C: WiFi | 最简单，无需隧道 | 需要同一内网，IP 可能变 |

---

## API 端点

| 端点 | 说明 | 参数 |
|------|------|------|
| POST /health | 健康检查 | - |
| POST /screenshot | 截图(base64) | - |
| POST /click | 点击 | x, y |
| POST /long_click | 长按 | x, y, duration? |
| POST /swipe | 滑动 | x1, y1, x2, y2, duration? |
| POST /scroll | 滚动 | direction (up/down) |
| POST /input | 输入文本 | text |
| POST /key | 按键 | key (back/home/recents) |
| POST /app/start | 启动App | package |
| POST /app/stop | 停止App | package |
| POST /app/current | 当前App | - |
| POST /find_element | 查找元素 | by, value, timeout? |
| POST /click_element | 点击元素 | by, value, timeout? |
| POST /ui_tree | UI树 | maxDepth? |
| POST /ocr | OCR识别 | - |
| POST /clipboard | 剪贴板 | text? |
| POST /run_script | 执行脚本 | script |

---

## 常见问题

### AutoJS 服务无法启动
检查无障碍服务是否开启。

### SSH 隧道断开
重新执行 `adb forward` 和 `ssh -R` 命令。

### frp 连接失败
1. 检查云服务器防火墙是否放行 7000 端口
2. 检查 auth.token 是否一致

### 截图权限申请失败
首次运行脚本时会弹出权限申请，需要手动点击允许。

### 手机息屏后服务断开
将 AutoJS 加入电池优化白名单，锁定后台。
