# Implementation Plan: OpenClaw Mobile RPA Skill

## Overview

基于 TypeScript + Bun 运行时实现 OpenClaw 移动端 RPA Skill。采用自底向上的构建方式：先实现基础设施层（类型定义、ADB 通信、日志），再构建核心模块（屏幕解析、动作执行、模板引擎），最后组装 RPA 循环和 Skill 入口。每个模块完成后紧跟测试任务。

## Tasks

- [x] 1. 项目初始化与类型定义
  - [x] 1.1 创建项目结构和配置文件
    - 在 `~/.openclaw/workspace/skills/mobile-rpa/` 下创建 `package.json`（依赖：fast-check）、`tsconfig.json`
    - 创建 `src/`、`templates/`、`tests/` 目录
    - _Requirements: 1.4_
  - [x] 1.2 定义所有 TypeScript 类型和接口
    - 创建 `src/types.ts`，包含设计文档中所有数据模型：DeviceInfo、UiElement、Bounds、ScreenState、ScreenDiff、Action、ActionResult、OperationTemplate、TemplateParam、TemplateStep、ResolvedTemplate、TemplateSummary、ValidationResult、StepRecord、ExecutionHistory、LoopOptions、ExplorationResult、TemplateExecutionResult、CommandType、ParsedCommand、SkillResponse
    - _Requirements: 3.2, 4.1-4.6, 5.1, 6.3, 7.2_
  - [x] 1.3 创建 SKILL.md 文件
    - 编写符合 OpenClaw 规范的 SKILL.md，包含 YAML frontmatter（name: mobile-rpa, description, requires: [adb], install 脚本）和自然语言指令说明
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. ADB Client 实现
  - [x] 2.1 实现 ADB Client 模块
    - 创建 `src/adb-client.ts`，实现 AdbClient 接口
    - 使用 Bun.spawn 执行 ADB shell 命令
    - 实现 listDevices（解析 `adb devices` 输出）、isConnected、dumpUiHierarchy（`adb shell uiautomator dump`）、tap、inputText、swipe、keyEvent、shell 方法
    - 支持通过 deviceId 参数指定目标设备（`-s` 标志）
    - _Requirements: 2.1, 2.3, 2.4_
  - [x] 2.2 实现日志模块
    - 创建 `src/logger.ts`，支持写入日志文件，包含时间戳、指令内容和执行结果
    - _Requirements: 7.5_

- [x] 3. Screen Parser 实现
  - [x] 3.1 实现屏幕解析器
    - 创建 `src/screen-parser.ts`，实现 ScreenParser 接口
    - 实现 parseAccessibilityTree：解析 ADB uiautomator dump 的 XML 输出，提取 UiElement 列表
    - 实现元素过滤逻辑：移除不可见且不可交互的元素
    - 实现唯一 ID 分配：为每个可交互元素生成 `elem_N` 格式 ID
    - 实现 captureScreen：调用 ADB Client 获取 XML 并解析
    - 实现 diffScreens：比较两个 ScreenState，计算 added/removed/changed
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [ ]* 3.2 编写 Screen Parser 属性测试
    - **Property 1: Accessibility Tree 解析正确性** - 生成随机 XML 节点，验证解析后字段一致
    - **Validates: Requirements 3.2**
    - **Property 2: 不可见/不可交互元素过滤** - 生成混合元素，验证过滤结果不含不可见且不可交互元素
    - **Validates: Requirements 3.3**
    - **Property 3: 元素标识符唯一性** - 对任意解析结果，验证所有 ID 互不相同
    - **Validates: Requirements 3.4**
    - **Property 4: 屏幕差异计算正确性** - 生成两个随机 ScreenState，验证 diff 的 added/removed/changed 正确
    - **Validates: Requirements 3.5**

- [x] 4. Action Executor 实现
  - [x] 4.1 实现动作执行器
    - 创建 `src/action-executor.ts`，实现 ActionExecutor 接口
    - 实现 execute：根据 Action 类型生成对应 ADB 命令并执行，返回 ActionResult
    - 实现执行前连接验证（调用 isConnected）
    - 实现超时控制（AbortController）
    - 实现 executeBatch：顺序执行操作序列
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 2.4, 2.5_
  - [ ]* 4.2 编写 Action Executor 属性测试
    - **Property 5: Action 到 ADB 命令生成正确性** - 生成随机 Action，验证 ADB 命令字符串正确编码类型和参数
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6**
    - **Property 18: 设备序列号选择** - 生成随机设备列表和 ID，验证正确选中
    - **Validates: Requirements 2.3**
    - **Property 19: 执行前连接验证** - 对未连接设备执行操作，验证拒绝执行
    - **Validates: Requirements 2.4**

