# Mobile RPA Skill 部署指南

## 推荐：完整部署（含 Midscene AI）

**新用户推荐使用完整部署方案**，包含 Midscene AI 自然语言操作能力。

详见 [`deploy/DEPLOY.md`](deploy/DEPLOY.md) — 包含 U2_Service + Midscene + AutoX.js + frp 全部组件。

### 简化部署（仅 AutoX.js）

如果只需要 AutoX.js 直连模式，详见 [`deploy/DEPLOY-SIMPLE.md`](deploy/DEPLOY-SIMPLE.md)

架构对比：
```
完整架构: Agent → U2_Service(:9400) → Midscene(:9401) + GUI-Plus + ADB + AutoX
简化架构: Agent → Python(:9400) → frp隧道 → AutoJS(手机:9500)
```

---

## ADB 模式部署（传统方式）

以下是传统 ADB + uiautomator2 模式的部署说明，适用于需要 ADB 特定功能的场景。

## 环境信息

| 项目 | 值 |
|------|-----|
| 云服务器 | 腾讯云 101.32.242.14 (OpenCloudOS 9) |
| 本地电脑 | Windows |
| 手机设备 | a394960e (PJZ110) |
| 项目本地路径 | D:\abnjd |
| 项目云端路径 | ~/.openclaw/workspace/skills/mobile-rpa |
| ADB 云端路径 | /opt/adb |

---

## 一、首次部署（完整流程）

### 1. 云服务器准备
默认用户名：root

登录密码：3,jyBg!Pc5%A2
101.32.242.14
#### 1.1 安装 ADB

```bash
# OpenCloudOS 没有 android-tools 包，手动安装 Google platform-tools
cd /tmp
curl -O https://dl.google.com/android/repository/platform-tools-latest-linux.zip
unzip platform-tools-latest-linux.zip
mv platform-tools /opt/adb

# 加入 PATH（写入 bashrc 永久生效）
echo 'export PATH=/opt/adb:$PATH' >> ~/.bashrc
source ~/.bashrc

# 验证
adb version
```

#### 1.2 安装 Bun

```bash
curl -fsSL https://bun.sh/install | bash
source ~/.bashrc
bun --version
```

#### 1.3 修复 npm registry（腾讯云镜像不全）

```bash
echo 'registry=https://registry.npmjs.org/' > ~/.npmrc
```

### 2. 本地电脑准备

#### 2.1 确保 ADB 版本最新

从 https://developer.android.com/tools/releases/platform-tools 下载最新 platform-tools。
本地和云端 ADB 版本必须一致，否则会出现 `protocol fault` 错误。

#### 2.2 手机开启 USB 调试

手机连接本地电脑 USB，开启开发者选项 > USB 调试。

验证本地能看到手机：
```cmd
adb devices
```

### 3. 建立 SSH 反向隧道（ADB over SSH）

在本地 Windows CMD/PowerShell 中执行：

```cmd
ssh -R 5037:127.0.0.1:5037 root@101.32.242.14
```

输入密码后保持窗口不关。这样云服务器上的 ADB 就能通过隧道访问本地手机。

> **注意**：如果提示 `remote port forwarding failed for listen port 5037`，
> 先在云服务器上杀掉已有的 adb server：
> ```bash
> adb kill-server
> ```
> 然后重新建立隧道。

验证（在云服务器上）：
```bash
adb devices
# 应该看到: a394960e    device
```

### 4. 首次拉取代码

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

> `.env` 文件不在 git 中，首次部署需要手动创建：
> ```bash
> cp .env.example .env
> nano .env  # 填入真实 API Key
> ```

### 5. 云端安装依赖

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
bun install
```

### 6. 验证部署

```bash
# 测试设备列表
echo '{"type": "list_devices"}' | bun run src/skill-cli.ts

# 测试屏幕抓取
echo '{"type": "get_screen", "deviceId": "a394960e"}' | bun run src/skill-cli.ts

# 测试点击操作
echo '{"type": "execute_action", "deviceId": "a394960e", "action": {"type": "tap", "x": 540, "y": 960}}' | bun run src/skill-cli.ts

