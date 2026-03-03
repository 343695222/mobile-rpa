---
name: mobile-rpa
description: 移动端 RPA 自动化 Skill，通过 U2 Service (uiautomator2 + DashScope GUI-Plus 视觉模型) 控制 Android 设备，支持智能任务、截图、点击、滑动、文本输入、应用管理、视觉分析等操作
install: cd u2-server && uv sync
metadata: {"clawdbot":{"emoji":"📱","requires":{"bins":["curl"]}}}
---

# Mobile RPA Skill

本 Skill 为 OpenClaw AI Agent 提供移动端 RPA 能力，通过 U2 Service REST API 操控 Android 设备。

## ⚠️ 核心原则（必读）

1. **所有手机操作通过 HTTP API 执行**，服务地址 `http://localhost:9400`
2. **复杂任务优先用 smart_task**：涉及多步操作（如"找到某人并发消息"、"打开某 App 做某事"）时，直接调用 `/vision/smart_task`，让 GUI-Plus 视觉模型自动完成，不要自己一步步拼命令
3. **简单操作用基础 API**：单步操作（如截图、点击、启动 App）直接调对应端点
4. **设备 ID 固定为 `a394960e`**
5. 截图返回 base64 编码，保存为文件后用 `<qqimg>` 标签发送

## 🚀 智能任务（推荐，复杂操作首选）

对于需要多步操作的任务，直接用 smart_task，AI 视觉模型会自动截图→分析→操作→循环：

```bash
curl -s -X POST http://localhost:9400/vision/smart_task \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "goal": "在微信中找到王浩婷并发送消息你好", "max_steps": 20}'
```

适用场景举例：
- "打开微信发消息给张三" → smart_task
- "往下滑动找到某人" → smart_task
- "打开设置连接 WiFi" → smart_task
- "在淘宝搜索某商品" → smart_task

返回：`{"success": true, "message": "Task completed", "data": {"steps": [...], "final_action": "FINISH"}}`

## 📸 视觉分析

截图并用 AI 分析屏幕内容：

```bash
curl -s -X POST http://localhost:9400/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "prompt": "屏幕上有哪些可点击的按钮？"}'
```

## 🔍 OCR 文字识别

截图并用专用 OCR 模型（qwen-vl-ocr-latest）识别屏幕上所有文字：

```bash
curl -s -X POST http://localhost:9400/vision/ocr \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e"}'
```

返回：`{"success": true, "data": {"text": "[顶部-状态栏] 10:30 WiFi...\n[中部] 微信\n...", "model": "qwen-vl-ocr-latest"}}`

自定义 prompt（提取特定信息）：
```bash
curl -s -X POST http://localhost:9400/vision/ocr \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "prompt": "提取屏幕上所有联系人的名字，每行一个"}'
```

如果需要更灵活的分析（比如"屏幕上有哪些按钮"），用 `/vision/analyze` 自定义 prompt。

## 基础操作 API

### 截图
```bash
curl -s -X POST http://localhost:9400/device/a394960e/screenshot
```
返回：`{"success":true,"message":"OK","data":"<base64>"}`

截图保存为文件并发送：
```bash
curl -s -X POST http://localhost:9400/device/a394960e/screenshot | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('/tmp/screen.png','wb').write(base64.b64decode(d['data']))"
```
然后用 `<qqimg>/tmp/screen.png</qqimg>` 发送。

### 点击坐标
```bash
curl -s -X POST http://localhost:9400/device/a394960e/click \
  -H "Content-Type: application/json" -d '{"x":540,"y":960}'
```

### 滑动
```bash
curl -s -X POST http://localhost:9400/device/a394960e/swipe \
  -H "Content-Type: application/json" -d '{"x1":540,"y1":1500,"x2":540,"y2":500,"duration":0.5}'
```

### 输入文本（支持中文）
```bash
curl -s -X POST http://localhost:9400/device/a394960e/input_text \
  -H "Content-Type: application/json" -d '{"text":"你好"}'
```

### 按键
```bash
curl -s -X POST http://localhost:9400/device/a394960e/key_event \
  -H "Content-Type: application/json" -d '{"key_code":4}'
```
常用 key_code：4=返回, 3=Home, 187=最近任务, 66=回车

### 查找元素
```bash
curl -s -X POST http://localhost:9400/device/a394960e/find_element \
  -H "Content-Type: application/json" -d '{"by":"text","value":"微信"}'
```
by 可选：`text`, `resourceId`, `xpath`

### 点击元素（按文本/ID 查找并点击）
```bash
curl -s -X POST http://localhost:9400/device/a394960e/click_element \
  -H "Content-Type: application/json" -d '{"by":"text","value":"确定"}'
```

### 启动应用
```bash
curl -s -X POST http://localhost:9400/device/a394960e/app_start \
  -H "Content-Type: application/json" -d '{"package":"com.tencent.mm"}'
```

### 停止应用
```bash
curl -s -X POST http://localhost:9400/device/a394960e/app_stop \
  -H "Content-Type: application/json" -d '{"package":"com.tencent.mm"}'
```

### 获取当前前台应用
```bash
curl -s http://localhost:9400/device/a394960e/current_app
```

### 剪贴板
读取：
```bash
curl -s http://localhost:9400/device/a394960e/clipboard
```
写入：
```bash
curl -s -X POST http://localhost:9400/device/a394960e/clipboard \
  -H "Content-Type: application/json" -d '{"text":"要复制的内容"}'
```

### UI 层级树
```bash
curl -s http://localhost:9400/device/a394960e/ui_hierarchy
```

### 设备列表
```bash
curl -s http://localhost:9400/devices
```

### 健康检查
```bash
curl -s http://localhost:9400/health
```

## 常见应用包名

| 应用 | 包名 |
|------|------|
| 微信 | com.tencent.mm |
| QQ | com.tencent.mobileqq |
| 抖音 | com.ss.android.ugc.aweme |
| 支付宝 | com.eg.android.AlipayGphone |
| 淘宝 | com.taobao.taobao |
| 设置 | com.android.settings |
| 浏览器 | com.android.browser |

## 典型工作流

### 复杂任务（推荐 smart_task）
用户说"打开微信找到张三发消息你好"：
```bash
curl -s -X POST http://localhost:9400/vision/smart_task \
  -H "Content-Type: application/json" \
  -d '{"device_id": "a394960e", "goal": "打开微信，找到张三，发送消息你好", "max_steps": 20}'
```

### 简单任务（直接调 API）
用户说"截个图"：
```bash
curl -s -X POST http://localhost:9400/device/a394960e/screenshot | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('/tmp/screen.png','wb').write(base64.b64decode(d['data']))"
```
然后回复：`<qqimg>/tmp/screen.png</qqimg>`

用户说"打开微信"：
```bash
curl -s -X POST http://localhost:9400/device/a394960e/app_start -H "Content-Type: application/json" -d '{"package":"com.tencent.mm"}'
```

## 统一响应格式

```json
{"success": true, "message": "操作描述", "data": ...}
```

## 注意事项

1. 操作前先 `curl -s http://localhost:9400/health` 检查服务状态
2. 如果返回连接错误，说明 U2 Service 或 ADB 隧道断开
3. 点击坐标基于屏幕分辨率（OPPO 手机 1080x2400）
4. smart_task 超时时间较长（最多几分钟），适合复杂多步任务
5. 不要用 `adb shell` 直接操作手机，全部走 HTTP API
