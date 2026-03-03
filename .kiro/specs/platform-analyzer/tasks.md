# 实施计划：竞品平台自动分析 (platform-analyzer)

## 概述

分 4 个阶段实施，每个阶段独立可用。前两个阶段全是确定性代码，可以直接写出来跑测试。

## Phase 1: 流量捕获与分析（⚙️ 全自动代码，可直接输出）

这一阶段零 AI 依赖，纯数据处理，可以 100% 单元测试覆盖。

### Task 1.1: TrafficCapture 流量捕获模块
- 创建 `u2-server/traffic_capture.py`
- 实现 TrafficRecord 数据类
- 实现 start_recording / stop_recording / add_record
- 实现 load_from_har（HAR 文件解析）
- 实现 save_to_file（JSON 持久化）
- 实现域名过滤逻辑
- **可直接测试：** 构造 mock 数据，验证过滤/保存/加载

### Task 1.2: TrafficAnalyzer 流量分析模块
- 创建 `u2-server/traffic_analyzer.py`
- 实现请求分类（api / page / static）
- 实现 API 端点提取与去重（URL 路径归一化）
- 实现鉴权方式检测（bearer / cookie / custom_sign / none）
- 实现响应 JSON schema 提取
- **可直接测试：** 构造各种流量样本，验证分类和提取结果

### Task 1.3: 单元测试
- 创建 `u2-server/tests/test_traffic_capture.py`
- 创建 `u2-server/tests/test_traffic_analyzer.py`
- 覆盖：HAR 解析、域名过滤、请求分类、鉴权检测、schema 提取

### Task 1.4: FastAPI 端点
- 在 server.py 中注册流量相关端点
- POST /traffic/start, POST /traffic/stop, GET /traffic/records
- POST /traffic/load_har

**Checkpoint 1:** 能加载 HAR 文件 → 分析出接口清单 → 返回结构化结果

---

## Phase 2: 脚本生成与验证（⚙️ 全自动代码，可直接输出）

同样零 AI 依赖，纯逻辑代码。

### Task 2.1: ApiScriptGenerator 脚本生成模块
- 创建 `u2-server/script_generator.py`
- 实现 generate_api_script（Level 1 无鉴权）
- 实现 generate_api_script_with_auth（Level 2 需鉴权）
- 实现 generate_rpa_script（Level 3-4 回退 RPA）
- 实现 save_to_store（写入 ScriptStore）
- 实现 _guess_data_path（猜测数据路径）
- **可直接测试：** 构造 endpoint + analysis，验证生成的脚本格式

### Task 2.2: ScriptVerifier 脚本验证模块
- 创建 `u2-server/script_verifier.py`
- 实现 verify_script（执行脚本并检查结果）
- 实现 verify_data_format（验证数据字段完整性）
- 实现 generate_verify_report（输出验证报告）
- **可直接测试：** mock HTTP 响应，验证脚本执行和数据校验

### Task 2.3: DataMapper 数据映射模块
- 创建 `u2-server/data_mapper.py`
- 实现配置式字段映射（JSON 配置文件）
- 实现数据类型转换
- 实现 HTTP 推送到目标系统
- 创建 `u2-server/platform_configs/` 目录和配置模板
- **可直接测试：** 构造原始数据 + 映射规则，验证转换结果

### Task 2.4: 单元测试
- 创建 `u2-server/tests/test_script_generator.py`
- 创建 `u2-server/tests/test_script_verifier.py`
- 创建 `u2-server/tests/test_data_mapper.py`

**Checkpoint 2:** 给定接口分析结果 → 自动生成脚本 → 验证脚本 → 数据映射

---

## Phase 3: AI 分析层（🤖 AI 驱动，需要 GLM）

这一阶段引入 GLM 做"理解"和"判断"。

### Task 3.1: InterfaceAnalyzer 接口分析模块
- 创建 `u2-server/interface_analyzer.py`
- 实现 analyze_endpoints（GLM 分析接口用途和难度）
- 实现 generate_report（生成 Markdown 报告）
- 实现 _call_glm_text（文本模式调用 GLM）
- 精心设计 ANALYSIS_PROMPT（这是核心）
- **测试方式：** mock GLM 返回，验证 prompt 构造和结果解析

### Task 3.2: PlatformExplorer 平台探索模块
- 创建 `u2-server/platform_explorer.py`
- 复用 VisionAgent 的截图→分析→操作循环
- 新增页面记录功能（每个页面的截图、描述、数据字段）
- 生成平台页面地图
- **测试方式：** 需要真实设备，或 mock VisionAgent

