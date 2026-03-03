# 设计文档：竞品平台自动分析与数据采集 (platform-analyzer)

## 概述

在现有 u2-server 基础上新增 platform-analyzer 模块，实现"探索→抓包→分析→生成脚本→验证→对接"的自动化流程。核心设计原则：能用代码确定性解决的绝不用 AI，AI 只用在需要"理解"和"判断"的环节。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                  AnalysisOrchestrator                     │
│              （编排整个分析流程的控制器）                    │
│                                                           │
│  analyze_platform("聚宝猪", device_id) → 完整报告         │
└────────┬──────────┬──────────┬──────────┬────────────────┘
         │          │          │          │
    ┌────▼───┐ ┌───▼────┐ ┌──▼───┐ ┌───▼──────┐
    │Platform│ │Traffic │ │Traffic│ │Interface │
    │Explorer│ │Capture │ │Analyz.│ │Analyzer  │
    │(AI驱动)│ │(代码)  │ │(代码) │ │(AI驱动)  │
    └────┬───┘ └───┬────┘ └──┬───┘ └───┬──────┘
         │         │         │         │
    ┌────▼───┐     │    ┌───▼────┐ ┌──▼────────┐
    │Vision  │     │    │Endpoint│ │Difficulty  │
    │Agent   │     │    │Extract │ │Assessor    │
    │(已有)  │     │    │(代码)  │ │(AI驱动)    │
    └────────┘     │    └────────┘ └──┬─────────┘
                   │                  │
              ┌────▼──────────────────▼──────┐
              │      ApiScriptGenerator       │
              │    （生成 ScriptStore 脚本）    │
              └────────────┬─────────────────┘
                           │
              ┌────────────▼─────────────────┐
              │       ScriptVerifier          │
              │    （执行脚本验证数据）         │
              └────────────┬─────────────────┘
                           │
              ┌────────────▼─────────────────┐
              │        DataMapper             │
              │  （标准化 + 推送到目标系统）    │
              └──────────────────────────────┘
```

## 新增文件结构

```
u2-server/
├── traffic_capture.py      # 流量捕获（mitmproxy addon）
├── traffic_analyzer.py     # 流量分析（纯数据处理）
├── interface_analyzer.py   # 接口智能分析（GLM 驱动）
├── script_generator.py     # 采集脚本生成
├── script_verifier.py      # 脚本验证
├── data_mapper.py          # 数据标准化与对接
├── platform_explorer.py    # 平台探索（复用 VisionAgent）
├── analysis_orchestrator.py # 分析编排器
├── platform_configs/       # 平台配置目录
│   └── example.json        # 平台配置模板
└── analysis_reports/       # 分析报告输出目录
```


## 组件详细设计

### 1. TrafficCapture — 流量捕获 ⚙️ 全自动代码

这是整个方案的关键新增能力。用 mitmproxy 的 Python API 做 addon，不需要启动独立进程。

```python
# u2-server/traffic_capture.py

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import threading
from pathlib import Path

@dataclass
class TrafficRecord:
    """单条 HTTP 流量记录"""
    url: str
    method: str
    request_headers: dict
    request_body: str | None
    response_status: int
    response_headers: dict
    response_body: str | None  # 截断到 50KB
    content_type: str
    timestamp: str
    duration_ms: float
    
    @property
    def is_api(self) -> bool:
        """判断是否为 API 请求（返回 JSON）"""
        ct = self.content_type.lower()
        return "json" in ct or "text/plain" in ct
    
    @property
    def is_static(self) -> bool:
        """判断是否为静态资源"""
        ct = self.content_type.lower()
        return any(t in ct for t in ["image/", "css", "javascript", "font"])


