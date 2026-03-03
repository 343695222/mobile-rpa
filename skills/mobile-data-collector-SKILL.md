---
name: mobile-data-collector
description: 多策略智能数据采集编排器，自动选择最优采集策略，支持脚本学习与复用，协调 U2 和 AutoX 自动化引擎从任意 App 采集数据
requires:
  - mobile-u2
install: cd u2-server && uv sync
---

# Mobile Data Collector Skill

多策略数据采集编排器，能够从任意 Android App 智能采集数据。核心流程为"探索→学习→复用"：首次采集时自动探索最优策略，成功后将采集流程保存为可复用脚本；后续采集优先使用已保存脚本，大幅提升效率。

## 能力范围

### 数据采集
- 按优先级自动选择采集策略：API 直连 > RPA 剪贴板复制 > 截图 OCR
- 支持强制指定采集策略
- 采集成功后自动保存脚本供复用
- 已有脚本时优先复用，脚本失败时自动标记无效并回退到探索模式

### 脚本管理
- 以 JSON 文件格式存储采集脚本（`u2-server/scripts/` 目录）
- 每个脚本包含：目标 App、数据类型、采集策略、导航步骤、提取配置
- 支持按 App 名称和数据类型查找脚本
- 支持列出所有脚本、删除脚本、标记脚本无效
- 记录脚本使用次数和最后使用时间

### 导航管理
- 通过 VisionAgent 智能探索到达目标 App 的目标页面
- 优先使用已保存的导航脚本
- 探索成功后自动保存导航脚本

### 脚本验证
- 逐一执行所有已保存脚本，检查是否仍能成功采集
- 验证失败的脚本自动标记为无效
- 返回验证摘要（总数、成功数、失败数）

## 采集策略说明

| 策略 | 优先级 | 说明 | 适用场景 |
|------|--------|------|---------|
| `api` | 最高 | 直接调用 App 的 HTTP API 获取数据 | 已知 API 接口的 App |
| `rpa_copy` | 中 | 导航到目标页面→长按→全选→复制→读剪贴板 | 文本内容为主的页面 |
| `rpa_ocr` | 最低 | 导航到目标页面→截图→GLM-4.6V OCR 识别→翻页→合并 | 复杂布局或图片内容 |

## 指令调用

通过 Bun 入口层（`skill-cli.ts`）发送 JSON 指令，或直接调用 U2 服务 REST API。

### 通过 Bun 入口

数据采集：
```json
{
  "type": "collect_data",
  "deviceId": "emulator-5554",
  "app": "微信",
  "dataType": "联系人列表",
  "query": "",
  "forceStrategy": null
}
```

强制使用指定策略：
```json
{
  "type": "collect_data",
  "deviceId": "emulator-5554",
  "app": "微信",
  "dataType": "聊天记录",
  "forceStrategy": "rpa_ocr"
}
```

列出已保存脚本：
```json
{ "type": "list_scripts" }
```

验证所有脚本：
```json
{ "type": "validate_scripts", "deviceId": "emulator-5554" }
```

### 通过 U2 REST API

```bash
# 数据采集
curl -X POST http://localhost:9400/collect \
  -H "Content-Type: application/json" \
  -d '{"device_id": "emulator-5554", "app": "微信", "data_type": "联系人列表"}'

# 列出脚本
curl http://localhost:9400/scripts

# 验证脚本
curl -X POST http://localhost:9400/scripts/validate \
  -H "Content-Type: application/json" \
  -d '{"device_id": "emulator-5554"}'

# 删除脚本
curl -X DELETE http://localhost:9400/scripts/{script_id}
```

## 采集结果格式

```json
{
  "success": true,
  "items": [
    { "name": "张三", "phone": "138xxxx1234" },
    { "name": "李四", "phone": "139xxxx5678" }
  ],
  "strategy": "rpa_copy",
  "scriptId": "a1b2c3d4-...",
  "error": null
}
```

失败时：
```json
{
  "success": false,
  "items": [],
  "strategy": "rpa_ocr",
  "scriptId": null,
  "error": "所有策略均失败 (尝试: api, rpa_copy, rpa_ocr): ..."
}
```

## 脚本数据结构

每个采集脚本以 JSON 文件存储在 `u2-server/scripts/` 目录，包含以下字段：

```json
{
  "id": "uuid-string",
  "app": "微信",
  "dataType": "联系人列表",
  "strategy": "rpa_copy",
  "navigation": [
    { "order": 1, "action": { "type": "click_element", "selector": { "by": "text", "value": "通讯录" } }, "description": "点击通讯录标签" }
  ],
  "extraction": {
    "type": "clipboard",
    "config": { "longPressX": 540, "longPressY": 800, "selectAllText": "全选", "copyText": "复制" }
  },
  "metadata": {
    "createdAt": "2024-01-01T00:00:00Z",
    "lastUsedAt": "2024-01-02T00:00:00Z",
    "lastValidatedAt": "2024-01-01T12:00:00Z",
    "useCount": 5,
    "isValid": true
  }
}
```

## 前置条件

- U2 服务（`mobile-u2`）已启动并运行于 9400 端口
- Android 设备已连接且 uiautomator2 agent 已推送
- （视觉分析/OCR 策略）环境变量 `GLM_API_KEY` 已设置
