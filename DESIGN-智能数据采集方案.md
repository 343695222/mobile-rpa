# OpenClaw 智能数据采集系统 — 设计方案 v2

## 一、核心思路

基于 **uiautomator2 (Python)** 替换自写 ADB 操作层，构建多策略、自适应、可学习的 App 数据采集系统。

```
OpenClaw Agent 发出采集指令
        ↓
  Bun/TS 入口 (skill-cli.ts)
        ↓ HTTP
  Python FastAPI 服务 (u2-server)
  ├── uiautomator2 (设备操作，截图 500ms vs 12s)
  ├── GLM-4.6V (视觉分析)
  ├── 策略选择器 (API > 抓包 > 复制 > OCR)
  └── 脚本仓库 (自动学习 + 复用)
        ↓
  数据标准化 → JSON 返回给 OpenClaw
```

**为什么用 uiautomator2 替换自写 ADB：**

| 对比项 | 自写 ADB (现有) | uiautomator2 |
|--------|----------------|--------------|
| 截图速度 | ~12s (screencap+pull) | ~500ms (设备端直出) |
| 元素查找 | dump XML → 传回 → 解析 | 设备端直接查找，毫秒级 |
| 点击操作 | `adb shell input tap` | 设备端 HTTP 调用，更快更稳 |
| 文本输入 | `adb shell input text` (不支持中文) | 支持中文输入 |
| App 管理 | 手动 `am start` | `app_start/app_stop` 一行搞定 |
| XPath | 无 | 内置 XPath 选择器 |
| 剪贴板 | 需要 hack | `d.clipboard` 直接读写 |
| 等待元素 | 无 | `d(text="xxx").wait(timeout=10)` |

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────┐
│                    OpenClaw Agent                      │
│              （自然语言 → JSON 指令）                    │
└────────────────────────┬─────────────────────────────┘
                         │ stdin/stdout JSON
                         ▼
┌──────────────────────────────────────────────────────┐
│              Bun/TS 入口 (skill-cli.ts)               │
│  保留现有指令 + 新增 collect_data 等                    │
│  所有设备操作 → 转发给 Python 服务                      │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP (localhost:9400)
                         ▼
┌──────────────────────────────────────────────────────┐
│           Python FastAPI 服务 (u2-server)              │
│           uv 管理环境 + 依赖                            │
│                                                        │
│  ┌────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ DeviceCtrl  │ │ DataCollector│ │ ScriptStore     │  │
│  │ uiautomator2│ │ 策略调度器   │ │ 脚本仓库(JSON)  │  │
│  │ 截图/点击/  │ │ API>抓包>    │ │ 自动学习+复用   │  │
│  │ 滑动/输入   │ │ 复制>OCR     │ │ 有效性验证      │  │
│  └────────────┘ └──────────────┘ └─────────────────┘  │
│                                                        │
│  ┌────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ VisionAgent│ │ Navigator    │ │ ScriptValidator │  │
│  │ GLM-4.6V   │ │ 导航管理器   │ │ 每日验证        │  │
│  │ 截图+分析  │ │ 探索→模板    │ │ 失效→重新探索   │  │
│  └────────────┘ └──────────────┘ └─────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 两层架构的好处

1. **Bun/TS 层**：保持 OpenClaw Skill 接口不变（stdin/stdout JSON），向后兼容
2. **Python 层**：用 uiautomator2 获得高性能设备操作，用 uv 管理干净的 Python 环境
3. **解耦**：Python 服务可以独立重启、升级，不影响 Skill 入口

---

## 三、Python 服务设计 (u2-server)

### 3.1 项目结构

```
u2-server/
├── pyproject.toml          # uv 项目配置
├── server.py               # FastAPI 入口
├── device.py               # uiautomator2 设备操作封装
├── vision.py               # GLM-4.6V 视觉分析
├── vision_agent.py         # 视觉驱动的智能决策
├── collector.py            # DataCollector 数据采集调度
├── strategies/
│   ├── __init__.py
│   ├── base.py             # 策略基类
│   ├── api_strategy.py     # API 直连
│   ├── rpa_copy_strategy.py # RPA + 剪贴板
│   └── rpa_ocr_strategy.py  # RPA + OCR
├── script_store.py         # 脚本仓库
├── navigator.py            # 导航管理器
├── validator.py            # 脚本验证器
└── scripts/                # 已学习的采集脚本 (JSON)
```