class TrafficCapture:
    """流量捕获管理器
    
    两种工作模式：
    1. 内嵌模式：作为 mitmproxy addon 运行（需要 mitmproxy 进程）
    2. 日志模式：读取 mitmproxy 导出的 HAR/flow 文件（更简单）
    
    推荐先用日志模式，稳定后再切内嵌模式。
    """
    
    def __init__(self, data_dir: str | None = None):
        self._dir = Path(data_dir or "traffic_data")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._records: list[TrafficRecord] = []
        self._recording = False
        self._domain_filter: list[str] = []
        self._platform_name: str = ""
    
    def start_recording(self, platform_name: str, domain_filter: list[str]) -> None:
        """开始录制"""
        self._platform_name = platform_name
        self._domain_filter = domain_filter
        self._records = []
        self._recording = True
    
    def stop_recording(self) -> list[TrafficRecord]:
        """停止录制并返回记录"""
        self._recording = False
        return list(self._records)
    
    def add_record(self, record: TrafficRecord) -> None:
        """添加一条记录（由 mitmproxy addon 或 HAR 解析器调用）"""
        if not self._recording:
            return
        # 域名过滤
        if self._domain_filter:
            from urllib.parse import urlparse
            domain = urlparse(record.url).hostname or ""
            if not any(f in domain for f in self._domain_filter):
                return
        self._records.append(record)
    
    def load_from_har(self, har_path: str) -> list[TrafficRecord]:
        """从 HAR 文件加载流量记录（日志模式）"""
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
        records = []
        for entry in har.get("log", {}).get("entries", []):
            req = entry.get("request", {})
            resp = entry.get("response", {})
            record = TrafficRecord(
                url=req.get("url", ""),
                method=req.get("method", ""),
                request_headers={h["name"]: h["value"] for h in req.get("headers", [])},
                request_body=req.get("postData", {}).get("text"),
                response_status=resp.get("status", 0),
                response_headers={h["name"]: h["value"] for h in resp.get("headers", [])},
                response_body=resp.get("content", {}).get("text", "")[:50000],
                content_type=resp.get("content", {}).get("mimeType", ""),
                timestamp=entry.get("startedDateTime", ""),
                duration_ms=entry.get("time", 0),
            )
            records.append(record)
        self._records = records
        return records
    
    def save_to_file(self) -> str:
        """保存当前记录到 JSON 文件"""
        platform_dir = self._dir / self._platform_name
        platform_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = platform_dir / f"traffic_{ts}.json"
        data = [asdict(r) for r in self._records]
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)
    
    def get_records(self) -> list[TrafficRecord]:
        return list(self._records)
    
    def clear(self) -> None:
        self._records = []
        self._recording = False
```

### 2. TrafficAnalyzer — 流量分析 ⚙️ 全自动代码

纯数据处理，零 AI 依赖，100% 可测试。

```python
# u2-server/traffic_analyzer.py

from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
import json
import re

@dataclass
class ApiEndpoint:
    """识别出的 API 端点"""
    url_pattern: str          # /api/v1/auctions
    base_url: str             # https://api.example.com
    method: str               # GET / POST
    auth_type: str            # none / bearer / cookie / custom_sign / unknown
    auth_headers: list[str]   # 涉及鉴权的 header 名
    request_params: dict      # 参数名 → 类型描述
    response_sample: str      # 响应体样本（截断）
    response_schema: dict     # 响应 JSON 结构摘要（key → type）
    sample_count: int         # 捕获到的样本数
    avg_duration_ms: float    # 平均响应时间

@dataclass
class AnalysisResult:
    """流量分析结果"""
    platform_name: str
    total_requests: int
    api_endpoints: list[ApiEndpoint]
    page_requests: list[str]   # HTML 页面 URL
    static_resources: int      # 静态资源数量
    domains: list[str]         # 涉及的域名

