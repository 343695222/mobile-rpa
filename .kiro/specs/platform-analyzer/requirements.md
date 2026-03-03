# 需求文档：竞品平台自动分析与数据采集 (platform-analyzer)

## 简介

本功能为 OpenClaw 系统新增"竞品平台自动分析"能力，使 AI Agent 能够像人类逆向工程师一样，自动分析生猪竞拍平台（微信小程序/App），通过抓包分析接口、评估实施难度、自动实施数据抓取验证，并对接到目标系统。

## 核心流程

```
Phase 1: 平台探索（全自动）
  AI 打开目标小程序/App → 逐页截图 → GLM 分析页面结构和数据

Phase 2: 流量捕获（半自动，需 mitmproxy 环境）
  mitmproxy 后台录制 → AI 操作 App 触发请求 → 流量日志自动保存

Phase 3: 接口分析（全自动）
  AI 读取流量日志 → 识别数据接口 → 分析鉴权方式 → 评估难度

Phase 4: 采集实施（全自动/半自动）
  简单接口 → 自动生成采集脚本 → 自动验证
  复杂接口 → 生成评估报告 → 人工确认后实施

Phase 5: 数据对接（需配置）
  数据标准化 → 推送到目标系统 API
```

## 模块自动化程度分级

| 模块 | 自动化程度 | 说明 |
|------|-----------|------|
| TrafficCapture | ⚙️ 全自动代码 | mitmproxy addon，纯 Python，可直接测试 |
| TrafficAnalyzer | ⚙️ 全自动代码 | 解析 HAR/flow 文件，纯数据处理 |
| InterfaceAnalyzer | 🤖 AI 驱动 | GLM 分析接口，输出结构化评估 |
| DifficultyAssessor | 🤖 AI 驱动 | GLM 评估难度等级 |
| ApiScriptGenerator | ⚙️ 全自动代码 | 根据分析结果生成采集脚本 |
| ScriptVerifier | ⚙️ 全自动代码 | 执行脚本并验证数据 |
| DataMapper | ⚙️ 全自动代码+配置 | 数据字段映射，需人工配置映射规则 |
| PlatformExplorer | 🤖 AI 驱动 | 复用现有 VisionAgent 逐页探索 |
| AnalysisOrchestrator | ⚙️ 全自动代码 | 编排整个分析流程 |

## 需求

### 需求 1：流量捕获 (TrafficCapture)

**自动化程度：⚙️ 全自动代码，可直接输出稳定代码并测试**

**用户故事：** 作为用户，我希望系统能在 AI 操作手机时自动捕获 HTTP/HTTPS 流量，以便后续分析接口。

#### 验收标准

1. THE TrafficCapture SHALL 以 mitmproxy addon 形式运行，自动记录经过代理的所有 HTTP/HTTPS 请求和响应
2. WHEN 捕获到请求时，THE TrafficCapture SHALL 记录完整的请求信息：URL、method、headers、body、响应 status、响应 body、时间戳
3. THE TrafficCapture SHALL 将捕获的流量保存为 JSON 格式文件（每个平台一个目录）
4. THE TrafficCapture SHALL 支持按域名/路径过滤，只记录目标平台的流量
5. THE TrafficCapture SHALL 提供 REST API 接口（集成到 FastAPI），支持：开始录制、停止录制、获取录制结果、清空录制
6. IF mitmproxy 未安装或代理未配置，THEN THE TrafficCapture SHALL 返回明确的环境检查错误

#### 技术方案（可直接编码）

```python
# u2-server/traffic_capture.py
# 纯 Python，依赖 mitmproxy 库
# 数据结构清晰，可完整单元测试

class TrafficRecord:
    """单条流量记录"""
    url: str
    method: str
    request_headers: dict
    request_body: str | None
    response_status: int
    response_headers: dict
    response_body: str | None
    timestamp: str
    duration_ms: float

class TrafficCapture:
    """流量捕获管理器"""
    def start_recording(self, platform_name: str, domain_filter: list[str]) -> None
    def stop_recording(self) -> list[TrafficRecord]
    def get_records(self) -> list[TrafficRecord]
    def save_to_file(self, platform_name: str) -> str  # 返回文件路径
    def clear(self) -> None
```

### 需求 2：流量分析 (TrafficAnalyzer)

**自动化程度：⚙️ 全自动代码，可直接输出稳定代码并测试**