### 3.2 环境管理 (uv)

```bash
# 云服务器安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 初始化项目
cd u2-server
uv init
uv add fastapi uvicorn uiautomator2 httpx pillow

# 运行服务
uv run uvicorn server:app --host 0.0.0.0 --port 9400
```

`pyproject.toml`:
```toml
[project]
name = "u2-server"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "uiautomator2>=3",
    "httpx>=0.28",
    "pillow>=11",
]
```

### 3.3 FastAPI 接口设计

```python
# server.py — 核心 API 端点

# === 设备操作 (替代原 ADB 操作) ===
GET  /devices                          # 列出设备
GET  /device/{id}/info                 # 设备信息
POST /device/{id}/screenshot           # 截图 (base64)
POST /device/{id}/click                # 点击 {x, y}
POST /device/{id}/swipe                # 滑动 {x1,y1,x2,y2,duration}
POST /device/{id}/input_text           # 输入文字 {text} (支持中文)
POST /device/{id}/key_event            # 按键 {keyCode}
POST /device/{id}/app_start            # 启动App {package}
POST /device/{id}/app_stop             # 停止App {package}
GET  /device/{id}/current_app          # 当前前台App
POST /device/{id}/find_element         # 查找元素 {text/resourceId/xpath}
POST /device/{id}/click_element        # 点击元素 {text/resourceId/xpath}
GET  /device/{id}/clipboard            # 读剪贴板
POST /device/{id}/clipboard            # 写剪贴板 {text}
GET  /device/{id}/ui_hierarchy         # 获取UI树 (XML)

# === 视觉分析 ===
POST /vision/analyze                   # 截图+GLM分析 {deviceId, prompt}
POST /vision/smart_task                # 智能任务 {deviceId, goal}

# === 数据采集 (新功能) ===
POST /collect                          # 采集数据 {deviceId, app, dataType, query?}
GET  /scripts                          # 列出所有脚本
POST /scripts/validate                 # 验证所有脚本 {deviceId}
DELETE /scripts/{id}                   # 删除脚本

# === 健康检查 ===
GET  /health                           # 服务状态
```

### 3.4 设备操作封装 (device.py)

```python
import uiautomator2 as u2
import base64
from io import BytesIO

class DeviceManager:
    """管理多设备连接，缓存 u2 连接实例"""
    
    def __init__(self):
        self._devices: dict[str, u2.Device] = {}
    
    def get_device(self, device_id: str) -> u2.Device:
        if device_id not in self._devices:
            self._devices[device_id] = u2.connect(device_id)
        return self._devices[device_id]
    
    def list_devices(self) -> list[dict]:
        """通过 adb devices 列出设备"""
        import subprocess
        result = subprocess.run(
            ["adb", "devices", "-l"], capture_output=True, text=True
        )
        # 解析输出...
        return devices
    
    def screenshot_base64(self, device_id: str) -> str:
        """截图并返回 base64，~500ms"""
        d = self.get_device(device_id)
        img = d.screenshot()  # PIL Image
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    
    def click(self, device_id: str, x: int, y: int):
        d = self.get_device(device_id)
        d.click(x, y)
    
    def input_text(self, device_id: str, text: str):
        """支持中文输入"""
        d = self.get_device(device_id)
        d.send_keys(text)
    
    def find_and_click(self, device_id: str, **kwargs):
        """通过文本/resourceId/xpath 查找并点击"""
        d = self.get_device(device_id)
        if "text" in kwargs:
            d(text=kwargs["text"]).click()
        elif "resourceId" in kwargs:
            d(resourceId=kwargs["resourceId"]).click()
        elif "xpath" in kwargs:
            d.xpath(kwargs["xpath"]).click()
    
    def get_clipboard(self, device_id: str) -> str:
        d = self.get_device(device_id)
        return d.clipboard or ""
    
    def set_clipboard(self, device_id: str, text: str):
        d = self.get_device(device_id)
        d.set_clipboard(text)
    
    def app_start(self, device_id: str, package: str):
        d = self.get_device(device_id)
        d.app_start(package, stop=True)
    
    def current_app(self, device_id: str) -> dict:
        d = self.get_device(device_id)
        info = d.app_current()
        return {"package": info.package, "activity": info.activity}
```