class TrafficAnalyzer:
    """流量分析器 — 从原始流量中提取结构化接口信息"""
    
    # 常见鉴权 header
    AUTH_HEADERS = [
        "authorization", "token", "x-token", "x-access-token",
        "x-auth-token", "x-api-key", "cookie", "x-sign", "sign",
        "x-signature", "nonce", "timestamp", "x-timestamp",
    ]
    
    def analyze(self, records: list, platform_name: str = "") -> AnalysisResult:
        """分析流量记录，输出结构化结果"""
        classified = self.classify_requests(records)
        endpoints = self.extract_endpoints(classified["api"])
        domains = list(set(urlparse(r.url).hostname for r in records if urlparse(r.url).hostname))
        
        return AnalysisResult(
            platform_name=platform_name,
            total_requests=len(records),
            api_endpoints=endpoints,
            page_requests=[r.url for r in classified["page"]],
            static_resources=len(classified["static"]),
            domains=domains,
        )
    
    def classify_requests(self, records: list) -> dict:
        """将请求分为 api / page / static 三类"""
        result = {"api": [], "page": [], "static": []}
        for r in records:
            if r.is_static:
                result["static"].append(r)
            elif r.is_api:
                result["api"].append(r)
            else:
                ct = r.content_type.lower()
                if "html" in ct:
                    result["page"].append(r)
                elif r.response_body and r.response_body.strip().startswith("{"):
                    result["api"].append(r)  # 没标 content-type 但返回 JSON
                else:
                    result["static"].append(r)
        return result
    
    def extract_endpoints(self, api_records: list) -> list[ApiEndpoint]:
        """从 API 请求中提取去重的端点信息"""
        # 按 (method, url_path) 分组
        groups: dict[tuple, list] = {}
        for r in api_records:
            parsed = urlparse(r.url)
            # 将路径中的数字 ID 替换为 {id}
            path = re.sub(r'/\d+', '/{id}', parsed.path)
            key = (r.method, f"{parsed.scheme}://{parsed.hostname}", path)
            groups.setdefault(key, []).append(r)
        
        endpoints = []
        for (method, base_url, path), records in groups.items():
            sample = records[0]
            auth_type, auth_hdrs = self.detect_auth_type(sample)
            schema = self.extract_response_schema(sample.response_body)
            
            # 提取请求参数
            parsed = urlparse(sample.url)
            params = {}
            for k, v in parse_qs(parsed.query).items():
                params[k] = v[0] if v else ""
            if sample.request_body:
                try:
                    body_params = json.loads(sample.request_body)
                    if isinstance(body_params, dict):
                        params.update(body_params)
                except (json.JSONDecodeError, ValueError):
                    pass
            
            endpoints.append(ApiEndpoint(
                url_pattern=path,
                base_url=base_url,
                method=method,
                auth_type=auth_type,
                auth_headers=auth_hdrs,
                request_params=params,
                response_sample=sample.response_body[:2000] if sample.response_body else "",
                response_schema=schema,
                sample_count=len(records),
                avg_duration_ms=sum(r.duration_ms for r in records) / len(records),
            ))
        
        return endpoints
    
    def detect_auth_type(self, record) -> tuple[str, list[str]]:
        """检测鉴权方式"""
        headers = {k.lower(): v for k, v in record.request_headers.items()}
        found_headers = []
        
        # Bearer Token
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return "bearer", ["Authorization"]
        
        # Cookie
        if "cookie" in headers and len(headers["cookie"]) > 20:
            found_headers.append("Cookie")
        
        # 自定义签名
        sign_headers = [h for h in self.AUTH_HEADERS if h in headers and h not in ("cookie", "authorization")]
        if sign_headers:
            found_headers.extend(sign_headers)
            if any(h in sign_headers for h in ["x-sign", "sign", "x-signature"]):
                return "custom_sign", found_headers
        
        if found_headers:
            return "cookie" if "Cookie" in found_headers else "unknown", found_headers
        
        return "none", []
    
    def extract_response_schema(self, body: str | None) -> dict:
        """提取 JSON 响应的结构摘要"""
        if not body:
            return {}
        try:
            data = json.loads(body)
            return self._schema_from_value(data, depth=0, max_depth=3)
        except (json.JSONDecodeError, ValueError):
            return {"_type": "non-json"}
    
    def _schema_from_value(self, value, depth: int, max_depth: int) -> dict:
        if depth >= max_depth:
            return {"_type": type(value).__name__}
        if isinstance(value, dict):
            return {k: self._schema_from_value(v, depth+1, max_depth) for k, v in list(value.items())[:20]}
        if isinstance(value, list):
            if value:
                return {"_type": "array", "_item": self._schema_from_value(value[0], depth+1, max_depth), "_count": len(value)}
            return {"_type": "array", "_count": 0}
        return {"_type": type(value).__name__}
