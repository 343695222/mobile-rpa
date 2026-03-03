---
name: mobile-autox
description: 手机端 JavaScript 自动化服务 v2，完整替代 ADB + uiautomator2，支持截图、点击、滑动、元素操作、OCR、App 管理等全部功能
requires:
  - autoxjs-app 或 autojs6-app
  - frp
install: 在手机端安装 AutoX.js 或 AutoJs6 APK 并导入 autox-server-v2.js 脚本
---

# Mobile AutoX Skill v2

运行于 Android 手机端的 HTTP 自动化服务，通过 Android 无障碍服务直接在手机上执行自动化操作。

**v2 版本完整替代 ADB + uiautomator2**，所有操作在手机本地执行，延迟极低。

服务端口 9500，通过 frp 隧道映射到云服务器端口 9501。

## 架构对比

```
旧架构（ADB）:
Agent → Python → ADB SSH隧道 → uiautomator2 → 手机
                 ↑ 延迟瓶颈

新架构（AutoJS v2）:
Agent → Python → frp隧道 → AutoJS (手机:9500)
                 ↑ 单一隧道，操作本地执行
```

## 能力范围

- 截图（base64 JPEG）
- 点击、长按、滑动、滚动
- 文本输入
- 按键（返回、Home、最近任务）
- App 启动/停止/获取当前前台 App
- 元素查找（text/textContains/id/className/desc/descContains）
- 元素点击、等待元素出现
- UI 树获取（无障碍节点）
- OCR 文字识别
- 剪贴板读写
- 设备信息获取
- 自定义 JavaScript 脚本执行

## HTTP API 端点

服务地址：手机端 `http://localhost:9500`，云服务器通过 frp 隧道访问 `http://localhost:9501`

### 基础操作

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/health` | — | 健康检查 |
| POST | `/device_info` | — | 设备信息 |
| POST | `/screenshot` | — | 截图（base64 JPEG） |
| POST | `/click` | `{x, y}` | 点击坐标 |
| POST | `/long_click` | `{x, y, duration?}` | 长按 |
| POST | `/swipe` | `{x1, y1, x2, y2, duration?}` | 滑动 |
| POST | `/scroll` | `{direction}` | 滚动（up/down） |
| POST | `/input` | `{text}` | 输入文本 |
| POST | `/key` | `{key}` | 按键（back/home/recents/power） |

### App 管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/app/start` | `{package}` | 启动 App |
| POST | `/app/stop` | `{package}` | 停止 App |
| POST | `/app/current` | — | 获取当前前台 App |

### 元素操作

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/find_element` | `{by, value, timeout?}` | 查找单个元素 |
| POST | `/find_elements` | `{by, value}` | 查找多个元素 |
| POST | `/click_element` | `{by, value, timeout?}` | 查找并点击元素 |
| POST | `/wait_element` | `{by, value, timeout?}` | 等待元素出现 |
| POST | `/ui_tree` | `{maxDepth?}` | 获取 UI 树 |

### 其他

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/ocr` | — | OCR 文字识别 |
| POST | `/clipboard` | `{text?}` | 剪贴板（有 text 写入，无 text 读取） |
| POST | `/run_script` | `{script}` | 执行自定义 JS 脚本 |

### 选择器类型（by 参数）

- `text` - 精确匹配文本
- `textContains` - 包含文本
- `id` - 资源 ID
- `className` - 类名
- `desc` - 内容描述
- `descContains` - 包含内容描述

## 请求/响应示例

健康检查：
```bash
curl -X POST http://localhost:9501/health
```
```json
{
  "success": true,
  "data": {
    "version": "2.0",
    "status": "running",
    "port": 9500,
    "screenCapture": true,
    "ts": "2024-01-15T10:30:00.000Z"
  }
}
```

截图：
```bash
curl -X POST http://localhost:9501/screenshot
```
```json
{
  "success": true,
  "data": {
    "base64": "/9j/4AAQSkZJRg...",
    "format": "jpeg",
    "length": 123456
  }
}
```

点击元素：
```bash
curl -X POST http://localhost:9501/click_element \
  -H "Content-Type: application/json" \
  -d '{"by": "text", "value": "确定", "timeout": 5000}'
```
```json
{
  "success": true,
  "data": {
    "clicked": true,
    "element": {
      "text": "确定",
      "bounds": {"left": 200, "top": 800, "right": 300, "bottom": 850},
      "centerX": 250,
      "centerY": 825
    }
  }
}
```

启动 App：
```bash
curl -X POST http://localhost:9501/app/start \
  -H "Content-Type: application/json" \
  -d '{"package": "com.tencent.mm"}'
```
```json
{ "success": true, "data": { "package": "com.tencent.mm" } }
```

## 响应格式

成功：
```json
{ "success": true, "data": { ... } }
```

失败：
```json
{ "success": false, "error": "错误描述" }
```

## 前置条件

1. Android 手机已安装 AutoX.js（v6.x+）或 AutoJs6 App
2. App 已开启无障碍服务权限
3. App 已授予悬浮窗权限
4. App 已授予截图权限（首次运行脚本时会弹出）
5. `autox-server-v2.js` 脚本已导入并运行
6. frp 客户端已在手机端 Termux 中运行
7. frp 服务端已在云服务器运行

## 部署步骤

详见 `deploy/DEPLOY-SIMPLE.md`

快速步骤：
1. 手机安装 AutoX.js 或 AutoJs6
2. 开启无障碍服务和悬浮窗权限
3. 导入并运行 `autox/autox-server-v2.js`
4. 手机安装 Termux，配置并运行 frp 客户端
5. 云服务器运行 frp 服务端
6. 验证：`curl -X POST http://localhost:9501/health`

## 脚本文件说明

| 文件 | 说明 |
|------|------|
| `autox-server-v2.js` | **推荐** - 完整功能版本，替代 ADB + uiautomator2 |
| `autox-server-autox.js` | 旧版 - 仅基础功能（AutoX.js 专用） |
| `autox-server-autojs6.js` | 旧版 - 仅基础功能（AutoJs6 专用） |