# 测试模板列表
echo '{"type": "list_templates"}' | bun run src/skill-cli.ts
```

---

## 二、后续代码更新（Git）

### 本地提交 + 推送

在本地项目目录中：
```cmd
git add -A
git commit -m "描述你的改动"
git push origin main
```

### 云端拉取 + 重启

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
git pull origin main

# 如果改了 package.json
bun install

# 如果改了 pyproject.toml
cd u2-server && uv sync && cd ..

# 重启服务
bash deploy/stop-all.sh
bash deploy/start-all.sh
```

> `.env` 不在 git 中，`git pull` 不会覆盖云端的 API Key 配置。

---

## 三、下次重新连接（关机/断开后恢复）

每次电脑关机、手机断开、或 SSH 隧道断了之后，按以下步骤恢复：

### 步骤 1：本地准备

1. 手机 USB 连接本地电脑
2. 确认手机 USB 调试已开启
3. 本地打开 CMD，确认手机连上了：

```cmd
adb devices
:: 应该看到: a394960e    device
```

### 步骤 2：建立 SSH 隧道

本地 CMD 执行（这个窗口要一直开着）：

```cmd
ssh -R 5037:127.0.0.1:5037 root@101.32.242.14
```

输入密码：`3,jyBg!Pc5%A2`

> 如果提示 `remote port forwarding failed for listen port 5037`，
> 在云服务器上先执行 `adb kill-server`，然后退出 SSH，重新建立隧道。

### 步骤 3：云端验证

隧道建好后，在同一个 SSH 窗口里（或另开一个 SSH 窗口）：

```bash
# 确认能看到手机
adb devices

# 进入项目目录
cd ~/.openclaw/workspace/skills/mobile-rpa

# 测试 skill
echo '{"type": "list_devices"}' | bun run src/skill-cli.ts
```

看到手机 `a394960e` 就说明一切正常，可以开始使用了。

### 快速恢复清单（复制粘贴用）

本地 CMD：
```cmd
adb devices
ssh -R 5037:127.0.0.1:5037 root@101.32.242.14
```

云端：
```bash
adb devices
cd ~/.openclaw/workspace/skills/mobile-rpa
echo '{"type": "list_devices"}' | bun run src/skill-cli.ts
```

---

## 四、日常使用流程

每次使用 Skill 的完整步骤：

```
1. 手机 USB 连接本地电脑
2. 本地打开 CMD，建立 SSH 隧道：
   ssh -R 5037:127.0.0.1:5037 root@101.32.242.14
3. 隧道窗口保持不关
4. OpenClaw 通过 stdin/stdout 调用 skill：
   echo '{"type": "..."}' | bun run src/skill-cli.ts
```

---

## 四、日常使用流程

每次使用 Skill 的完整步骤：

```
1. 手机 USB 连接本地电脑
2. 本地打开 CMD，建立 SSH 隧道：
   ssh -R 5037:127.0.0.1:5037 root@101.32.242.14
3. 隧道窗口保持不关
4. OpenClaw 通过 stdin/stdout 调用 skill：
   echo '{"type": "..."}' | bun run src/skill-cli.ts
```

---

## 五、常见问题

### Q: `protocol fault (couldn't read status)` 错误
本地和云端 ADB 版本不一致。两边都更新到最新版 platform-tools。

### Q: `remote port forwarding failed for listen port 5037`
云端已有 adb server 占用 5037 端口。先在云端执行 `adb kill-server`，再重新建立隧道。

### Q: `bun install` 报 404 错误
检查 `~/.npmrc` 是否指向官方源：
```bash
cat ~/.npmrc
# 应该是: registry=https://registry.npmjs.org/
```

### Q: `Module not found` 错误
确认当前目录是项目根目录：
```bash
cd ~/.openclaw/workspace/skills/mobile-rpa
```

### Q: 手机断开连接
检查本地 USB 连接和 SSH 隧道窗口是否还在。重新插拔 USB，重建隧道。

cli_a92f8fcfab389cc8

TtblXrxHG5mmfEwLscr2kcxyQ8k1ahX2