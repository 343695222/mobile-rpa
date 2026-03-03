# 自动化操作 + 抓包 技能方案

> 本文档是技能设计方案，不是代码实现。描述如何将 AI 自动化操作与网络抓包能力结合，实现"边操作边抓包"的竞品分析工作流。

---

## 一、现状盘点

### 已有能力

| 能力 | 模块 | 状态 |
|------|------|------|
| AI 视觉驱动操作 | VisionAgent (GLM-4.6V) | ✅ 已实现 |
| uiautomator2 设备操作 | DeviceManager | ✅ 已实现 |
| 导航管理（脚本优先 + 探索回退） | Navigator | ✅ 已实现 |
| 安全守卫（出价/支付拦截） | SafetyGuard | ✅ 已实现，32 测试通过 |
| HAR 文件离线分析 | TrafficCapture + TrafficAnalyzer | ✅ 已实现，47 测试通过 |
| 采集脚本生成 | ScriptGenerator | ✅ 已实现，11 测试通过 |
| 数据字段映射 | DataMapper | ✅ 已实现，21 测试通过 |
| ADB SSH 隧道 | 本地 USB → 云服务器 | ✅ 已部署 |
| frp 隧道（AutoX.js） | 手机 9500 → 云服务器 9501 | ✅ 已部署 |

### 缺失能力（本方案要解决的）

| 能力 | 说明 | 难度 |
|------|------|------|
| 实时抓包（mitmproxy） | AI 操作手机的同时捕获 HTTPS 流量 | 🟡 中等 |
| 手机代理配置 | 让手机流量经过 mitmproxy | 🟡 中等 |
| 微信小程序 HTTPS 解密 | 绕过微信证书固定 | 🔴 高 |
| "操作 + 抓包"联动编排 | 两个能力的协同控制 | 🟢 低（代码编排） |

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent (云服务器)                   │
│                                                               │
│  Bun/TS 入口 (skill-cli.ts)                                  │
│    ↓ HTTP :9400                                               │
│  Python FastAPI (u2-server)                                   │
│    ├── VisionAgent ──→ GLM-4.6V (截图分析+决策)               │
│    ├── SafetyGuard ──→ 操作安全拦截                           │
│    ├── Navigator ────→ 页面导航                               │
│    ├── TrafficCapture → 流量录制管理                          │
│    ├── TrafficAnalyzer → 流量分析                             │
│    └── CaptureOrchestrator (新) → 编排"操作+抓包"联动         │
│                                                               │
│  mitmproxy (新) ──→ HTTPS 流量拦截 + 解密                    │
│    监听端口 :8080                                             │
│    addon → 实时推送流量到 TrafficCapture                      │
│                                                               │
└──────────┬────────────────────────────────────────────────────┘
           │ ADB SSH 隧道 (:5037)
           │ frp 隧道 (AutoX :9501)
           │ WiFi 代理 → mitmproxy :8080
           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Android 手机                               │
│                                                               │
│  WiFi 代理 → 101.32.242.14:8080 (mitmproxy)                 │
│  uiautomator2 agent (设备操作)                                │
│  AutoX.js HTTP 服务 (:9500)                                  │
│  目标 App / 微信小程序                                        │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
手机 App 发出 HTTPS 请求
  → WiFi 代理 → mitmproxy (:8080, 云服务器)
  → mitmproxy addon 实时推送 → TrafficCapture._records
  → 同时：mitmproxy 转发原始请求到目标服务器
  → 响应原路返回给 App

与此同时：
  VisionAgent 截图 → GLM 分析 → 执行操作 → 触发 App 新请求 → 被 mitmproxy 捕获
```

---

## 三、两种工作模式

### 模式 A：离线 HAR 分析（已实现，推荐先用）

```
人工操作手机 + 浏览器开发者工具/Charles 导出 HAR
  → traffic_load_har 加载
  → TrafficAnalyzer 自动分析
  → 输出接口清单
