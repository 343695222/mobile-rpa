# OpenClaw 技术实施指南

## 开发实施手册

---

## 一、技术架构详解

### 1.1 系统分层

```
┌─────────────────────────────────────────────────────────────────┐
│                        API 接入层                                │
│                    (REST API / WebSocket)                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────────┐
│                        业务编排层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ 任务调度器  │  │ 状态管理器  │  │      结果组装器          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────────┐
│                        核心引擎层                                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    自动探索引擎                           │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ DeviceManager (uiautomator2)                      │  │   │
│  │  │  - 设备连接管理                                     │  │   │
│  │  │  - 高速截图 (500ms)                                 │  │   │
│  │  │  - 元素查找/点击/输入/滑动                           │  │   │
│  │  │  - 剪贴板操作                                       │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ VisionAgent (GLM-4.6V)                            │  │   │
│  │  │  - 屏幕截图分析                                     │  │   │
│  │  │  - 操作决策推理                                     │  │   │
│  │  │  - 任务循环执行                                     │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ SafetyGuard                                       │  │   │
│  │  │  - 危险操作拦截 (出价/支付)                         │  │   │
│  │  │  - 安全规则引擎                                     │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    流量捕获引擎                           │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ ProxyManager                                      │  │   │
│  │  │  - mitmproxy 进程管理                              │  │   │
│  │  │  - 手机代理配置                                    │  │   │
│  │  │  - 证书安装管理                                    │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ TrafficCapture                                    │  │   │
│  │  │  - 流量记录                                        │  │   │
│  │  │  - HAR 文件导入                                    │  │   │
│  │  │  - 域名过滤                                        │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    分析生成引擎                           │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ TrafficAnalyzer                                   │  │   │
│  │  │  - 请求分类 (API/页面/静态)                         │  │   │
│  │  │  - 端点提取与去重                                   │  │   │
│  │  │  - 鉴权方式检测                                     │  │   │
│  │  │  - 响应结构分析                                     │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ ComplexityEvaluator                               │  │   │
│  │  │  - 鉴权复杂度评估                                   │  │   │
│  │  │  - 数据格式复杂度评估                               │  │   │
│  │  │  - 生成方式决策                                     │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ CodeGenerator                                     │  │   │
│  │  │  - 完整代码生成                                     │  │   │
│  │  │  - 框架代码生成 (+TODO)                             │  │   │
│  │  │  - 知识包生成                                       │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────────┐
│                        数据存储层                                │
│  - 配置存储 (JSON)                                               │
│  - 脚本仓库 (JSON)                                               │
│  - 元数据存储 (SQLite)                                           │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 目录结构

```
openclaw/
├── api/                          # API 接入层
│   ├── server.py                 # FastAPI 主服务
│   ├── router/
│   │   ├── tasks.py              # 任务相关接口
│   │   ├── devices.py            # 设备管理接口
│   │   └── codegen.py            # 代码生成接口
│   └── models/
│       ├── task.py               # 任务数据模型
│       └── config.py             # 配置数据模型
│
├── core/                         # 核心引擎层
│   ├── exploration/              # 自动探索引擎
│   │   ├── device_manager.py     # uiautomator2 设备管理
│   │   ├── vision_agent.py       # GLM 视觉分析
│   │   ├── navigator.py          # 导航管理器
│   │   └── safety_guard.py       # 安全守卫
│   │
│   ├── capture/                  # 流量捕获引擎
│   │   ├── proxy_manager.py      # mitmproxy 管理
│   │   ├── traffic_capture.py    # 流量记录
│   │   └── mitm_addon.py         # mitmproxy 插件
│   │
│   └── generation/               # 分析生成引擎
│       ├── traffic_analyzer.py   # 流量分析
│       ├── complexity_eval.py    # 复杂度评估
│       ├── code_generator.py     # 代码生成
│       └── knowledge_builder.py  # 知识包构建
│
├── storage/                      # 数据存储层
│   ├── config_store.py           # 配置存储
│   ├── script_store.py           # 脚本仓库
│   └── metadata_db.py            # 元数据库
│
├── templates/                    # 代码模板
│   ├── python/
│   │   ├── simple_api.py.j2      # 简单 API 模板
│   │   ├── complex_framework.py.j2  # 复杂框架模板
│   │   └── README.md.j2          # 说明文档模板
│   └── typescript/
│
├── u2-server/                    # Python 设备服务 (已有)
│   ├── server.py
│   ├── device.py
│   ├── vision.py
│   └── ...
│
├── src/                          # Bun/TS 入口层 (已有)
│   └── skill-cli.ts
│
├── tests/                        # 测试
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── docs/                         # 文档
```

---

## 二、核心模块设计

### 2.1 任务调度器 (TaskScheduler)

```python
class TaskScheduler:
    """任务调度器 - 管理代码生成任务的生命周期"""

    async def create_task(self, request: CodeGenRequest) -> str:
        """创建新任务，返回 task_id"""
        task_id = generate_uuid()
        task = Task(
            id=task_id,
            platform=request.platform,
            data_type=request.data_type,
            status=TaskStatus.PENDING,
            created_at=now()
        )
        await self.storage.save_task(task)
        # 异步执行任务
        asyncio.create_task(self._execute_task(task_id))
        return task_id

    async def _execute_task(self, task_id: str):
        """执行任务的主要流程"""
        task = await self.storage.get_task(task_id)

        try:
            # 1. 检查是否已有可用配置
            if existing := await self._find_existing_config(task):
                return await self._deliver_existing(task, existing)

            # 2. 自动探索流程
            await self.update_status(task_id, TaskStatus.EXPLORING)
            exploration_result = await self.exploration_engine.explore(
                device_id=task.device_id,
                platform=task.platform,
                data_type=task.data_type
            )

            # 3. 分析流量
            await self.update_status(task_id, TaskStatus.ANALYZING)
            analysis = await self.analyzer.analyze(
                exploration_result.traffic_records
            )

            # 4. 评估复杂度
            can_auto, reason = self.complexity_eval.can_generate_auto(analysis)

            # 5. 生成代码
            await self.update_status(task_id, TaskStatus.GENERATING)
            if can_auto:
                result = await self.code_generator.generate_full(analysis)
            else:
                result = await self.code_generator.generate_framework(analysis)

            # 6. 测试代码
            await self.update_status(task_id, TaskStatus.TESTING)
            test_result = await self._test_generated_code(result)

            # 7. 交付
            await self.update_status(task_id, TaskStatus.COMPLETED)
            await self._deliver_result(task, result, test_result)

        except Exception as e:
            await self.update_status(task_id, TaskStatus.FAILED, str(e))

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """获取任务状态"""
        return await self.storage.get_task(task_id)