**用户故事：** 作为用户，我希望系统能自动分析捕获的流量，识别出数据接口和静态资源。

#### 验收标准

1. THE TrafficAnalyzer SHALL 从流量记录中自动分类：数据接口（返回 JSON）、页面请求（返回 HTML）、静态资源（图片/CSS/JS）
2. THE TrafficAnalyzer SHALL 对数据接口进行去重和聚合（相同路径不同参数的请求合并）
3. THE TrafficAnalyzer SHALL 提取每个数据接口的：URL 模式、请求参数、响应数据结构、鉴权 header
4. THE TrafficAnalyzer SHALL 自动识别常见鉴权方式：Bearer Token、Cookie Session、自定义签名、无鉴权
5. THE TrafficAnalyzer SHALL 输出结构化的接口清单（JSON 格式）

#### 技术方案（可直接编码）

```python
# u2-server/traffic_analyzer.py
# 纯数据处理，无外部依赖，100% 可测试

class ApiEndpoint:
    """识别出的 API 端点"""
    url_pattern: str          # 如 /api/v1/auctions/{id}
    method: str
    auth_type: str            # none / bearer / cookie / custom_sign
    auth_headers: list[str]   # 涉及鉴权的 header 名
    request_params: dict      # 参数名 → 示例值
    response_schema: dict     # 响应 JSON 结构摘要
    sample_count: int         # 捕获到的样本数

class TrafficAnalyzer:
    """流量分析器"""
    def analyze(self, records: list[TrafficRecord]) -> AnalysisResult
    def classify_requests(self, records) -> dict  # api / page / static
    def extract_endpoints(self, api_records) -> list[ApiEndpoint]
    def detect_auth_type(self, endpoint) -> str
    def extract_response_schema(self, response_body: str) -> dict
```

### 需求 3：接口智能评估 (InterfaceAnalyzer + DifficultyAssessor)

**自动化程度：🤖 AI 驱动，依赖 GLM 分析，输出需人工确认**

**用户故事：** 作为用户，我希望 AI 能像人类分析师一样评估每个接口的采集难度和实施方案。

#### 验收标准

1. THE InterfaceAnalyzer SHALL 将 TrafficAnalyzer 的结果发送给 GLM，请求分析每个接口的用途和数据价值
2. THE DifficultyAssessor SHALL 对每个接口评估难度等级：
   - Level 1 (简单)：无鉴权或简单 Token，可直接调用
   - Level 2 (中等)：需要登录态/Cookie，但 Token 有效期长
   - Level 3 (困难)：需要动态签名/加密参数
   - Level 4 (极难)：有反爬机制/频率限制/设备指纹
3. THE DifficultyAssessor SHALL 为每个接口生成实施建议：推荐采集策略（API直连/RPA/混合）
4. THE InterfaceAnalyzer SHALL 输出完整的平台评估报告（Markdown 格式），包含所有接口的分析结果

#### 技术方案

```python
# u2-server/interface_analyzer.py
# 调用 GLM 分析，prompt 工程是关键

class InterfaceAnalysis:
    """单个接口的分析结果"""
    endpoint: ApiEndpoint
    purpose: str              # AI 判断的接口用途
    data_value: str           # 数据价值评估
    difficulty_level: int     # 1-4
    difficulty_reason: str    # 难度原因
    recommended_strategy: str # api / rpa_copy / rpa_ocr / hybrid
    implementation_notes: str # 实施注意事项

class InterfaceAnalyzer:
    """接口智能分析器（GLM 驱动）"""
    async def analyze_endpoints(self, endpoints: list[ApiEndpoint]) -> list[InterfaceAnalysis]
    async def generate_report(self, platform_name: str, analyses: list[InterfaceAnalysis]) -> str
```

### 需求 4：采集脚本自动生成 (ApiScriptGenerator)

**自动化程度：⚙️ 全自动代码，可直接输出稳定代码并测试**

**用户故事：** 作为用户，我希望系统能根据分析结果自动生成可执行的采集脚本。

#### 验收标准