```

优点：零环境配置，立即可用
缺点：需要人工操作手机，无法自动化

### 模式 B：实时抓包 + AI 自动操作（本方案核心）

```
CaptureOrchestrator 启动：
  1. 启动 mitmproxy（后台进程）
  2. 配置手机 WiFi 代理
  3. 启动 TrafficCapture 录制
  4. VisionAgent 自动操作 App（浏览各页面）
  5. 操作过程中 mitmproxy 实时捕获流量
  6. 操作完成后停止录制
  7. TrafficAnalyzer 分析捕获的流量
  8. 输出接口清单 + 评估报告
```

---

## 四、新增组件设计

### 4.1 MitmproxyAddon — mitmproxy 流量桥接

作用：作为 mitmproxy 的 Python addon，将拦截到的请求实时推送给 TrafficCapture。

```
mitmproxy 进程
  └── MitmproxyAddon (addon)
        └── 每个请求/响应 → 构造 TrafficRecord → 推送到 TrafficCapture
```

关键设计点：
- mitmproxy 作为独立进程运行（不嵌入 FastAPI），通过共享内存或 HTTP 回调与 u2-server 通信
- addon 脚本放在 `u2-server/mitm_addon.py`
- 两种通信方式可选：
  - 方式 1：addon 通过 HTTP POST 回调 u2-server 的 `/traffic/add_record` 端点（简单，推荐）
  - 方式 2：addon 写入共享文件，TrafficCapture 轮询读取（无网络依赖）

自动化程度：⚙️ 全自动代码，可直接测试

### 4.2 ProxyManager — 代理环境管理

作用：管理 mitmproxy 进程的启停，以及手机 WiFi 代理的配置。

职责：
- 启动/停止 mitmproxy 进程
- 通过 ADB 设置手机 WiFi 代理（`adb shell settings put global http_proxy`）
- 通过 ADB 清除手机 WiFi 代理
- 检查 mitmproxy 是否已安装
- 检查 CA 证书是否已安装到手机

自动化程度：⚙️ 代码全自动，但首次 CA 证书安装需要人工

### 4.3 CaptureOrchestrator — "操作+抓包"联动编排器

作用：串联 ProxyManager + TrafficCapture + VisionAgent，实现"边操作边抓包"。

工作流程：
```
capture_and_explore(device_id, platform_name, app_package, domain_filter)
  │
  ├── 1. ProxyManager.start_mitmproxy()
  ├── 2. ProxyManager.set_phone_proxy(device_id)
  ├── 3. TrafficCapture.start_recording(platform_name, domain_filter)
  ├── 4. DeviceManager.app_start(device_id, app_package)
  ├── 5. VisionAgent.run_task(device_id, "浏览所有主要页面", max_steps=30)
  │       ↑ 每一步操作都会触发 App 网络请求 → mitmproxy 捕获
  ├── 6. TrafficCapture.stop_recording()
  ├── 7. ProxyManager.clear_phone_proxy(device_id)
  ├── 8. TrafficAnalyzer.analyze(records)
  └── 9. 返回分析结果
```

自动化程度：⚙️ 全自动代码

---

## 五、环境配置方案

### 5.1 mitmproxy 安装（云服务器）

```bash
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
uv add mitmproxy
```

mitmproxy 监听在云服务器 `0.0.0.0:8080`，手机通过 WiFi 代理连接。

### 5.2 手机代理配置

两种方式：

方式 A — ADB 全局代理（推荐，可自动化）：
```bash
# 设置代理
adb shell settings put global http_proxy 101.32.242.14:8080

# 清除代理
adb shell settings put global http_proxy :0
```

方式 B — WiFi 设置手动配置：
手机 WiFi 设置 → 高级 → 代理 → 手动 → 服务器 101.32.242.14，端口 8080

### 5.3 CA 证书安装（首次，需人工）

mitmproxy 解密 HTTPS 需要手机信任其 CA 证书：

```bash
# 1. 启动 mitmproxy 生成证书
mitmproxy --listen-port 8080

# 2. 手机浏览器访问 mitm.it 下载证书