```

### 2.2 复杂度评估器 (ComplexityEvaluator)

```python
class ComplexityEvaluator:
    """评估代码生成复杂度，决策生成方式"""

    # 复杂度评分阈值
    AUTO_THRESHOLD = 30        # ≤30 分可全自动生成
    FRAMEWORK_THRESHOLD = 70   # ≤70 分生成框架，>70 需深度介入

    async def evaluate(self, analysis: AnalysisResult) -> ComplexityReport:
        """综合评估复杂度"""
        score = 0
        blockers = []
        warnings = []

        # 1. 鉴权复杂度 (0-40 分)
        auth_score, auth_issues = self._eval_auth(analysis.api_endpoints)
        score += auth_score
        blockers.extend(auth_issues)

        # 2. 数据格式复杂度 (0-20 分)
        format_score, format_issues = self._eval_format(analysis.api_endpoints)
        score += format_score
        warnings.extend(format_issues)

        # 3. 响应结构复杂度 (0-20 分)
        structure_score, structure_issues = self._eval_structure(analysis.api_endpoints)
        score += structure_score
        warnings.extend(structure_issues)

        # 4. 分页与状态管理 (0-20 分)
        pagination_score, pagination_issues = self._eval_pagination(analysis.api_endpoints)
        score += pagination_score
        warnings.extend(pagination_issues)

        # 决策
        if score <= self.AUTO_THRESHOLD:
            mode = GenerationMode.AUTO
        elif score <= self.FRAMEWORK_THRESHOLD:
            mode = GenerationMode.SEMI_AUTO
        else:
            mode = GenerationMode.MANUAL

        return ComplexityReport(
            total_score=score,
            mode=mode,
            blockers=blockers,
            warnings=warnings,
            breakdown={
                "auth": auth_score,
                "format": format_score,
                "structure": structure_score,
                "pagination": pagination_score
            }
        )

    def _eval_auth(self, endpoints: list[ApiEndpoint]) -> tuple[int, list[str]]:
        """评估鉴权复杂度"""
        max_score = 0
        issues = []

        for api in endpoints:
            score = 0
            if api.auth_type == "none":
                score = 0
            elif api.auth_type == "cookie":
                score = 10
            elif api.auth_type == "bearer":
                score = 20
                issues.append(f"{api.url_pattern}: Bearer Token 需要刷新机制")
            elif api.auth_type == "custom_sign":
                score = 40
                if any("sign" in h.lower() for h in api.auth_headers):
                    issues.append(f"{api.url_pattern}: 自定义签名算法，需逆向分析")

            max_score = max(max_score, score)

        return max_score, issues
