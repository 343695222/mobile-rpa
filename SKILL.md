---
name: mobile-rpa
description: 移动端 RPA 自动化 Skill，通过 AutoJS 直连控制 Android 设备，支持截图、点击、滑动、文本输入、应用管理等操作
install: bun install
metadata: {"clawdbot":{"emoji":"📱","requires":{"bins":["bun"]}}}
---

# Mobile RPA Skill

本 Skill 为 OpenClaw AI Agent 提供移动端 RPA（机器人流程自动化）能力。

## ⚠️ 重要：必须使用 AutoJS 指令

**所有手机操作必须使用 `autox_*` 系列指令**，旧的 ADB 指令已废弃。

常用指令：
- 截图：`autox_screenshot`（不是 `screenshot`）
- 点击：`autox_click`（不是 `execute_action`）
- 滑动：`autox_swipe`
- 输入：`autox_input`
- 返回：`autox_key` (key="back")
- 打开应用：`autox_app_start`

## 能力范围

- 截图并返回 base64 图片
- 点击、长按、滑动、滚动屏幕
- 输入文本
- 按键（返回、Home、最近任务）
- 启动/停止应用
- 获取当前前台应用
- 查找和点击 UI 元素
- 获取 UI 树结构
- OCR 识别屏幕文字
- 读写剪贴板
- AI 驱动的智能任务循环

## 调用方式

通过向 Skill 发送 JSON 格式的指令来调用各项功能。

### AutoJS 指令（必须使用）

| 指令类型 | 说明 | 参数 |
|---------|------|------|
| `autox_health` | 检查 AutoJS 服务状态 | 无 |
| `autox_device_info` | 获取设备信息 | 无 |
| `autox_screenshot` | 截图（base64 JPEG） | 无 |
| `autox_click` | 点击坐标 | `x`, `y` |
| `autox_long_click` | 长按坐标 | `x`, `y`, `duration?` |
| `autox_swipe` | 滑动 | `x1`, `y1`, `x2`, `y2`, `duration?` |
| `autox_scroll` | 滚动屏幕 | `direction` (up/down) |
| `autox_input` | 输入文本 | `text` |
| `autox_key` | 按键 | `key` (back/home/recents/power) |
| `autox_app_start` | 启动应用 | `packageName` |
| `autox_app_stop` | 停止应用 | `packageName` |
| `autox_app_current` | 获取当前前台应用 | 无 |
| `autox_find_element` | 查找元素 | `by`, `value`, `timeout?` |
| `autox_click_element` | 查找并点击元素 | `by`, `value`, `timeout?` |
| `autox_ui_tree` | 获取 UI 树 | `maxDepth?` |
| `autox_ocr` | OCR 识别屏幕文字 | 无 |
| `autox_clipboard` | 读写剪贴板 | `text?` (有则写，无则读) |
| `autox_smart_task` | AI 驱动智能任务 | `taskGoal`, `maxSteps?` |

### 指令示例

截图：
```json
{ "type": "autox_screenshot" }
```

点击操作：
```json
{ "type": "autox_click", "x": 540, "y": 960 }
{ "type": "autox_long_click", "x": 540, "y": 960, "duration": 1000 }
```

滑动和滚动：
```json
{ "type": "autox_swipe", "x1": 540, "y1": 1500, "x2": 540, "y2": 500, "duration": 500 }
{ "type": "autox_scroll", "direction": "down" }
```

文本输入：
```json
{ "type": "autox_input", "text": "Hello World" }
```

按键：
```json
{ "type": "autox_key", "key": "back" }
{ "type": "autox_key", "key": "home" }
```

应用管理：
```json
{ "type": "autox_app_start", "packageName": "com.tencent.mm" }
{ "type": "autox_app_stop", "packageName": "com.tencent.mm" }
{ "type": "autox_app_current" }
```

元素操作：
```json
{ "type": "autox_find_element", "by": "text", "value": "微信" }
{ "type": "autox_click_element", "by": "text", "value": "确定", "timeout": 5000 }
```

UI 树和 OCR：
```json
{ "type": "autox_ui_tree", "maxDepth": 3 }
{ "type": "autox_ocr" }
```

剪贴板：
```json
{ "type": "autox_clipboard" }
{ "type": "autox_clipboard", "text": "要复制的内容" }
```

AI 智能任务：
```json
{ "type": "autox_smart_task", "taskGoal": "打开微信并发送消息给张三", "maxSteps": 20 }
```

检查服务状态：
```json
{ "type": "autox_health" }
```

## 响应格式

所有指令执行后返回统一的 JSON 响应：

```json
{
  "status": "success",
  "message": "Screenshot captured",
  "data": { "base64": "...", "format": "jpeg" }
}
```

## 前置条件

- 手机安装 AutoX.js 或 AutoJs6 App
- 开启无障碍服务和悬浮窗权限
- 运行 `autox/autox-server-v2.js` 脚本（端口 9500）
- SSH 隧道已建立（本地电脑执行 `adb forward` + `ssh -R`）

详细部署说明见 `deploy/DEPLOY-SIMPLE.md`。

## 架构

```
Agent → Bun/TS CLI → HTTP → AutoJS (手机:9500 via SSH隧道:9501)
```
