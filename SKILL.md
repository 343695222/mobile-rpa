---
name: mobile-rpa
description: 移动端 RPA 自动化 Skill，通过 U2 Service (uiautomator2 + DashScope GUI-Plus 视觉模型) 控制 Android 设备，支持智能任务、截图、点击、滑动、文本输入、应用管理、视觉分析等操作
install: cd u2-server && uv sync
metadata: {"clawdbot":{"emoji":"📱","requires":{"bins":["curl"]}}}
---

# Mobile RPA Skill

本 Skill 为 OpenClaw AI Agent 提供移动端 RPA 能力，通过 U2 Service REST API 操控 Android 设备。

## 🚨🚨🚨 最重要的规则（违反此规则 = 任务失败）

**收到任何手机操作指令时，你只需要执行一条 curl 命令调用 smart_task，然后等结果。就这么简单。**

```bash
curl -s -X POST http://localhost:9400/vision/smart_task \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "goal": "把用户的原始指令直接放这里", "max_steps": 20}'
```

**禁止事项（严格遵守）：**
- ❌ 禁止自己截图然后分析然后点击然后再截图（这样做会超时）
- ❌ 禁止把任务拆成多个 curl 命令一步步执行
- ❌ 禁止用 adb shell 命令操作手机
- ❌ 禁止先 screenshot 再 analyze 再 click（smart_task 内部已经做了这些）
- ❌ 禁止用 app_start 启动应用后再自己操作（直接把整个任务给 smart_task）

**唯一例外**：用户只是说"截个图"或"看看屏幕"时，用 screenshot API。

## ⚠️ 核心原则

1. **所有手机操作通过 HTTP API 执行**，服务地址 `http://localhost:9400`
2. **设备 ID 固定为 `a394960e`**
3. 截图返回 base64 编码，保存为文件后用 `<qqimg>` 标签发送

## 🚀 智能任务（99% 的情况用这个）

smart_task 内部有 GUI-Plus 视觉模型，会自动：截图→分析屏幕→决定操作→执行→再截图→循环，直到任务完成。

```bash
curl -s -X POST http://localhost:9400/vision/smart_task \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "goal": "用户的指令原文", "max_steps": 20}'
```

所有这些都用 smart_task：
- "打开京东快递小程序" → `goal: "打开京东快递小程序"`
- "打开微信发消息给张三" → `goal: "打开微信，找到张三，发送消息你好"`
- "往下滑动找到某人" → `goal: "往下滑动找到某人"`
- "打开设置连接 WiFi" → `goal: "打开设置连接WiFi"`
- "在淘宝搜索某商品" → `goal: "在淘宝搜索某商品"`
- "打开微信" → `goal: "打开微信"`（不要用 app_start，smart_task 更可靠）
- "查看最新消息" → `goal: "查看最新消息"`

返回格式：
```json
{"success": true, "message": "Task completed", "data": {"stepsCompleted": 5, "steps": [...]}}
```

smart_task 返回后，你可以：
1. 如果 success=true，告诉用户任务完成
2. 如果 success=false，告诉用户失败原因
3. 如果用户想看结果，再调一次 screenshot 截图发给用户

## 📸 截图（用户说"截个图"时用）

```bash
curl -s -X POST http://localhost:9400/device/a394960e/screenshot | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('/tmp/screen.png','wb').write(base64.b64decode(d['data']))"
```
然后用 `<qqimg>/tmp/screen.png</qqimg>` 发送。

## 📸 视觉分析（用户问"屏幕上有什么"时用）

```bash
curl -s -X POST http://localhost:9400/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "prompt": "屏幕上有哪些可点击的按钮？"}'
```

## 🔍 OCR 文字识别（用户说"识别屏幕文字"时用）

```bash
curl -s -X POST http://localhost:9400/vision/ocr \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e"}'
```

自定义 prompt：
```bash
curl -s -X POST http://localhost:9400/vision/ocr \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "prompt": "提取屏幕上所有联系人的名字"}'
```