```

### 2.3 代码生成器 (CodeGenerator)

```python
class CodeGenerator:
    """根据分析结果生成采集代码"""

    def __init__(self, template_dir: str):
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False
        )

    async def generate_full(self, analysis: AnalysisResult,
                           platform: str, data_type: str) -> GenerationResult:
        """生成完整可运行的代码"""

        # 提取主要 API
        primary_api = self._find_primary_api(analysis.api_endpoints)

        # 准备模板变量
        template_vars = {
            "class_name": self._to_class_name(platform, data_type),
            "base_url": primary_api.base_url,
            "endpoint": primary_api.url_pattern,
            "method": primary_api.method,
            "auth": self._build_auth_code(primary_api),
            "request_params": primary_api.request_params,
            "response_parser": self._build_parser_code(primary_api.response_schema),
            "pagination": self._build_pagination_code(analysis.api_endpoints),
            "imports": self._build_imports(primary_api),
        }

        # 渲染模板
        template = self.jinja_env.get_template("python/simple_api.py.j2")
        code = template.render(**template_vars)

        return GenerationResult(
            code=code,
            mode=GenerationMode.AUTO,
            todo_items=[],
            metadata=template_vars
        )

    async def generate_framework(self, analysis: AnalysisResult,
                                 platform: str, data_type: str) -> GenerationResult:
        """生成代码框架 + TODO 标记"""

        primary_api = self._find_primary_api(analysis.api_endpoints)

        template_vars = {
            "class_name": self._to_class_name(platform, data_type),
            "base_url": primary_api.base_url,
            "endpoint": primary_api.url_pattern,
            "method": primary_api.method,
            "auth_stub": self._build_auth_stub(primary_api),  # 带TODO的鉴权代码
            "request_example": primary_api.request_params,
            "response_structure": primary_api.response_schema,
            "todos": self._extract_todos(primary_api),
        }

        template = self.jinja_env.get_template("python/complex_framework.py.j2")
        code = template.render(**template_vars)

        # 生成知识包
        knowledge_pack = await self._build_knowledge_pack(
            analysis, platform, data_type
        )

        return GenerationResult(
            code=code,
            mode=GenerationMode.SEMI_AUTO,
            todo_items=template_vars["todos"],
            knowledge_pack=knowledge_pack,
            metadata=template_vars
        )
```

### 2.4 知识包构建器 (KnowledgeBuilder)

```python
class KnowledgeBuilder:
    """构建人类介入所需的背景知识包"""

    async def build(self, analysis: AnalysisResult,
                   complexity: ComplexityReport,
                   platform: str, data_type: str) -> KnowledgePack:

        primary_api = self._find_primary_api(analysis.api_endpoints)

        return KnowledgePack(
            # 基本信息
            meta={
                "platform": platform,
                "data_type": data_type,
                "generated_at": now().isoformat(),
            },

            # 技术信息
            technical_info=TechnicalInfo(
                endpoint=EndpointInfo(
                    method=primary_api.method,
                    url=primary_api.url_pattern,
                    base_url=primary_api.base_url,
                ),
                authentication=AuthInfo(
                    type=primary_api.auth_type,
                    headers=primary_api.auth_headers,
                    description=self._describe_auth(primary_api),
                ),
                request_sample=RequestSample(
                    headers=self._sample_headers(primary_api),
                    body=primary_api.request_params,
                ),
                response_sample=ResponseSample(
                    raw=primary_api.response_sample[:1000],
                    schema=primary_api.response_schema,
                    description=self._describe_response(primary_api),
                ),
            ),

            # 业务信息
            business_info=BusinessInfo(
                description=self._infer_business_purpose(platform, data_type),
                data_meaning=self._explain_data_fields(primary_api),
                pagination=self._explain_pagination(analysis.api_endpoints),
            ),

            # 阻碍问题
            blocking_issues=complexity.blockers,

            # 建议操作
            suggested_actions=self._generate_suggestions(
                complexity, primary_api
            ),

            # 代码示例
            code_examples=CodeExamples(
                authentication=self._auth_code_examples(primary_api),
                request_building=self._request_examples(primary_api),
                response_parsing=self._parsing_examples(primary_api),
            ),
        )
```

---

## 三、API 接口设计

### 3.1 核心接口

```python
# 创建代码生成任务
POST /api/v1/codegen/tasks
Request:
{
  "platform": "聚宝猪",
  "data_type": "拍卖列表",
  "target_app": "com.jubaozhu.app",
  "device_id": "emulator-5554",
  "domain_filter": ["jubaozhu.com"],
  "output_format": "python"
}
Response:
{
  "task_id": "task_20250304_abc123",
  "status": "pending",
  "estimated_time_minutes": 10
}