### Task 3.3: FastAPI 端点
- POST /analyze/platform（完整分析流程）
- GET /analyze/reports（列出报告）

**Checkpoint 3:** 能对 HAR 文件执行完整分析 → 输出评估报告 + 采集脚本

---

## Phase 4: 编排与集成（⚙️ 全自动代码）

### Task 4.1: AnalysisOrchestrator 编排器
- 创建 `u2-server/analysis_orchestrator.py`
- 实现 analyze_platform 完整流程
- 实现离线模式（HAR 文件）和实时模式（AI 探索 + 抓包）
- 实现进度输出和人工待办事项收集

### Task 4.2: Bun 入口层扩展
- 在 types.ts 中新增 analyze_platform 指令类型
- 在 skill-cli.ts 中新增路由
- 在 SKILL.md 中新增指令说明

### Task 4.3: 部署文档
- mitmproxy 安装和配置指南
- 手机代理配置指南
- 微信小程序抓包特殊处理指南

**Checkpoint 4:** 一条指令完成全流程

---

## 推荐实施顺序

**立即可以开始写代码的（Phase 1 + 2）：**
1. traffic_capture.py + 测试 ← 最先做，基础模块
2. traffic_analyzer.py + 测试 ← 紧接着，核心分析
3. script_generator.py + 测试 ← 生成脚本
4. script_verifier.py + 测试 ← 验证脚本
5. data_mapper.py + 测试 ← 数据对接

这 5 个模块全是确定性代码，不依赖 AI，不依赖真实设备，可以在本地完整测试。

**需要你提供信息后才能做的：**
- 目标平台列表（聚宝猪等的域名、包名）
- 你的系统对接 API（推送地址、数据格式）
- 一个 HAR 文件样本（用于测试分析流程）

**需要环境准备后才能做的：**
- mitmproxy 安装和手机代理配置
- 微信小程序抓包环境（如果目标是小程序）


---

## Phase 0: 安全防护层（⚙️ 全自动代码，最先实施）

安全层必须在所有其他模块之前完成，是整个系统的基础。

### Task 0.1: ActionGuard 操作安全守卫
- 创建 `u2-server/action_guard.py`
- 实现 4 级操作分级（Level 0-3）
- 实现关键词匹配 + 上下文分析
- 实现 check_action / confirm_pending / reject_pending
- 实现 blocked_log 审计日志
- **可直接测试：** 构造各种操作 + 屏幕上下文，验证分级结果

### Task 0.2: RequestBlocker 网络层拦截器
- 创建 `u2-server/request_blocker.py`
- 实现 URL 模式匹配拦截
- 实现请求体关键词拦截
- 实现 mock 响应生成
- 实现被拦截请求的记录（用于接口分析）
- **可直接测试：** 构造各种 URL + body，验证拦截判断

### Task 0.3: 平台安全配置
- 创建 `u2-server/platform_configs/` 目录
- 创建配置模板 `_template.json`
- 实现配置加载和合并逻辑

### Task 0.4: 安全模块单元测试
- 创建 `u2-server/tests/test_action_guard.py`
- 创建 `u2-server/tests/test_request_blocker.py`
- 覆盖所有安全等级的判断逻辑
- 特别测试边界情况（如"确认"在非交易上下文中应该放行）

### Task 0.5: FastAPI 安全端点
- POST /safety/check, /safety/confirm, /safety/reject
- GET /safety/blocked_log, /safety/blocked_requests
- PUT /safety/config

### Task 0.6: 集成到 VisionAgent
- 修改 vision_agent.py，在 _execute_action 前插入 ActionGuard 检查
- 实现暂停/恢复机制
- 实现 Level 3 自动按返回键退出

**Checkpoint 0:** 安全层独立可用，所有测试通过

---

## 修订后的完整实施顺序

```
Phase 0: 安全防护层 ← 最先做，基础保障
  ↓
Phase 1: 流量捕获与分析 ← 纯代码，可直接测试
  ↓
Phase 2: 脚本生成与验证 ← 纯代码，可直接测试
  ↓
Phase 3: AI 分析层 ← 需要 GLM
  ↓
Phase 4: 编排与集成 ← 串联全流程
```

Phase 0 + Phase 1 + Phase 2 全是确定性代码，
可以直接输出、直接测试、不依赖任何外部服务。