- [x] 5. Checkpoint - 基础模块验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Template Engine 实现
  - [x] 6.1 实现模板引擎核心功能
    - 创建 `src/template-engine.ts`，实现 TemplateEngine 接口
    - 实现 validateTemplate：验证模板 JSON 结构（必填字段、步骤格式）
    - 实现 serialize/deserialize：模板对象与 JSON 字符串互转
    - 实现 resolveParams：替换 `{{paramName}}` 占位符，检查必填参数
    - 实现 loadTemplates：从目录读取所有 .json 文件并解析为模板
    - 实现 listTemplates：返回模板摘要列表
    - 实现 saveTemplate：将模板保存为 JSON 文件
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_
  - [x] 6.2 实现模板自动生成功能
    - 在 template-engine.ts 中实现 generateFromHistory：将 ExecutionHistory 转换为 OperationTemplate
    - 实现可变部分识别逻辑：检测步骤中的文本输入内容作为候选参数
    - 实现 findMatchingTemplate：根据任务描述匹配已保存模板
    - _Requirements: 5b.1, 5b.2, 5b.3, 5b.4, 5b.5_
  - [ ]* 6.3 编写 Template Engine 属性测试
    - **Property 6: 模板序列化/反序列化往返一致性** - 生成随机 OperationTemplate，验证 serialize→deserialize 等价
    - **Validates: Requirements 5.1, 5.8**
    - **Property 7: 模板格式验证正确性** - 生成有效和无效模板，验证 validateTemplate 结果
    - **Validates: Requirements 5.2**
    - **Property 8: 模板参数替换完整性** - 生成带占位符的模板和完整参数，验证替换后无残留占位符
    - **Validates: Requirements 5.3**
    - **Property 9: 缺失必填参数拒绝** - 生成模板并故意缺少参数，验证拒绝并列出缺失参数
    - **Validates: Requirements 5.5**
    - **Property 10: 模板目录加载完整性** - 创建临时目录写入 N 个模板文件，验证加载数量一致
    - **Validates: Requirements 5.6**
    - **Property 11: 操作历史到模板生成正确性** - 生成随机 ExecutionHistory，验证生成模板的步骤数和 metadata
    - **Validates: Requirements 5b.1, 5b.2, 5b.3, 6.6**

- [x] 7. RPA Loop 实现
  - [x] 7.1 实现 RPA 循环控制器
    - 创建 `src/rpa-loop.ts`，实现 RpaLoop 接口
    - 实现 detectStuck：检查最近 N 步是否相同操作且屏幕未变化
    - 实现 runExploration：自由探索模式循环（感知→确定操作→执行→记录），成功后调用 generateFromHistory
    - 实现 runTemplate：模板执行模式，按步骤顺序执行并记录每步状态
    - 实现模式选择逻辑：根据 findMatchingTemplate 结果决定模式
    - 实现最大步骤数限制和超时控制
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - [ ]* 7.2 编写 RPA Loop 属性测试
    - **Property 12: 双模式选择逻辑** - 生成任务描述和模板集合，验证模式选择与 findMatchingTemplate 一致
    - **Validates: Requirements 6.1, 6.2**
    - **Property 13: 步骤记录完整性** - 对任意执行结果，验证每个 StepRecord 包含必填字段
    - **Validates: Requirements 6.3**
    - **Property 14: 最大步骤数限制** - 设置 maxSteps=N，验证执行步骤不超过 N
    - **Validates: Requirements 6.4**
    - **Property 15: 卡住状态检测** - 生成步骤历史，验证连续 3 次相同操作+相同屏幕时返回 true
    - **Validates: Requirements 6.5**

- [x] 8. Checkpoint - 核心模块验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Skill CLI 入口与集成
  - [x] 9.1 实现 Skill CLI 入口脚本
    - 创建 `src/skill-cli.ts`，实现 SkillCli 接口
    - 实现指令解析：从输入字符串解析 CommandType 和参数
    - 实现 routeCommand：根据指令类型调用对应模块（list_devices→AdbClient, get_screen→ScreenParser, execute_action→ActionExecutor, run_template→TemplateEngine+RpaLoop, run_task→RpaLoop, list_templates→TemplateEngine）
    - 实现统一 JSON 响应格式（status, message, data）
    - 实现未知指令错误处理
    - 集成 Logger 记录所有指令执行
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [ ]* 9.2 编写 Skill CLI 属性测试
    - **Property 16: 响应格式一致性** - 生成随机指令，验证响应始终包含 status 和 message 字段
    - **Validates: Requirements 7.2**
    - **Property 17: 未知指令错误处理** - 生成随机非法指令字符串，验证返回 error 状态和支持的指令列表
    - **Validates: Requirements 7.3**

- [x] 10. 示例模板与集成测试
  - [x] 10.1 创建示例操作模板
    - 在 `templates/` 目录创建 `open-app.json`（打开指定应用）和 `send-message.json`（发送消息）示例模板
    - 模板应包含参数化占位符，展示模板功能
    - _Requirements: 5.1, 5.3_
  - [ ]* 10.2 编写集成测试
    - 测试完整流程：指令输入→模块调用→响应输出
    - 使用 MockAdbClient 模拟设备交互
    - _Requirements: 7.1, 7.2_

- [x] 11. Final checkpoint - 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 所有 ADB 交互通过接口注入，测试时使用 Mock 实现
- 属性测试使用 fast-check 库，每个属性至少 100 次迭代
- 每个属性测试标注格式：`Feature: openclaw-mobile-rpa-skill, Property N: {title}`