### 3.5 视觉分析 (vision.py)

```python
import httpx
import json

class GlmVisionClient:
    """GLM-4.6V 视觉模型客户端，流式调用"""
    
    def __init__(self, api_key: str, model: str = "glm-4.6v"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    async def analyze(self, base64_image: str, prompt: str) -> dict:
        """发送图片+prompt，流式接收结果"""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": 500,
                    "stream": True,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": base64_image}},
                            {"type": "text", "text": prompt},
                        ]
                    }]
                }
            )
            
            content = ""
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                    delta = parsed["choices"][0]["delta"].get("content", "")
                    content += delta
                except:
                    pass
            
            return {"success": True, "description": content, "model": self.model}
```

### 3.6 智能导航 (navigator.py)

```python
class Navigator:
    """导航管理器：到达目标 App 的目标页面
    
    优先用已有脚本（快），没有则用视觉 Agent 探索（慢但智能）
    探索成功后自动保存为脚本供下次复用
    """
    
    def __init__(self, device_mgr, vision_client, script_store):
        self.device_mgr = device_mgr
        self.vision = vision_client
        self.scripts = script_store
    
    async def navigate_to(self, device_id: str, app: str, target_page: str) -> dict:
        # 1. 查找已有导航脚本
        script = self.scripts.find_navigation(app, target_page)
        if script and script["metadata"]["isValid"]:
            return await self._execute_script(device_id, script)
        
        # 2. 没有脚本 → 视觉 Agent 自主探索
        result = await self._explore(device_id, app, target_page)
        
        # 3. 探索成功 → 保存为脚本
        if result["success"]:
            self.scripts.save_navigation(app, target_page, result["steps"])
        
        return result
    
    async def _explore(self, device_id: str, app: str, target: str) -> dict:
        """用 GLM-4.6V 视觉 Agent 自主探索到达目标页面"""
        # 类似现有 smart_task 逻辑，但目标是"到达某个页面"
        ...
    
    async def _execute_script(self, device_id: str, script: dict) -> dict:
        """执行已保存的导航脚本（快速路径）"""
        for step in script["steps"]:
            action = step["action"]
            if action["type"] == "click":
                self.device_mgr.click(device_id, action["x"], action["y"])
            elif action["type"] == "click_element":
                self.device_mgr.find_and_click(device_id, **action["selector"])
            # ...
            await asyncio.sleep(0.5)
        return {"success": True}
```

### 3.7 数据采集调度 (collector.py)

```python
class DataCollector:
    """数据采集调度器 — 按优先级尝试各策略"""
    
    STRATEGY_PRIORITY = ["api", "rpa_copy", "rpa_ocr"]
    
    def __init__(self, device_mgr, vision, navigator, script_store):
        self.strategies = {
            "api": ApiStrategy(),
            "rpa_copy": RpaCopyStrategy(device_mgr, navigator),
            "rpa_ocr": RpaOcrStrategy(device_mgr, navigator, vision),
        }
        self.scripts = script_store
    
    async def collect(self, device_id: str, app: str, 
                      data_type: str, query: str = "",
                      force_strategy: str = None) -> dict:
        
        # 1. 查找已有脚本
        script = self.scripts.find(app, data_type)
        if script and script["metadata"]["isValid"]:
            strategy = self.strategies[script["strategy"]]
            result = await strategy.execute(device_id, script)
            if result["success"]:
                self.scripts.update_usage(script["id"])
                return result
            # 脚本执行失败 → 标记失效，继续探索
            self.scripts.mark_invalid(script["id"])
        
        # 2. 按优先级尝试各策略
        strategies = [force_strategy] if force_strategy else self.STRATEGY_PRIORITY
        
        for name in strategies:
            strategy = self.strategies.get(name)
            if not strategy:
                continue
            
            result = await strategy.explore(device_id, app, data_type, query)
            if result["success"]:
                # 保存为脚本
                self.scripts.save(app, data_type, name, result["script_config"])
                return result
        
        return {"success": False, "error": "所有策略均失败"}
```

