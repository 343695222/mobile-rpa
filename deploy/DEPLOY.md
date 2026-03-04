# OpenClaw 移动端自动化插件 — 部署指南

> 本文档覆盖所有组件的部署：U2_Service（Python FastAPI）、Midscene 服务（Bun）、AutoX.js、frp 隧道、数据采集器。
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
| DashScope API Key | (通过环境变量 DASHSCOPE_API_KEY 配置) |
| 视觉模型 | GUI-Plus + Qwen-VL-Max + Qwen3-VL (Midscene) |

### 端口一览

| 服务 | 端口 | 运行位置 | 说明 |
|------|------|---------|------|
| U2_Service (FastAPI) | 9400 | 云服务器 | 主 API 服务，含 Midscene 代理端点 |
| **Midscene 服务 (Bun)** | **9401** | **云服务器** | **Midscene Android Agent HTTP 服务** |
| AutoX_Service | 9500 | 手机 | AutoX.js HTTP 服务 |
| AutoX_Service (frp 映射) | 9501 | 云服务器 localhost | frp 映射 |
| frp 控制通道 | 7000 | 云服务器 | frp 服务端 |
| frp Web 管理面板 | 7500 | 云服务器 (admin/admin123) | frp 管理 |
| ADB SSH 隧道 | 5037 | 云服务器 (反向隧道) | ADB 转发 |

### 系统架构（新增 Midscene 层）

```
                          ┌─────────────────────────────────────────┐
                          │              云服务器                     │
                          │                                         │
Agent ──→ U2_Service ─────┤  /midscene/* ──→ Midscene服务(:9401)    │
          (:9400)         │                    │ Qwen3-VL (DashScope)│
                          │                    │ Scrcpy 快速截图      │
                          │                    ↓                     │
                          │  /vision/*  ──→ GUI-Plus (DashScope)    │
                          │                    │ 复杂多步任务 fallback │
                          │                                         │
                          │  ADB ──→ uiautomator2 ──→ 手机          │
                          │  frp ──→ AutoX.js(:9500) ──→ 手机       │
                          └─────────────────────────────────────────┘
```

---

## 一、云服务器部署

> 以下操作均在云服务器 (101.32.242.14) 上以 root 用户执行。

### 1.1 安装 uv（Python 环境管理）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

### 1.2 安装 Bun（Midscene 服务运行时）

```bash
curl -fsSL https://bun.sh/install | bash
source ~/.bashrc
bun --version
```

### 1.3 修复 npm registry（腾讯云镜像不全）

```bash
echo 'registry=https://registry.npmjs.org/' > ~/.npmrc
```

### 1.4 拉取代码（Git）

项目仓库：`https://github.com/343695222/mobile-rpa.git`

**首次部署（云端还没有代码）：**
```bash
mkdir -p ~/.openclaw/workspace/skills
cd ~/.openclaw/workspace/skills
git clone https://github.com/343695222/mobile-rpa.git
```

**已有代码（更新到最新）：**
```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main
```

> 不要上传 `node_modules`，云端会自己安装。

### 1.5 安装所有依赖

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa

# Bun 依赖（含 @midscene/android）
bun install

# Python 依赖
cd u2-server
uv sync
```

### 1.6 配置环境变量

`.env` 文件不会被 git 提交（已在 `.gitignore` 中排除），需要手动创建：

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa

# 从模板复制
cp .env.example .env

# 编辑，填入真实 API Key
nano .env
```

**必须修改的项：**

```bash
# 把 ${DASHSCOPE_API_KEY} 替换为你的真实 Key
MIDSCENE_MODEL_API_KEY=sk-你的真实key
MIDSCENE_PLANNING_MODEL_API_KEY=sk-你的真实key
MIDSCENE_INSIGHT_MODEL_API_KEY=sk-你的真实key

# 同时设置系统环境变量（U2_Service 的 GUI-Plus/OCR 也需要）
export DASHSCOPE_API_KEY=sk-你的真实key
```

> 建议把 `export DASHSCOPE_API_KEY=sk-xxx` 写入 `~/.bashrc` 永久生效。

---

## 二、启动服务

### 2.1 建立 ADB SSH 隧道

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

### 2.2 启动 frp 服务端

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
```

### 2.3 启动 Midscene 服务（新增）

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa

# 前台运行（调试用，能看到日志）
bun run src/midscene-client.ts

# 后台运行（生产用）
nohup bun run src/midscene-client.ts > midscene.log 2>&1 &
```