1. WHEN 接口难度为 Level 1 时，THE ApiScriptGenerator SHALL 自动生成 API 直连采集脚本并写入 ScriptStore
2. WHEN 接口难度为 Level 2 时，THE ApiScriptGenerator SHALL 生成需要登录态的采集脚本，并标注需要人工提供 Token/Cookie
3. WHEN 接口难度为 Level 3-4 时，THE ApiScriptGenerator SHALL 生成 RPA 采集脚本（复用现有 rpa_copy / rpa_ocr 策略）
4. THE ApiScriptGenerator SHALL 生成的脚本格式与现有 ScriptStore 完全兼容

#### 技术方案（可直接编码）

```python
# u2-server/script_generator.py
# 根据 InterfaceAnalysis 生成 ScriptStore 兼容的脚本

class ApiScriptGenerator:
    """采集脚本生成器"""
    def generate(self, analysis: InterfaceAnalysis) -> dict  # ScriptStore 格式
    def generate_api_script(self, endpoint: ApiEndpoint) -> dict
    def generate_rpa_script(self, analysis: InterfaceAnalysis) -> dict
    def save_to_store(self, script: dict) -> str  # 返回 script_id
```

### 需求 5：脚本验证 (ScriptVerifier)

**自动化程度：⚙️ 全自动代码，可直接输出稳定代码并测试**

**用户故事：** 作为用户，我希望生成的采集脚本能自动执行验证，确认数据可以正常采集。

#### 验收标准

1. THE ScriptVerifier SHALL 执行生成的采集脚本，检查是否能成功获取数据
2. THE ScriptVerifier SHALL 验证返回数据的格式和字段完整性
3. WHEN 验证失败时，THE ScriptVerifier SHALL 记录失败原因并标记脚本为待修复
4. THE ScriptVerifier SHALL 输出验证报告（成功/失败/数据样本）

### 需求 6：数据标准化与对接 (DataMapper)

**自动化程度：⚙️ 代码框架全自动 + 映射规则需人工配置**

**用户故事：** 作为用户，我希望从不同平台采集的数据能统一格式后推送到我的系统。

#### 验收标准

1. THE DataMapper SHALL 支持配置式字段映射（源字段 → 目标字段）
2. THE DataMapper SHALL 支持数据类型转换（字符串→数字、日期格式化等）
3. THE DataMapper SHALL 支持通过 HTTP API 将标准化数据推送到目标系统
4. THE DataMapper SHALL 为每个平台维护独立的映射配置文件

### 需求 7：平台探索 (PlatformExplorer)

**自动化程度：🤖 AI 驱动，复用现有 VisionAgent**

**用户故事：** 作为用户，我希望 AI 能自动打开目标平台，逐页浏览并分析页面结构。

#### 验收标准

1. THE PlatformExplorer SHALL 复用现有 VisionAgent 的截图→分析→操作循环
2. THE PlatformExplorer SHALL 在探索过程中记录每个页面的：截图、页面描述、可交互元素、数据字段
3. THE PlatformExplorer SHALL 生成平台页面地图（哪些页面有什么数据）
4. THE PlatformExplorer SHALL 在探索同时触发 TrafficCapture 录制流量

### 需求 8：分析编排器 (AnalysisOrchestrator)

**自动化程度：⚙️ 全自动代码**

**用户故事：** 作为用户，我希望一条指令就能启动完整的平台分析流程。

#### 验收标准

1. THE AnalysisOrchestrator SHALL 编排完整流程：探索 → 抓包 → 分析 → 评估 → 生成脚本 → 验证
2. THE AnalysisOrchestrator SHALL 在每个阶段输出进度和中间结果
3. WHEN 某个阶段需要人工介入时（如 Level 3-4 接口），THE AnalysisOrchestrator SHALL 暂停并输出待办事项
4. THE AnalysisOrchestrator SHALL 通过 Bun 入口层暴露为 `analyze_platform` 指令

## 人机协同边界（关键）

### 完全自动（AI + 代码，无需人工）

| 步骤 | 模块 | 输入 | 输出 |
|------|------|------|------|
| 打开 App/小程序 | VisionAgent (已有) | 平台名称 | 操作完成 |
| 逐页截图分析 | PlatformExplorer | 平台名称 | 页面地图 |
| 流量录制 | TrafficCapture | 域名过滤 | 流量日志 |
| 流量分类 | TrafficAnalyzer | 流量日志 | 接口清单 |
| 接口评估 | InterfaceAnalyzer | 接口清单 | 评估报告 |
| Level 1 脚本生成 | ApiScriptGenerator | 评估结果 | 采集脚本 |
| 脚本验证 | ScriptVerifier | 采集脚本 | 验证报告 |