### 3.8 采集策略

#### RPA + OCR 策略 (兜底，最通用)

```python
class RpaOcrStrategy:
    """截图 → GLM-4.6V 识别 → 滑动翻页 → 合并数据"""
    
    async def explore(self, device_id, app, data_type, query):
        # 1. 导航到目标页面
        nav = await self.navigator.navigate_to(device_id, app, data_type)
        if not nav["success"]:
            return nav
        
        # 2. 截图 + OCR
        all_items = []
        for page in range(3):  # 最多翻3页
            screenshot = self.device_mgr.screenshot_base64(device_id)
            result = await self.vision.analyze(
                screenshot,
                f"提取屏幕上所有与'{data_type}'相关的数据，JSON格式返回"
            )
            items = self._parse_items(result["description"])
            all_items.extend(items)
            
            # 滑动翻页
            d = self.device_mgr.get_device(device_id)
            d.swipe(540, 1600, 540, 400, duration=0.5)
            await asyncio.sleep(1)
        
        return {
            "success": True,
            "items": all_items,
            "strategy": "rpa_ocr",
            "script_config": nav.get("steps", [])
        }
```

#### RPA + 剪贴板策略 (文本数据优先)

```python
class RpaCopyStrategy:
    """导航到页面 → 长按全选复制 → 读剪贴板"""
    
    async def explore(self, device_id, app, data_type, query):
        # 1. 导航
        nav = await self.navigator.navigate_to(device_id, app, data_type)
        if not nav["success"]:
            return nav
        
        # 2. 尝试长按 → 全选 → 复制
        d = self.device_mgr.get_device(device_id)
        d.long_click(540, 960)
        await asyncio.sleep(0.5)
        
        # 尝试点击"全选"
        if d(text="全选").exists(timeout=2):
            d(text="全选").click()
            await asyncio.sleep(0.3)
        
        # 尝试点击"复制"
        if d(text="复制").exists(timeout=2):
            d(text="复制").click()
            await asyncio.sleep(0.3)
            
            text = d.clipboard
            if text:
                return {
                    "success": True,
                    "items": [{"text": text}],
                    "strategy": "rpa_copy",
                }
        
        return {"success": False, "error": "复制失败"}
```

#### API 直连策略

```python
class ApiStrategy:
    """直接调用已知 API 端点"""
    
    async def execute(self, device_id, script):
        config = script["extraction"]["config"]
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                config["method"],
                config["url"],
                headers=config.get("headers", {}),
                params=config.get("params"),
                json=config.get("body"),
            )
            data = resp.json()
            # 按 dataPath 提取数据
            items = self._extract(data, config["dataPath"])
            return {"success": True, "items": items, "strategy": "api"}
```

---

## 四、Bun/TS 层改造

现有 `skill-cli.ts` 改为**薄代理层**，所有设备操作转发给 Python 服务：

```typescript
// skill-cli.ts 中新增 Python 服务调用
const U2_SERVER = process.env.U2_SERVER || "http://localhost:9400";

async function callU2(path: string, body?: any): Promise<any> {
  const resp = await fetch(`${U2_SERVER}${path}`, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return resp.json();
}

// 新增指令路由
case "collect_data":
  return await callU2("/collect", {
    deviceId: command.deviceId,
    app: command.app,
    dataType: command.dataType,
    query: command.query,
  });
```

**保持向后兼容**：现有的 `list_devices`、`get_screen`、`execute_action` 等指令继续工作，但底层改为调用 Python 服务（更快）。

---

## 五、部署方案