```


### 3. InterfaceAnalyzer — 接口智能分析 🤖 AI 驱动

这是需要 GLM "理解"的部分。prompt 工程是关键。

```python
# u2-server/interface_analyzer.py

ANALYSIS_PROMPT = """你是一个资深的移动端逆向工程师和数据采集专家。

我从一个生猪竞拍平台的小程序/App 中抓包获取了以下 API 接口信息。
请分析每个接口，评估数据采集的实施难度。

## 接口列表

{endpoints_json}

## 请对每个接口输出以下分析（JSON 数组格式）：

```json
[
  {{
    "url_pattern": "接口路径",
    "purpose": "接口用途（如：获取竞拍列表、获取猪源详情、提交出价等）",
    "data_value": "high/medium/low（对我们系统的数据价值）",
    "difficulty_level": 1-4,
    "difficulty_reason": "难度原因",
    "recommended_strategy": "api/rpa_copy/rpa_ocr/hybrid",
    "implementation_notes": "实施注意事项",
    "key_fields": ["重要数据字段列表"]
  }}
]
```

## 难度等级说明：
- Level 1: 无鉴权或简单固定 Token，可直接 HTTP 调用
- Level 2: 需要登录态（Cookie/Token），但 Token 有效期长，手动获取一次可用很久
- Level 3: 需要动态签名/加密参数/时间戳校验
- Level 4: 有反爬机制/设备指纹/频率限制/证书固定

只输出 JSON 数组，不要其他文字。"""