# 3. 手机设置 → 安全 → 安装证书 → CA 证书
```

Android 7+ 默认不信任用户安装的 CA 证书（仅系统证书），需要：
- 方案 1：root 手机 → 将证书安装到系统证书目录
- 方案 2：使用 Magisk + MagiskTrustUserCerts 模块
- 方案 3：不 root，仅抓 HTTP 流量（部分 App 仍用 HTTP）

### 5.4 微信小程序特殊处理

微信有额外的证书固定（Certificate Pinning），即使安装了系统 CA 证书也无法抓包。

| 方案 | 条件 | 效果 |
|------|------|------|
| Xposed + JustTrustMe | root + Xposed 框架 | 绕过证书固定，可抓微信 HTTPS |
| LSPosed + TrustMeAlready | root + Magisk + LSPosed | 同上，更现代的方案 |
| 太极（免 root） | 无需 root | 部分有效，不稳定 |
| 手动 HAR（模式 A） | 无需任何配置 | 用电脑端微信开发者工具抓包 |

---

## 六、端口与网络拓扑

```
云服务器 101.32.242.14
├── :5037  ← ADB SSH 反向隧道（本地电脑 → 云服务器）
├── :7000  ← frp 控制通道
├── :7500  ← frp Web 管理面板
├── :8080  ← mitmproxy 代理（新增）
├── :9400  ← U2_Service (FastAPI)
└── :9501  ← AutoX.js (frp 映射)

手机
├── WiFi 代理 → 101.32.242.14:8080（新增）
├── uiautomator2 agent（通过 ADB 隧道）
├── :9500  ← AutoX.js HTTP 服务
└── frp 客户端 → 101.32.242.14:7000
```

防火墙需新增放行：`8080/tcp`（mitmproxy）

---

## 七、技能指令设计

### 新增指令

| 指令 | 说明 | 参数 |
|------|------|------|
| `capture_explore` | 边操作边抓包（核心指令） | `deviceId`, `platformName`, `appPackage`, `domainFilter` |
| `proxy_start` | 启动 mitmproxy + 设置手机代理 | `deviceId` |
| `proxy_stop` | 停止 mitmproxy + 清除手机代理 | `deviceId` |
| `proxy_status` | 检查代理环境状态 | 无 |
| `capture_explore_manual` | 启动抓包，人工操作手机，停止后分析 | `platformName`, `domainFilter` |

### 指令示例

一键自动化（AI 操作 + 抓包）：
```json
{
  "type": "capture_explore",
  "deviceId": "a394960e",
  "platformName": "聚宝猪",
  "appPackage": "com.jubaozhu.app",
  "domainFilter": ["jubaozhu.com", "jbz.cn"]
}
```

半自动（人工操作 + 自动抓包）：
```json
{ "type": "proxy_start", "deviceId": "a394960e" }
// ... 人工在手机上操作 App ...
{ "type": "proxy_stop", "deviceId": "a394960e" }
// 自动分析捕获的流量
```

---

## 八、安全边界

### SafetyGuard 在抓包场景的作用

CaptureOrchestrator 调用 VisionAgent 自动浏览时，SafetyGuard 全程生效：

| 操作 | 安全等级 | 行为 |
|------|---------|------|
| 浏览列表页、详情页 | SAFE | 直接执行，同时触发网络请求被抓包 |
| 点击搜索、筛选 | SAFE | 直接执行 |
| 滑动翻页 | SAFE | 直接执行 |
| 点击"出价"按钮 | DANGER | 暂停，请求人工确认 |
| 点击"支付" | BLOCKED | 直接拒绝 |

关键原则：抓包场景下 SafetyGuard 默认使用 `strict` 模式，绝不自动触发交易类操作。

### 抓包本身的安全性

- mitmproxy 仅在需要时启动，用完即停
- 手机代理用完后自动清除，不影响日常使用
- 捕获的流量数据保存在云服务器 `traffic_data/` 目录，不外传

---

## 九、实施路径

### 阶段 1：环境验证（人工，1-2 小时）

目标：确认 mitmproxy 能在当前架构下正常工作。

步骤：
1. 云服务器安装 mitmproxy：`uv add mitmproxy`
2. 启动 mitmproxy：`mitmproxy --listen-port 8080 --set block_global=false`
3. 手机设置 WiFi 代理指向云服务器
4. 手机浏览器访问 `http://mitm.it` 安装 CA 证书
5. 手机打开任意 App，观察 mitmproxy 是否捕获到流量
6. 尝试打开微信小程序，观察是否能解密 HTTPS