# 查询任务状态
GET /api/v1/codegen/tasks/{task_id}
Response:
{
  "task_id": "task_20250304_abc123",
  "status": "completed",  # pending/exploring/analyzing/generating/testing/completed/failed
  "progress": {
    "current_step": "testing",
    "completed_steps": ["exploration", "analysis", "generation"],
    "total_steps": 5
  },
  "result": {
    "mode": "auto",  # auto/semi_auto/manual
    "deliverables": {
      "code_file": "jubaozhu_auction_collector.py",
      "readme": "README.md",
      "test_sample": "test_output.json"
    },
    "test_result": {
      "success": true,
      "execution_time_ms": 250,
      "sample_count": 20
    }
  }
}

# 下载生成的代码
GET /api/v1/codegen/tasks/{task_id}/download
Response: ZIP file containing all deliverables

# 获取知识包（半自动模式）
GET /api/v1/codegen/tasks/{task_id}/knowledge
Response: KnowledgePack JSON
```

### 3.2 WebSocket 实时推送

```python
# 客户端连接
WS /api/v1/codegen/tasks/{task_id}/stream

# 服务端推送进度
{
  "type": "progress",
  "step": "exploration",
  "message": "正在启动 App 并浏览目标页面...",
  "percent": 20
}

{
  "type": "progress",
  "step": "capture",
  "message": "已捕获 15 个 API 请求",
  "percent": 40
}

{
  "type": "decision",
  "message": "检测到自定义签名，将生成代码框架",
  "mode": "semi_auto"
}

{
  "type": "complete",
  "result": {...}
}
```

---

## 四、数据模型

### 4.1 核心数据结构

```python
@dataclass
class CodeGenRequest:
    platform: str              # 目标平台名称
    data_type: str             # 数据类型描述
    target_app: str | None     # App 包名
    device_id: str | None      # 指定设备
    domain_filter: list[str]   # 域名过滤
    output_format: str         # python/typescript

@dataclass
class Task:
    id: str
    platform: str
    data_type: str
    status: TaskStatus
    mode: GenerationMode | None
    result: GenerationResult | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None

@dataclass
class GenerationResult:
    code: str                  # 生成的代码
    mode: GenerationMode       # auto/semi_auto/manual
    todo_items: list[TODOItem] # 需要人工完成的部分
    knowledge_pack: KnowledgePack | None
    metadata: dict             # 代码元数据
    test_result: TestResult | None

@dataclass
class KnowledgePack:
    meta: dict
    technical_info: TechnicalInfo
    business_info: BusinessInfo
    blocking_issues: list[str]
    suggested_actions: list[str]
    code_examples: CodeExamples
```

---

## 五、测试策略

### 5.1 测试金字塔

```
        ┌─────────┐
       /   E2E    \          少量端到端测试
      /─────────────\        - 完整流程验证
     /               \
    /    集成测试     \      中等数量
   /─────────────────────\    - 模块间协作
  /                       \
 /      单元测试            \    大量
/─────────────────────────────\  - 函数/类级别
```

### 5.2 测试覆盖

| 模块 | 单元测试 | 集成测试 | E2E 测试 |
|------|---------|---------|---------|
| DeviceManager | ✅ | ✅ | ✅ |
| VisionAgent | ✅ | ✅ | 🚧 |
| TrafficCapture | ✅ | ✅ | ✅ |
| TrafficAnalyzer | ✅ | ✅ | - |
| ComplexityEvaluator | ✅ | ✅ | - |
| CodeGenerator | ✅ | ✅ | 🚧 |
| KnowledgeBuilder | ✅ | 🚧 | - |
| TaskScheduler | - | 🚧 | 🚧 |

---

## 六、部署架构

### 6.1 单机部署

```
┌─────────────────────────────────────────────────────────────┐
│                        云服务器                              │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   Docker Compose                      │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │ FastAPI     │  │  U2 Server  │  │   Redis     │  │  │
│  │  │   :8000     │  │   :9400     │  │   :6379     │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │ mitmproxy   │  │   Worker    │  │   Nginx     │  │  │
│  │  │   :8080     │  │  (async)    │  │   :443      │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   ADB 连接                            │  │
│  │                   ────────                           │  │
│  │                        │                              │  │
│  │                        ▼                              │  │
│  │              Android 设备池                           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 环境变量配置

```bash
# 服务配置
OPENCLAW_HOST=0.0.0.0
OPENCLAW_PORT=8000
OPENCLAW_ENV=production

# 数据库
REDIS_URL=redis://localhost:6379/0
SQLITE_PATH=/data/openclaw.db

# GLM API
DASHSCOPE_API_KEY=sk-***

# 设备服务
U2_SERVER_URL=http://localhost:9400

# 存储
STORAGE_PATH=/data/openclaw
TEMPLATE_PATH=/app/templates

# mitmproxy
MITMPROXY_HOST=0.0.0.0
MITMPROXY_PORT=8080
```

---

*文档版本：v1.0*
*更新日期：2026-03-04*
