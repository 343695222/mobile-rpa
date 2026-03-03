---
name: mobile-rpa
description: 移动端 RPA 自动化 Skill，通过 AutoJS 直连控制 Android 设备，支持截图、点击、滑动、文本输入、应用管理等操作
install: bun install
metadata: {"clawdbot":{"emoji":"📱","requires":{"bins":["bun"]}}}
---

# Mobile RPA Skill

本 Skill 为 OpenClaw AI Agent 提供移动端 RPA（机器人流程自动化）能力。

## ⚠️ 执行方式（必读）

**所有手机操作通过 HTTP API 执行**，服务运行在 `http://localhost:9400`。

使用 `curl` 命令调用，所有响应为 JSON 格式：`{"success": true/false, "message": "...", "data": ...}`

**截图返回的 base64 图片可以直接用 `<qqimg>` 标签发送。**

## 常用操作速查

### 截图
```bash
curl -s -X POST http://localhost:9400/screenshot
```
返回：`{"success":true,"data":{"base64":"...","format":"jpeg"}}`

截图后将 base64 保存为文件再发送：
```bash
curl -s -X POST http://localhost:9400/screenshot | python3 -c "import sys,json; d=json.load(sys.stdin); open('/tmp/screen.jpg','wb').write(__import__('base64').b64decode(d['data']['base64']))"
```
然后用 `<qqimg>/tmp/screen.jpg</qqimg>` 发送。

### 点击
```bash
curl -s -X POST http://localhost:9400/click -H "Content-Type: application/json" -d '{"x":540,"y":960}'
```

### 长按
```bash
curl -s -X POST http://localhost:9400/long_click -H "Content-Type: application/json" -d '{"x":540,"y":960,"duration":1000}'
```

### 滑动
```bash
curl -s -X POST http://localhost:9400/swipe -H "Content-Type: application/json" -d '{"x1":540,"y1":1500,"x2":540,"y2":500,"duration":500}'
```

### 滚动
```bash
curl -s -X POST http://localhost:9400/scroll -H "Content-Type: application/json" -d '{"direction":"down"}'
```
direction 可选：`up`, `down`

### 输入文本
```bash
curl -s -X POST http://localhost:9400/input -H "Content-Type: application/json" -d '{"text":"Hello World"}'
```

### 按键
```bash
curl -s -X POST http://localhost:9400/key -H "Content-Type: application/json" -d '{"key":"back"}'
```
key 可选：`back`, `home`, `recents`, `power`

快捷方式：
```bash
curl -s -X POST http://localhost:9400/back
curl -s -X POST http://localhost:9400/home
```

### 启动应用
```bash
curl -s -X POST http://localhost:9400/app/start -H "Content-Type: application/json" -d '{"package":"com.tencent.mm"}'
```

### 停止应用
```bash
curl -s -X POST http://localhost:9400/app/stop -H "Content-Type: application/json" -d '{"package":"com.tencent.mm"}'
```

### 获取当前前台应用
```bash
curl -s http://localhost:9400/app/current
```

### 查找元素
```bash
curl -s -X POST http://localhost:9400/find_element -H "Content-Type: application/json" -d '{"by":"text","value":"微信","timeout":3000}'
```
by 可选：`text`, `id`, `desc`, `className`

### 点击元素（按文本/ID查找并点击）
```bash
curl -s -X POST http://localhost:9400/click_element -H "Content-Type: application/json" -d '{"by":"text","value":"确定","timeout":5000}'
```

### 获取 UI 树
```bash
curl -s http://localhost:9400/ui_tree
```

### OCR 识别屏幕文字
```bash
curl -s -X POST http://localhost:9400/ocr
```

### 剪贴板
读取：
```bash
curl -s http://localhost:9400/clipboard
```
写入：
```bash
curl -s -X POST http://localhost:9400/clipboard -H "Content-Type: application/json" -d '{"text":"要复制的内容"}'
```

### 检查服务状态
```bash
curl -s http://localhost:9400/health
```

### 获取设备信息
```bash
curl -s http://localhost:9400/device/info
```

### 执行自定义 AutoJS 脚本
```bash
curl -s -X POST http://localhost:9400/run_script -H "Content-Type: application/json" -d '{"script":"toast(\"Hello\")"}'
```

### AI 视觉分析
```bash
curl -s -X POST http://localhost:9400/vision/analyze -H "Content-Type: application/json" -d '{"prompt":"请描述屏幕上的内容"}'
```

### AI 智能任务
```bash
curl -s -X POST http://localhost:9400/vision/smart_task -H "Content-Type: application/json" -d '{"goal":"打开微信并发送消息给张三","max_steps":20}'
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

## 典型工作流示例

### 截图并发送给用户
```bash
# 1. 截图并保存
curl -s -X POST http://localhost:9400/screenshot | python3 -c "import sys,json; d=json.load(sys.stdin); open('/tmp/screen.jpg','wb').write(__import__('base64').b64decode(d['data']['base64']))"
# 2. 发送图片（用 qqimg 标签）
```
然后回复：`<qqimg>/tmp/screen.jpg</qqimg>`

### 打开微信
```bash
curl -s -X POST http://localhost:9400/app/start -H "Content-Type: application/json" -d '{"package":"com.tencent.mm"}'
```

## 注意事项

1. 所有操作前建议先 `curl -s http://localhost:9400/health` 检查服务是否正常
2. 如果服务返回连接错误，说明 AutoJS 或 SSH 隧道断开，需要用户重新连接
3. 截图返回 base64 编码的 JPEG 图片，需要解码后保存为文件才能发送
4. 点击坐标基于屏幕分辨率，OPPO 手机通常为 1080x2400