### 云服务器新增步骤

```bash
# 1. 安装 uv (Python 包管理)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# 2. 上传 u2-server 目录
scp -r u2-server root@101.32.242.14:~/.openclaw/workspace/skills/mobile-rpa/

# 3. 安装依赖
cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
uv sync

# 4. 初始化 uiautomator2（推送 agent 到手机，只需一次）
uv run python -c "import uiautomator2 as u2; d = u2.connect('a394960e'); print(d.info)"

# 5. 启动 Python 服务（后台运行）
nohup uv run uvicorn server:app --host 127.0.0.1 --port 9400 &

# 6. 验证
curl http://localhost:9400/health
curl http://localhost:9400/devices
```

### 日常启动顺序

```
1. 本地：手机 USB 连接 + SSH 隧道
2. 云端：启动 Python 服务（如果没在跑）
   cd ~/.openclaw/workspace/skills/mobile-rpa/u2-server
   uv run uvicorn server:app --host 127.0.0.1 --port 9400 &
3. 云端：OpenClaw 调用 Skill
   echo '{"type": "collect_data", ...}' | bun run src/skill-cli.ts
```

---

## 六、新增指令汇总

| 指令类型 | 说明 | 参数 |
|---------|------|------|
| `collect_data` | 从指定 App 采集数据 | `deviceId`, `app`, `dataType`, `query?`, `forceStrategy?` |
| `validate_scripts` | 验证所有已保存脚本 | `deviceId` |
| `list_scripts` | 列出所有采集脚本 | 无 |

### 示例

```json
{"type": "collect_data", "deviceId": "a394960e", "app": "微信", "dataType": "联系人列表"}
{"type": "collect_data", "deviceId": "a394960e", "app": "抖音", "dataType": "推荐视频", "forceStrategy": "rpa_ocr"}
{"type": "list_scripts"}
{"type": "validate_scripts", "deviceId": "a394960e"}
```

---

## 七、速度预估 (uiautomator2 vs 现有)

| 操作 | 现有 ADB | uiautomator2 | 提升 |
|------|---------|-------------|------|
| 截图 | ~12s | ~500ms | 24x |
| 点击 | ~200ms | ~50ms | 4x |
| 元素查找 | ~3s (dump+parse) | ~100ms | 30x |
| 文本输入 | ~300ms (不支持中文) | ~100ms (支持中文) | 3x |
| App 启动 | 手动 am start | ~1s (自动等待) | - |
| 读剪贴板 | 不支持 | ~50ms | ∞ |

**整体采集速度预估：**

| 场景 | 预估耗时 |
|------|---------|
| 有脚本 + API 策略 | <1s |
| 有脚本 + RPA复制 | 3-8s |
| 有脚本 + OCR | 5-20s (截图快了，主要等 GLM API) |
| 无脚本（首次探索）| 30s-3min |

---

## 八、实现计划（分阶段）

### 第一阶段：Python 服务基础 + 设备操作

1. uv 项目初始化 + pyproject.toml
2. FastAPI 服务框架 (server.py)
3. DeviceManager (device.py) — uiautomator2 封装
4. 设备操作 API 端点（截图、点击、滑动、输入、元素查找）
5. Bun/TS 层改造 — 调用 Python 服务
6. 部署文档更新

### 第二阶段：视觉分析迁移

7. GLM-4.6V 客户端 (vision.py) — 从 TS 迁移到 Python
8. VisionAgent (vision_agent.py) — smart_task 迁移
9. 视觉分析 API 端点

### 第三阶段：数据采集核心

10. ScriptStore (script_store.py) — 脚本仓库
11. Navigator (navigator.py) — 导航管理器
12. RpaOcrStrategy — OCR 采集策略
13. RpaCopyStrategy — 剪贴板采集策略
14. DataCollector (collector.py) — 调度器
15. collect_data / list_scripts 指令

### 第四阶段：自动验证 + API 策略

16. ScriptValidator — 脚本验证器
17. ApiStrategy — API 直连策略
18. validate_scripts 指令
19. 定时验证机制