这一步的结果决定后续方案：
- ✅ 能抓到 HTTPS → 直接进阶段 2
- ⚠️ 能抓 HTTP 但 HTTPS 失败 → 需要处理证书问题
- ❌ 微信小程序完全抓不到 → 回退到模式 A（手动 HAR）

### 阶段 2：代码实现（全自动代码，可直接写）

前提：阶段 1 验证通过。

| 模块 | 文件 | 依赖 | 可测试性 |
|------|------|------|---------|
| MitmproxyAddon | `u2-server/mitm_addon.py` | mitmproxy | 可 mock 测试 |
| ProxyManager | `u2-server/proxy_manager.py` | adb, subprocess | 可 mock 测试 |
| CaptureOrchestrator | `u2-server/capture_orchestrator.py` | 上述所有模块 | 可 mock 测试 |
| FastAPI 端点 | `u2-server/server.py` 扩展 | 无新依赖 | 集成测试 |
| Bun 入口扩展 | `src/skill-cli.ts` + `src/types.ts` | 无新依赖 | 已有测试框架 |

### 阶段 3：微信小程序适配（需人工 + 环境）

如果目标是微信小程序（聚宝猪等），需要额外处理：

| 任务 | 方式 | 说明 |
|------|------|------|
| 手机 root | 人工 | Magisk 刷入 |
| 安装 LSPosed | 人工 | Magisk 模块 |
| 安装 TrustMeAlready | 人工 | LSPosed 模块，绕过证书固定 |
| 验证微信抓包 | 人工 | 打开小程序，确认 mitmproxy 能解密 |

如果不想 root，替代方案：
- 用电脑端微信开发者工具打开小程序 → 导出 HAR → 走模式 A
- 用 Android 模拟器（已 root）代替真机

---

## 十、风险评估

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| mitmproxy 无法解密微信 HTTPS | 高（未 root） | 无法实时抓微信小程序 | 回退模式 A（手动 HAR） |
| 手机代理影响其他 App | 低 | 其他 App 网络异常 | 用完立即清除代理 |
| mitmproxy 性能影响 | 低 | 请求延迟增加 | 仅在抓包时启用 |
| AI 误触发交易操作 | 低（有 SafetyGuard） | 经济损失 | strict 模式 + BLOCKED 规则 |
| 目标平台检测代理/中间人 | 中 | App 拒绝服务 | 部分 App 有反代理检测 |
| ADB 全局代理设置失败 | 低 | 需手动配置 WiFi 代理 | 提供手动配置指南 |

---

## 十一、关键决策点

在开始实施前，需要你确认以下信息：

1. **手机是否已 root？**
   - 已 root → 可以直接抓微信小程序 HTTPS
   - 未 root → 只能抓 HTTP，或用模式 A

2. **Android 版本？**
   - Android 7+ 需要系统级 CA 证书（需 root）
   - Android 6 及以下可以直接安装用户 CA 证书

3. **目标平台是微信小程序还是独立 App？**
   - 微信小程序 → 需要绕过微信证书固定（难度更高）
   - 独立 App → 只需安装 CA 证书即可

4. **是否愿意先用模式 A（手动 HAR）验证流程？**
   - 建议先用模式 A 跑通整个分析流程
   - 确认分析结果有价值后，再投入环境配置做模式 B

---

## 十二、推荐执行顺序

```
第 1 步：模式 A 验证（0 配置）
  → 手动操作手机 + 导出 HAR
  → traffic_load_har 分析
  → 确认接口分析结果有价值

第 2 步：环境验证（1-2 小时人工）
  → 安装 mitmproxy
  → 配置手机代理
  → 验证能否抓到目标 App 的 HTTPS

第 3 步：代码实现（全自动，可直接写）
  → MitmproxyAddon
  → ProxyManager
  → CaptureOrchestrator
  → FastAPI 端点 + Bun 入口

第 4 步：联调测试
  → capture_explore 一键执行
  → 验证 AI 操作 + 抓包联动
```