### 需要人工介入

| 步骤 | 原因 | 人工操作 | AI 辅助 |
|------|------|---------|---------|
| mitmproxy 证书安装 | 首次配置，需要手机信任证书 | 安装 CA 证书到手机 | 提供安装指南 |
| 微信小程序抓包 | 微信有证书固定，需特殊处理 | 配置 Xposed/JustTrustMe | 提供配置指南 |
| Level 2 接口 Token | 需要登录态 | 提供有效 Token/Cookie | AI 告诉你需要哪个 header |
| Level 3-4 接口 | 签名/加密太复杂 | 人工逆向或放弃 | AI 给出分析报告和建议 |
| 数据字段映射 | 业务语义需要人工确认 | 配置映射规则 | AI 建议映射关系 |
| 目标系统 API | 需要知道推送地址和格式 | 提供 API 文档 | AI 生成对接代码 |

## 前置环境要求

1. mitmproxy 已安装（`pip install mitmproxy` 或 `uv add mitmproxy`）
2. 手机已配置 HTTP 代理指向云服务器
3. 手机已安装 mitmproxy CA 证书（HTTPS 抓包必需）
4. 微信小程序抓包需要：root 手机 + Xposed + JustTrustMe（绕过证书固定）
5. 现有 u2-server 正常运行


## 需求 9：敏感操作安全守卫 (SafetyGuard)

**自动化程度：⚙️ 全自动代码，已实现并通过 32 项测试**

**用户故事：** 作为用户，我希望 AI 在自动操作手机时不会误触发竞拍出价、支付、转账等敏感操作，避免造成经济损失。

### 安全等级

| 等级 | 行为 | 示例 |
|------|------|------|
| SAFE | 直接执行 | 浏览、截图、返回、滑动 |
| CAUTION | 记录日志但允许 | 登录、分享 |
| DANGER | 需要人工确认才能执行 | 出价、提交订单、输入金额 |
| BLOCKED | 直接拒绝，任何模式都不允许 | 支付、转账、注销账号、输入密码 |

### 三种运行模式

| 模式 | SAFE | CAUTION | DANGER | BLOCKED |
|------|------|---------|--------|---------|
| strict（默认） | ✅ 放行 | ✅ 放行+日志 | ❌ 需确认 | ❌ 拒绝 |
| permissive | ✅ 放行 | ✅ 放行+日志 | ✅ 放行+日志 | ❌ 拒绝 |
| observe_only | ✅ 放行 | ✅ 放行+日志 | ✅ 放行+日志 | ✅ 放行+日志 |

### 验收标准

1. THE SafetyGuard SHALL 在每次操作执行前检查操作的安全等级
2. WHEN 操作匹配 BLOCKED 规则时，THE SafetyGuard SHALL 直接拒绝执行，无论任何模式
3. WHEN 操作匹配 DANGER 规则且模式为 strict 时，THE SafetyGuard SHALL 暂停执行并请求人工确认
4. WHEN 人工确认批准后，THE SafetyGuard SHALL 允许该操作执行
5. THE SafetyGuard SHALL 记录所有安全事件到日志中
6. THE SafetyGuard SHALL 支持通过 REST API 查看待确认操作、批准/拒绝操作、切换模式
7. THE SafetyGuard SHALL 支持通过 JSON 配置文件自定义安全规则
8. THE SafetyGuard SHALL 已集成到 VisionAgent 和 Navigator 的操作执行链路中

### 针对竞拍场景的具体规则

- 浏览竞拍列表、查看详情 → SAFE（允许）
- 点击"出价"、"竞拍"、"报价"按钮 → DANGER（需确认）
- 输入纯数字（可能是金额） → DANGER（需确认）
- 点击"确认出价"、"确认订单" → DANGER（需确认）
- 点击"支付"、"付款"、"转账" → BLOCKED（直接拒绝）
- 输入密码 → BLOCKED（直接拒绝）

### REST API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /safety/rules | 列出所有安全规则 |
| GET | /safety/log | 查看安全事件日志 |
| GET | /safety/pending | 查看待确认操作 |
| POST | /safety/confirm | 批准或拒绝待确认操作 |
| GET | /safety/mode | 查看当前安全模式 |
| POST | /safety/mode | 切换安全模式 |