启动成功会看到：
```
[midscene] Agent connected to device: (default)
[midscene] HTTP server listening on http://localhost:9401
```

> Midscene 服务首次连接设备时会自动通过 Scrcpy 建立视频流，可能需要几秒。

### 2.4 启动 U2_Service

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server

# 前台运行（调试用）
uv run uvicorn server:app --host 0.0.0.0 --port 9400

# 后台运行（生产用）
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
```

### 2.5 手机端启动 AutoX.js + frp

1. 打开 AutoX.js App → 确认无障碍权限已开启 → 运行 `autox-server-v2.js`
2. 在 Termux 中启动 frp 客户端：
```bash
cd ~ && ./frpc -c frpc.toml
```

---

## 三、健康检查

部署完成后，逐一检查各组件：

```bash
# 1. ADB 连接
adb devices
# 预期: a394960e    device

# 2. Midscene 服务（新增）
curl http://localhost:9401/health
# 预期: {"success":true,"message":"Midscene service running","connected":true}

# 3. U2_Service
curl http://localhost:9400/health
# 预期: {"success":true,"message":"U2 Service is running","data":null}

# 4. Midscene 通过 U2_Service 代理
curl http://localhost:9400/midscene/health
# 预期: {"success":true,"message":"Midscene service running",...}

# 5. frp + AutoX
curl http://localhost:9501/health
# 预期: AutoX.js 健康状态

# 6. DashScope 视觉分析
curl -X POST http://localhost:9400/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "prompt": "请描述屏幕上的内容"}'
```

### 测试 Midscene AI 能力

```bash
# 测试 aiAct（自然语言操作）
curl -X POST http://localhost:9400/midscene/act \
  -H "Content-Type: application/json" \
  -d '{"instruction": "点击屏幕上的设置图标"}'

# 测试 aiQuery（结构化数据提取）
curl -X POST http://localhost:9400/midscene/query \
  -H "Content-Type: application/json" \
  -d '{"data_demand": "屏幕上所有可见的应用名称"}'

# 测试 aiAssert（屏幕断言）
curl -X POST http://localhost:9400/midscene/assert \
  -H "Content-Type: application/json" \
  -d '{"assertion": "当前在手机桌面"}'

# 测试 Midscene 快速截图（Scrcpy）
curl http://localhost:9400/midscene/screenshot
```

---

## 四、日常启动顺序（完整）

每次服务器重启或服务中断后，按以下顺序恢复：

```
步骤 1: 本地 → 建立 ADB SSH 隧道
步骤 2: 云端 → 启动 frp 服务端
步骤 3: 云端 → 启动 Midscene 服务 ← 新增
步骤 4: 云端 → 启动 U2_Service
步骤 5: 手机 → 启动 AutoX.js 服务
步骤 6: 手机 → 启动 frp 客户端
步骤 7: 云端 → 健康检查
```

### 一键启动脚本（云服务器端）

```bash
#!/bin/bash
# deploy/start-all.sh
PROJECT=~/.openclaw/workspace/skills/mobile-rpa

echo "=== 1. 启动 frp 服务端 ==="
cd $PROJECT
nohup frps -c deploy/frps.toml > frps-run.log 2>&1 &
echo "frps PID: $!"

echo "=== 2. 启动 Midscene 服务 ==="
cd $PROJECT
nohup bun run src/midscene-client.ts > midscene.log 2>&1 &
echo "Midscene PID: $!"

echo "=== 3. 启动 U2_Service ==="
cd $PROJECT/u2-server
nohup uv run uvicorn server:app --host 0.0.0.0 --port 9400 > u2-server.log 2>&1 &
echo "U2_Service PID: $!"

