# Mobile RPA 部署指南

## 架构

```
QQ Bot → OpenClaw Gateway → Agent(读SKILL.md) → U2_Service(:9400) → frp隧道 → 本地Midscene(:9401) → 模拟器
```

- 云端：OpenClaw Gateway + U2_Service (FastAPI) + frps
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
| U2_Service | 9400 | 云端 | 主 API，代理 Midscene 请求 |
| Midscene | 9401 | 本地 (frp映射到云端) | AI 视觉操作 |
| frps | 7000 | 云端 | frp 服务端 |
| frp 管理面板 | 7500 | 云端 | admin/admin123 |

---

## 一、首次部署

### 云端

```bash
# 安装基础工具
curl -fsSL https://bun.sh/install | bash
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'registry=https://registry.npmjs.org/' > ~/.npmrc

# 拉代码 + 装依赖
mkdir -p ~/.openclaw/workspace/skills
cd ~/.openclaw/workspace/skills
git clone https://github.com/343695222/mobile-rpa.git
cd mobile-rpa
bun install
cd u2-server && uv sync && cd ..

# 配置环境变量
cp .env.example .env
nano .env  # 填入 DASHSCOPE_API_KEY

# 启动所有服务
bash deploy/start-all.sh
```

### 本地

1. 安装 Android Studio，创建 AVD 模拟器
2. 安装 Bun: https://bun.sh
3. 下载 frpc: https://github.com/fatedier/frp/releases → `frp_x.x.x_windows_amd64.zip`，解压 `frpc.exe` 到项目根目录

```cmd
bun install
copy .env.example .env
:: 编辑 .env 填入 API Key
```

---

## 二、日常使用

### 本地（双击运行）
```cmd
deploy\start-local-to-cloud.cmd
```
自动：启动 Midscene → 连接模拟器 → 启动 frp 隧道

### 云端（如果服务停了）
```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
bash deploy/start-all.sh
```

### 验证（云端执行）
```bash
curl -s http://localhost:9400/health          # U2_Service
curl -s http://localhost:9401/health          # Midscene (frp隧道)
curl -s http://localhost:9400/midscene/health # 端到端
```

---

## 三、代码更新

### ⚠️ 重要：SKILL.md 的特殊处理

由于 Windows/Linux 换行符差异，SKILL.md 通过 git 更新可能不生效。
更新 SKILL.md 后需要在云端手动覆盖：

```bash
# 本地提交推送
git add -A && git commit -m "描述" && git push origin main

# 云端拉取
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main

# 如果 SKILL.md 内容没变（grep 验证）：
grep -c midscene SKILL.md
# 如果返回 0，说明换行符问题，需要手动用 cat heredoc 覆盖 SKILL.md

# 重启服务（包括 OpenClaw gateway 重新加载 skill）
bash deploy/start-all.sh
```

### 普通代码更新（不涉及 SKILL.md）
```bash
# 云端
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main
bash deploy/start-all.sh
```

---

## 四、常见问题

| 问题 | 解决 |
|------|------|
| frpc 连不上云端 | 确认云端 frps 在跑：`ss -tlnp \| grep 7000` |
| Midscene 报 No devices | 确认模拟器已启动：`adb devices` |
| 云端 9401 被占用 | `pkill -f midscene-client` |
| source-map 报错 | 本地启动脚本已自动修复 |
| 模型 404 | 检查 .env: MODEL_NAME=qwen3-vl-plus, FAMILY=qwen3-vl |
| OpenClaw 还用旧接口 | 重启 gateway：`pkill -f openclaw && nohup openclaw gateway > ~/.openclaw/openclaw.log 2>&1 &` |
| SKILL.md git pull 后没变 | CRLF 问题，在云端用 `cat > SKILL.md << 'EOF' ... EOF` 手动覆盖 |
| openclaw 直接运行退出 | 必须用 `openclaw gateway` 启动，不是 `openclaw` |

---

## 五、文件说明

| 文件 | 说明 |
|------|------|
| `SKILL.md` | OpenClaw agent 读取的技能描述（决定调哪个 API） |
| `src/midscene-client.ts` | Midscene Android Agent HTTP 服务 |
| `u2-server/server.py` | U2_Service FastAPI 主服务 |
| `u2-server/midscene_bridge.py` | Python → Midscene HTTP 桥接 |
| `deploy/start-all.sh` | 云端一键启动 (frps + U2_Service + OpenClaw gateway) |
| `deploy/start-local-to-cloud.cmd` | 本地一键启动 (Midscene + frpc) |
| `deploy/frps.toml` | frp 服务端配置 |
| `deploy/frpc-local.toml` | frp 客户端配置（本地 PC 用） |
| `.env` | 环境变量（API Key、模型配置） |
