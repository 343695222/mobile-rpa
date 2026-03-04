# Mobile RPA 部署指南

## 架构

```
云端 OpenClaw → U2_Service(:9400) → frp隧道 → 本地 Midscene(:9401) → 本地模拟器
```

- 云端：U2_Service (Python FastAPI) + frps
- 本地：Midscene 服务 (Bun) + frpc + Android 模拟器

## 环境信息

| 项目 | 值 |
|------|-----|
| 云服务器 | 101.32.242.14 (OpenCloudOS 9) |
| 云端项目路径 | ~/.openclaw/workspace/skills/mobile-rpa |
| 本地项目路径 | D:\abnjd |
| 本地 ADB | D:\learning\Open-AutoGLM-main\platform-tools\adb.exe |
| 模拟器 | Android Studio AVD (emulator-5554) |
| Midscene 模型 | qwen3-vl-plus (DashScope) |

## 端口一览

| 服务 | 端口 | 位置 | 说明 |
|------|------|------|------|
| U2_Service | 9400 | 云端 | 主 API |
| Midscene | 9401 | 本地 (frp映射到云端) | AI 操作 |
| frps 控制 | 7000 | 云端 | frp 服务端 |
| frp 管理面板 | 7500 | 云端 | admin/admin123 |

---

## 一、首次部署

### 云端

```bash
# 1. 拉代码
mkdir -p ~/.openclaw/workspace/skills
cd ~/.openclaw/workspace/skills
git clone https://github.com/343695222/mobile-rpa.git
cd mobile-rpa

# 2. 装依赖
bun install
cd u2-server && uv sync && cd ..

# 3. 配置 .env
cp .env.example .env
nano .env  # 填入 DashScope API Key

# 4. 启动
bash deploy/start-all.sh
```

### 本地

```bash
# 1. 装依赖
bun install

# 2. 下载 frpc
# https://github.com/fatedier/frp/releases → windows_amd64.zip
# 解压 frpc.exe 到项目根目录

# 3. 启动模拟器 (Android Studio → Virtual Device Manager)

# 4. 一键启动
deploy\start-local-to-cloud.cmd
```

---

## 二、日常使用

每次使用只需要：

### 本地（双击运行）
```cmd
deploy\start-local-to-cloud.cmd
```
自动启动 Midscene + 连接模拟器 + frp 隧道。

### 云端（如果服务停了）
```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
bash deploy/start-all.sh
```

### 验证
```bash
# 云端执行
curl http://localhost:9401/health
curl -X POST http://localhost:9401/ai/query -H "Content-Type: application/json" -d '{"dataDemand": "屏幕上所有可见的文字"}'
```

---

## 三、代码更新

```bash
# 本地
git add -A && git commit -m "描述" && git push origin main

# 云端
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main
bun install          # 如果改了 package.json
cd u2-server && uv sync && cd ..  # 如果改了 pyproject.toml
bash deploy/start-all.sh
```

---

## 四、常见问题

| 问题 | 解决 |
|------|------|
| frpc 连不上云端 | 确认云端 frps 在跑：`ss -tlnp \| grep 7000` |
| Midscene 报 No devices | 确认模拟器已启动：`adb devices` |
| 云端 9401 被占用 | 杀掉云端 Midscene：`pkill -f midscene-client` |
| source-map 报错 | 启动脚本已自动修复 |
| 模型 404 | 检查 .env 中 MODEL_NAME=qwen3-vl-plus, FAMILY=qwen3-vl |

这个脚本会自动：启动 Midscene → 连接模拟器 → 启动 frp 隧道

### 云端

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
bash deploy/start-all.sh
```

启动 frps + U2_Service（不启动 Midscene，通过 frp 隧道用本地的）。

### 验证

云端执行：
```bash
# 检查隧道
curl http://localhost:9401/health

# 连接设备（首次）
curl -X POST http://localhost:9401/connect

# 测试 aiQuery
curl -X POST http://localhost:9401/ai/query \
  -H "Content-Type: application/json" \
  -d '{"dataDemand": "屏幕上所有可见的文字"}'

# 测试 aiAct
curl -X POST http://localhost:9401/ai/act \
  -H "Content-Type: application/json" \
  -d '{"instruction": "点击Chrome图标"}'
```

---

## 首次部署

### 云端准备

```bash
# 安装 Bun
curl -fsSL https://bun.sh/install | bash

# 安装 uv (Python)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 修复 npm registry
echo 'registry=https://registry.npmjs.org/' > ~/.npmrc

# 拉取代码
mkdir -p ~/.openclaw/workspace/skills
cd ~/.openclaw/workspace/skills
git clone https://github.com/343695222/mobile-rpa.git
cd mobile-rpa

# 安装依赖
bun install
cd u2-server && uv sync && cd ..

# 配置环境变量
cp .env.example .env
nano .env  # 填入 DashScope API Key
```

### 本地准备

1. 安装 Android Studio，创建模拟器 (AVD)
2. 安装 Bun：https://bun.sh
3. 下载 frpc：https://github.com/fatedier/frp/releases → `frp_x.x.x_windows_amd64.zip`
4. 解压 `frpc.exe` 到项目根目录

```cmd
# 安装依赖
bun install

# 配置 .env（从 .env.example 复制，填入 API Key）
copy .env.example .env
```

---

## 代码更新流程

```cmd
:: 本地提交推送
git add -A
git commit -m "描述改动"
git push origin main
```

```bash
# 云端拉取重启
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main
bash deploy/start-all.sh
```

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `src/midscene-client.ts` | Midscene Android Agent HTTP 服务 |
| `u2-server/server.py` | U2_Service FastAPI 主服务 |
| `u2-server/midscene_bridge.py` | Python → Midscene HTTP 桥接 |
| `u2-server/strategies/midscene_strategy.py` | Midscene aiQuery 数据采集策略 |
| `deploy/start-all.sh` | 云端一键启动 (frps + U2_Service) |
| `deploy/start-local-to-cloud.cmd` | 本地一键启动 (Midscene + frpc) |
| `deploy/frps.toml` | frp 服务端配置 |
| `deploy/frpc-local.toml` | frp 客户端配置（本地 PC 用） |
| `.env` | 环境变量（API Key、模型配置） |

---

## 常见问题

### frpc 连不上云端
确认云端 frps 在运行：`ss -tlnp | grep 7000`

### Midscene 连接设备失败
确认模拟器已启动：`adb devices` 应看到 `emulator-5554`

### 云端 9401 端口被占
云端的 Midscene 进程没杀干净：`pkill -f "midscene-client"`

### source-map bug
本地启动脚本已自动修复。云端如需手动修复：
```bash
sed -i 's/if (aNeedle\[aColumnName\] < 0)/if (aNeedle[aColumnName] < -1)/' node_modules/source-map/lib/source-map-consumer.js
```