class InterfaceAnalyzer:
    """接口智能分析器"""
    
    def __init__(self, vision_client):
        self.vision = vision_client  # 复用 GlmVisionClient（文本模式）
    
    async def analyze_endpoints(self, endpoints: list) -> list[dict]:
        """用 GLM 分析所有接口"""
        # 构造接口摘要（不发送完整响应体，节省 token）
        summaries = []
        for ep in endpoints:
            summaries.append({
                "url_pattern": ep.url_pattern,
                "base_url": ep.base_url,
                "method": ep.method,
                "auth_type": ep.auth_type,
                "auth_headers": ep.auth_headers,
                "request_params": ep.request_params,
                "response_schema": ep.response_schema,
                "sample_count": ep.sample_count,
            })
        
        prompt = ANALYSIS_PROMPT.format(
            endpoints_json=json.dumps(summaries, ensure_ascii=False, indent=2)
        )
        
        # 调用 GLM（文本模式，不需要图片）
        result = await self._call_glm_text(prompt)
        
        try:
            analyses = json.loads(result)
            return analyses if isinstance(analyses, list) else [analyses]
        except json.JSONDecodeError:
            return [{"error": "GLM 返回非 JSON", "raw": result[:500]}]
    
    async def generate_report(self, platform_name: str, analyses: list[dict], 
                               analysis_result) -> str:
        """生成 Markdown 格式的平台评估报告"""
        lines = [
            f"# {platform_name} — 平台接口分析报告",
            f"",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"",
            f"## 概览",
            f"",
            f"- 总请求数: {analysis_result.total_requests}",
            f"- API 接口数: {len(analysis_result.api_endpoints)}",
            f"- 涉及域名: {', '.join(analysis_result.domains)}",
            f"",
            f"## 接口分析",
            f"",
        ]
        
        for i, a in enumerate(analyses, 1):
            level = a.get("difficulty_level", "?")
            emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}.get(level, "⚪")
            lines.extend([
                f"### {i}. {a.get('url_pattern', '未知')}",
                f"",
                f"- 用途: {a.get('purpose', '未知')}",
                f"- 数据价值: {a.get('data_value', '未知')}",
                f"- 难度: {emoji} Level {level} — {a.get('difficulty_reason', '')}",
                f"- 推荐策略: `{a.get('recommended_strategy', '未知')}`",
                f"- 关键字段: {', '.join(a.get('key_fields', []))}",
                f"- 备注: {a.get('implementation_notes', '')}",
                f"",
            ])
        
        # 汇总
        levels = [a.get("difficulty_level", 0) for a in analyses]
        lines.extend([
            f"## 实施建议",
            f"",
            f"- Level 1 (可直接采集): {levels.count(1)} 个接口",
            f"- Level 2 (需登录态): {levels.count(2)} 个接口",
            f"- Level 3 (需逆向): {levels.count(3)} 个接口",
            f"- Level 4 (高难度): {levels.count(4)} 个接口",
            f"",
        ])
        
        if any(l <= 2 for l in levels):
            lines.append("✅ 存在可自动采集的接口，建议优先实施 Level 1-2 接口。")
        if any(l >= 3 for l in levels):
            lines.append("⚠️ 部分接口需要人工逆向分析，AI 已给出分析方向。")
        
        return "\n".join(lines)
    
    async def _call_glm_text(self, prompt: str) -> str:
        """调用 GLM 文本模式（不带图片）"""
        import httpx
        headers = {
            "Authorization": f"Bearer {self.vision.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "glm-4-plus",  # 文本分析用更强的模型
            "max_tokens": 2000,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers=headers, json=payload,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
```

### 4. ApiScriptGenerator — 脚本生成 ⚙️ 全自动代码

根据分析结果生成与 ScriptStore 兼容的采集脚本。

```python
# u2-server/script_generator.py

class ApiScriptGenerator:
    """根据接口分析结果生成采集脚本"""
    
    def __init__(self, script_store):
        self.store = script_store
    
    def generate(self, endpoint, analysis: dict) -> dict:
        """根据难度等级选择生成方式"""
        level = analysis.get("difficulty_level", 4)
        strategy = analysis.get("recommended_strategy", "rpa_ocr")
        
        if level == 1 and strategy == "api":
            return self.generate_api_script(endpoint, analysis)
        elif level <= 2:
            return self.generate_api_script_with_auth(endpoint, analysis)
        else:
            return self.generate_rpa_script(endpoint, analysis)
    
    def generate_api_script(self, endpoint, analysis: dict) -> dict:
        """生成 API 直连脚本（Level 1）"""
        return {
            "app": analysis.get("platform_name", "unknown"),
            "dataType": analysis.get("purpose", endpoint.url_pattern),
            "strategy": "api",
            "navigation": [],  # API 直连不需要导航
            "extraction": {
                "type": "api",
                "config": {
                    "method": endpoint.method,
                    "url": f"{endpoint.base_url}{endpoint.url_pattern}",
                    "headers": {h: "{{" + h + "}}" for h in endpoint.auth_headers},
                    "params": endpoint.request_params,
                    "dataPath": self._guess_data_path(endpoint.response_schema),
                },
            },
        }
    
    def generate_api_script_with_auth(self, endpoint, analysis: dict) -> dict:
        """生成需要鉴权的 API 脚本（Level 2）— 标注需要人工提供 Token"""
        script = self.generate_api_script(endpoint, analysis)
        script["extraction"]["config"]["_auth_note"] = (
            f"需要人工提供以下 header 的值: {', '.join(endpoint.auth_headers)}"
        )
        script["extraction"]["config"]["_auth_type"] = endpoint.auth_type
        return script
    
    def generate_rpa_script(self, endpoint, analysis: dict) -> dict:
        """生成 RPA 采集脚本（Level 3-4）"""
        return {
            "app": analysis.get("platform_name", "unknown"),
            "dataType": analysis.get("purpose", ""),
            "strategy": "rpa_ocr",
            "navigation": [],  # 需要 Navigator 探索填充
            "extraction": {
                "type": "ocr",
                "config": {
                    "maxPages": 3,
                    "swipeParams": {"x1": 540, "y1": 1600, "x2": 540, "y2": 400, "duration": 0.5},
                    "extractPrompt": f"提取屏幕上所有与'{analysis.get('purpose', '数据')}'相关的信息，JSON 数组格式返回",
                },
            },
        }
    
    def save_to_store(self, script: dict) -> str:
        """保存到 ScriptStore"""
        return self.store.save(
            app=script["app"],
            data_type=script["dataType"],
            strategy=script["strategy"],
            config=script,
        )
    
    def _guess_data_path(self, schema: dict) -> str:
        """猜测数据在响应 JSON 中的路径"""
        if not schema:
            return ""
        # 常见模式：data.list, data.items, data.records, result.data
        for key in ["data", "result", "body"]:
            if key in schema:
                sub = schema[key]
                if isinstance(sub, dict):
                    for sub_key in ["list", "items", "records", "rows"]:
                        if sub_key in sub:
                            return f"{key}.{sub_key}"
                    if sub.get("_type") == "array":
                        return key
        return ""
```

### 5. AnalysisOrchestrator — 编排器 ⚙️ 全自动代码

串联整个流程的控制器。

```python
# u2-server/analysis_orchestrator.py

class AnalysisOrchestrator:
    """平台分析编排器 — 一条指令完成全流程"""
    
    def __init__(self, device_manager, vision_agent, vision_client,
                 traffic_capture, traffic_analyzer, interface_analyzer,
                 script_generator, script_store):
        self.device_mgr = device_manager
        self.vision_agent = vision_agent
        self.vision_client = vision_client
        self.traffic = traffic_capture
        self.analyzer = traffic_analyzer
        self.interface = interface_analyzer
        self.generator = script_generator
        self.store = script_store
    
    async def analyze_platform(self, device_id: str, platform_name: str,
                                app_package: str = "",
                                domain_filter: list[str] = None,
                                har_file: str = None) -> dict:
        """
        完整的平台分析流程。
        
        两种模式：
        1. 实时模式：AI 操作 App + mitmproxy 实时抓包
        2. 离线模式：导入 HAR 文件分析（推荐先用这个）
        
        Returns:
            {
                "success": bool,
                "report": str,           # Markdown 报告
                "endpoints": [...],       # 接口列表
                "analyses": [...],        # 分析结果
                "scripts_generated": int, # 生成的脚本数
                "human_action_required": [...],  # 需要人工处理的事项
            }
        """
        progress = []
        human_actions = []
        
        # ── Phase 1: 获取流量数据 ──
        if har_file:
            # 离线模式：从 HAR 文件加载
            progress.append("📂 从 HAR 文件加载流量数据...")
            records = self.traffic.load_from_har(har_file)
            progress.append(f"  加载了 {len(records)} 条请求")
        else:
            # 实时模式：AI 探索 + 实时抓包
            progress.append("🔍 开始平台探索...")
            self.traffic.start_recording(platform_name, domain_filter or [])
            
            # 启动 App
            if app_package:
                self.device_mgr.app_start(device_id, app_package)
                import asyncio
                await asyncio.sleep(2)
            
            # VisionAgent 自动探索（最多 30 步）
            explore_result = await self.vision_agent.run_task(
                device_id,
                f"浏览{platform_name}的所有主要页面，包括首页、列表页、详情页、搜索页。"
                f"每个页面停留 3 秒让数据加载完成。尽量多浏览不同的页面。",
                max_steps=30,
            )
            progress.append(f"  探索完成，执行了 {explore_result.get('stepsCompleted', 0)} 步")
            
            records = self.traffic.stop_recording()
            self.traffic.save_to_file()
            progress.append(f"  捕获了 {len(records)} 条请求")
        
        if not records:
            return {
                "success": False,
                "report": "未捕获到任何流量数据",
                "endpoints": [],
                "analyses": [],
                "scripts_generated": 0,
                "human_action_required": ["请确认 mitmproxy 代理已配置，或提供 HAR 文件"],
                "progress": progress,
            }
        
        # ── Phase 2: 流量分析 ──
        progress.append("📊 分析流量数据...")
        analysis_result = self.analyzer.analyze(records, platform_name)
        progress.append(f"  识别出 {len(analysis_result.api_endpoints)} 个 API 接口")
        progress.append(f"  涉及域名: {', '.join(analysis_result.domains)}")
        
        if not analysis_result.api_endpoints:
            return {
                "success": False,
                "report": "未识别到 API 接口。可能原因：1) 流量被加密 2) 域名过滤太严格 3) 小程序使用了非标准协议",
                "endpoints": [],
                "analyses": [],
                "scripts_generated": 0,
                "human_action_required": ["检查 mitmproxy 是否正确解密 HTTPS", "尝试放宽域名过滤"],
                "progress": progress,
            }
        
        # ── Phase 3: AI 接口评估 ──
        progress.append("🤖 AI 分析接口...")
        analyses = await self.interface.analyze_endpoints(analysis_result.api_endpoints)
        progress.append(f"  分析完成，{len(analyses)} 个接口已评估")
        
        # ── Phase 4: 生成采集脚本 ──
        progress.append("⚙️ 生成采集脚本...")
        scripts_count = 0
        
        for i, (endpoint, analysis) in enumerate(zip(analysis_result.api_endpoints, analyses)):
            level = analysis.get("difficulty_level", 4)
            value = analysis.get("data_value", "low")
            
            if value == "low":
                continue  # 跳过低价值接口
            
            analysis["platform_name"] = platform_name
            
            if level <= 2:
                # 自动生成脚本
                script = self.generator.generate(endpoint, analysis)
                script_id = self.generator.save_to_store(script)
                scripts_count += 1
                progress.append(f"  ✅ 生成脚本: {analysis.get('purpose', endpoint.url_pattern)}")
                
                if level == 2:
                    human_actions.append(
                        f"接口 {endpoint.url_pattern} 需要提供鉴权信息: {', '.join(endpoint.auth_headers)}"
                    )
            else:
                human_actions.append(
                    f"接口 {endpoint.url_pattern} (Level {level}) 需要人工分析: {analysis.get('difficulty_reason', '')}"
                )
        
        # ── Phase 5: 生成报告 ──
        progress.append("📝 生成分析报告...")
        report = await self.interface.generate_report(platform_name, analyses, analysis_result)
        
        # 保存报告
        report_dir = Path("analysis_reports")
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"{platform_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(report, encoding="utf-8")
        progress.append(f"  报告已保存: {report_path}")
        
        return {
            "success": True,
            "report": report,
            "report_path": str(report_path),
            "endpoints": [asdict(ep) for ep in analysis_result.api_endpoints],
            "analyses": analyses,
            "scripts_generated": scripts_count,
            "human_action_required": human_actions,
            "progress": progress,
        }
```

## FastAPI 端点扩展

在 server.py 中新增以下端点：

```python
# 新增请求模型
class AnalyzePlatformRequest(BaseModel):
    device_id: str
    platform_name: str
    app_package: str = ""
    domain_filter: list[str] = []
    har_file: str | None = None

# 新增端点
POST /analyze/platform          # 完整平台分析
POST /traffic/start             # 开始流量录制
POST /traffic/stop              # 停止流量录制
GET  /traffic/records           # 获取流量记录
POST /traffic/load_har          # 加载 HAR 文件
GET  /analyze/reports           # 列出分析报告
```

## Bun 入口层新增指令

```typescript
// skill-cli.ts 新增
case "analyze_platform":
  return await callU2("/analyze/platform", {
    device_id: command.deviceId,
    platform_name: command.platformName,
    app_package: command.appPackage || "",
    domain_filter: command.domainFilter || [],
    har_file: command.harFile || null,
  });
```

## 测试策略

### 可直接单元测试的模块（不需要真实设备/网络）

| 模块 | 测试方法 | Mock 什么 |
|------|---------|----------|
| TrafficCapture | 构造 TrafficRecord，测试过滤/保存/加载 | 无需 mock |
| TrafficAnalyzer | 构造流量记录，测试分类/去重/鉴权检测/schema提取 | 无需 mock |
| ApiScriptGenerator | 构造 endpoint+analysis，测试脚本生成格式 | mock ScriptStore |
| DataMapper | 构造原始数据+映射规则，测试转换结果 | 无需 mock |

### 需要集成测试的模块

| 模块 | 测试方法 | 依赖 |
|------|---------|------|
| InterfaceAnalyzer | mock GLM 返回，测试 prompt 构造和结果解析 | mock httpx |
| AnalysisOrchestrator | mock 所有子模块，测试编排逻辑 | mock 全部 |
| PlatformExplorer | 需要真实设备 | 真实设备 + u2 |
