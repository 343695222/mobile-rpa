---
name: mobile-u2
description: 基于 uiautomator2 的高性能 Android 设备操作服务，提供快速截图、元素查找、文本输入和 DashScope 百炼平台视觉分析能力
requires:
  - python3.10
  - uv
  - adb
install: cd u2-server && uv sync
---

# Mobile U2 Skill

基于 uiautomator2 和 FastAPI 的 Python 设备操作服务，运行于云服务器 9400 端口。相比 ADB 直连方式，截图速度提升约 24 倍（500ms vs 12s），并支持中文输入、XPath 选择器、剪贴板读写等高级功能。同时集成 DashScope 百炼平台视觉语言模型（GUI-Plus + 通义千问 VL），提供屏幕截图分析和视觉驱动的智能任务执行能力。

## 能力范围

### 设备操作
- 列出已连接设备、获取设备详细信息
- 高速截图（base64 格式）
- 点击、滑动、按键操作
- 文本输入（支持中文字符）
- 元素查找（支持 text、resourceId、xpath 三种选择器）
- 元素点击
- 剪贴板读写
- UI 层级树获取
- App 启动、停止、获取当前前台 App

### 视觉分析
- 截图 + DashScope 视觉分析（自定义 prompt，通义千问 VL 模型）
- 智能任务循环：截图→GUI-Plus 分析→决定操作→执行操作，直到任务完成或达到步骤上限

### 数据采集
- 多策略数据采集编排（api > rpa_copy > rpa_ocr）
- 采集脚本管理（列出、验证、删除）

## REST API 端点

服务地址：`http://localhost:9400`

### 基础端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/devices` | 列出已连接设备 |
| GET | `/device/{id}/info` | 设备详细信息 |

### 设备操作端点

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/device/{id}/screenshot` | — | 截图，返回 base64 |
| POST | `/device/{id}/click` | `{x, y}` | 点击坐标 |
| POST | `/device/{id}/swipe` | `{x1, y1, x2, y2, duration}` | 滑动 |
| POST | `/device/{id}/input_text` | `{text}` | 输入文字 |
| POST | `/device/{id}/key_event` | `{key_code}` | 按键事件 |
| POST | `/device/{id}/find_element` | `{by, value}` | 查找元素 |
| POST | `/device/{id}/click_element` | `{by, value}` | 点击元素 |
| GET | `/device/{id}/clipboard` | — | 读剪贴板 |
| POST | `/device/{id}/clipboard` | `{text}` | 写剪贴板 |
| GET | `/device/{id}/ui_hierarchy` | — | 获取 UI 树 |
| POST | `/device/{id}/app_start` | `{package}` | 启动 App |
| POST | `/device/{id}/app_stop` | `{package}` | 停止 App |
| GET | `/device/{id}/current_app` | — | 当前前台 App |

### 视觉分析端点

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/vision/analyze` | `{device_id, prompt}` | 截图 + DashScope 分析 |
| POST | `/vision/smart_task` | `{device_id, goal, max_steps?}` | 智能任务循环 |

### 数据采集端点

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/collect` | `{device_id, app, data_type, query?, force_strategy?}` | 数据采集 |
| GET | `/scripts` | — | 列出采集脚本 |
| POST | `/scripts/validate` | `{device_id}` | 验证所有脚本 |
| DELETE | `/scripts/{id}` | — | 删除脚本 |

## 请求/响应示例

截图：
```bash
curl -X POST http://localhost:9400/device/emulator-5554/screenshot
```
```json
{ "success": true, "message": "Screenshot captured", "data": "iVBORw0KGgo..." }
```

点击：
```bash
curl -X POST http://localhost:9400/device/emulator-5554/click \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 1200}'
```

视觉分析：
```bash
curl -X POST http://localhost:9400/vision/analyze \
  -H "Content-Type: application/json" \
  -d '{"device_id": "emulator-5554", "prompt": "屏幕上有哪些可点击的按钮？"}'
```

## 统一响应格式

```json
{
  "success": true,
  "message": "操作描述",
  "data": {}
}
```

## 前置条件

- Python 3.10+
- uv（Python 包管理工具）
- ADB 已安装，Android 设备已连接
- uiautomator2 agent 已推送到手机（`python -m uiautomator2 init`）
- （视觉分析）环境变量 `DASHSCOPE_API_KEY` 已设置

## 启动方式

```bash
cd u2-server
uv sync
uv run uvicorn server:app --host 0.0.0.0 --port 9400
```