sleep 3
echo ""
echo "=== 健康检查 ==="
echo -n "U2_Service: "; curl -s http://localhost:9400/health | head -c 60; echo
echo -n "Midscene:   "; curl -s http://localhost:9401/health | head -c 60; echo
echo ""
echo "=== 等待手机端连接 ==="
echo "1. 手机运行 AutoX.js 服务脚本"
echo "2. Termux 执行: ./frpc -c frpc.toml"
```

### 一键停止脚本

```bash
#!/bin/bash
# deploy/stop-all.sh
echo "=== 停止所有服务 ==="
pkill -f "uvicorn server:app" && echo "U2_Service stopped" || echo "U2_Service not running"
pkill -f "midscene-client" && echo "Midscene stopped" || echo "Midscene not running"
pkill -f "frps" && echo "frps stopped" || echo "frps not running"
echo "=== 完成 ==="
```

---

## 五、代码更新流程

### 本地提交 + 推送

在本地 Windows 项目目录中：
```cmd
git add -A
git commit -m "描述你的改动"
git push origin main
```

### 云端拉取

SSH 到云服务器后：
```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main
```

### 更新后重启

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa

# 如果改了 package.json（新增 npm 依赖）
bun install

# 如果改了 pyproject.toml（新增 Python 依赖）
cd u2-server && uv sync && cd ..

# 重启服务
bash deploy/stop-all.sh
bash deploy/start-all.sh
```

> `.env` 文件不在 git 中，`git pull` 不会覆盖云端的 `.env`，API Key 安全。

---

## 六、四种设备访问方式共存

| 方式 | 通道 | 适用场景 |
|------|------|---------|
| **Midscene (Scrcpy)** | **ADB → Scrcpy 视频流 → Qwen3-VL** | **自然语言操作、结构化数据提取、快速截图** |
| ADB SSH 隧道 | 本地 USB → SSH 反向隧道 → 云服务器 adb | 基础 shell 命令、文件传输 |
| uiautomator2 | ADB 隧道 → u2 agent → U2_Service | 元素操作、中文输入 |
| AutoX.js | 手机 HTTP 9500 → frp → 云服务器 9501 | 无障碍服务、手机端 JS 脚本 |

### 数据采集策略优先级（更新）

```
api > midscene > rpa_copy > rpa_ocr
```

- `midscene`：通过 Midscene aiQuery 直接提取结构化数据（推荐）
- `rpa_ocr`：传统截图 + GLM OCR + JSON 解析（fallback）

---

## 七、Midscene 模型配置说明

Midscene 使用三个独立的模型 intent，都通过 DashScope API 调用 Qwen3-VL：

| Intent | 用途 | 环境变量前缀 |
|--------|------|-------------|
| Default | 元素定位 (Locate) | `MIDSCENE_MODEL_*` |
| Planning | 多步操作规划 (aiAct) | `MIDSCENE_PLANNING_MODEL_*` |
| Insight | 数据提取 (aiQuery) + 断言 (aiAssert) | `MIDSCENE_INSIGHT_MODEL_*` |

所有配置在 `.env` 文件中，关键字段：

```bash
MIDSCENE_MODEL_NAME=qwen3-vl              # 模型名
MIDSCENE_MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # DashScope OpenAI 兼容端点
MIDSCENE_MODEL_API_KEY=sk-xxx             # DashScope API Key
MIDSCENE_MODEL_FAMILY=qwen3-vl            # 模型族（影响 prompt 格式和坐标系）
MIDSCENE_PREFERRED_LANGUAGE=zh            # 中文优先
```

> GUI-Plus 模型保留在 VisionAgent 中作为复杂多步任务的 fallback，通过 `DASHSCOPE_API_KEY` 环境变量配置。

---

## 八、常见问题

### Q: Midscene 服务启动报 `Cannot find module '@midscene/android'`

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
bun install
```

### Q: Midscene 连接设备失败

确保 ADB 隧道已建立且 `adb devices` 能看到手机。Midscene 通过 ADB 连接设备。

### Q: Midscene aiAct 超时

Qwen3-VL 模型调用可能需要 10-30 秒。可以在 `.env` 中调整超时：
```bash
MIDSCENE_MODEL_TIMEOUT=60000
```

### Q: `uv sync` 报错找不到 Python

```bash
dnf install -y python3.11
```

### Q: `uiautomator2 init` 失败

确保 ADB 隧道已建立且 `adb devices` 能看到手机。

### Q: frp 客户端连不上服务端

1. 检查云服务器防火墙是否放行 7000 端口
2. 检查腾讯云安全组是否放行 7000 端口
3. 确认 `auth.token` 两端一致：`openclaw-frp-2024`

### Q: U2_Service 报 `Device not connected`

```bash
adb devices
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
uv run python -m uiautomator2 init
```

### Q: 云服务器重启后所有服务都停了

按照"四、日常启动顺序"重新启动，或执行 `bash deploy/start-all.sh`。
