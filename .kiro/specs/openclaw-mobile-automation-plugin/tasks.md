# 实现计划：OpenClaw 移动端自动化插件 (mobile-automation)

## 概述

将现有 mobile-rpa Skill 扩展为多 Skill 插件架构。分阶段实现：先搭建 Python FastAPI 服务基础，再迁移视觉分析，然后实现 AutoX.js 集成，接着构建数据采集系统，最后扩展 Bun 入口层并完成部署配置。

## Tasks

- [x] 1. Python FastAPI 服务基础搭建 (u2-server)
  - [x] 1.1 初始化 uv 项目，创建 `u2-server/pyproject.toml`，添加 fastapi、uvicorn、uiautomator2、httpx、pillow 依赖
    - 创建 `u2-server/` 目录结构
    - 配置 `pyproject.toml` 中的 project name、version、requires-python、dependencies
    - _Requirements: 2.1_

  - [x] 1.2 实现 DeviceManager (`u2-server/device.py`)
    - 封装 uiautomator2 设备连接管理（连接缓存、多设备支持）
    - 实现 list_devices、screenshot_base64、click、swipe、input_text、key_event
    - 实现 find_element、click_element（支持 text/resourceId/xpath 三种选择器）
    - 实现 get_clipboard、set_clipboard、app_start、app_stop、current_app、ui_hierarchy
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.10_

  - [ ]* 1.3 编写 DeviceManager 属性测试
    - **Property 1: U2 API 点击坐标接受性**
    - **Property 2: U2 API 文本输入（含中文）**
    - **Property 3: U2 API 三种元素选择器支持**
    - **Property 4: 剪贴板读写往返一致性**
    - **Validates: Requirements 2.3, 2.4, 2.5, 2.7**

  - [x] 1.4 实现 FastAPI 服务入口 (`u2-server/server.py`)
    - 创建 FastAPI app，注册所有设备操作端点
    - 定义 Pydantic 请求/响应模型（ClickRequest、SwipeRequest、InputTextRequest、FindElementRequest 等）
    - 实现 /health、/devices、/device/{id}/* 系列端点
    - 实现错误处理中间件（设备未连接、操作超时等）
    - _Requirements: 2.1, 2.9, 2.10_

- [x] 2. Checkpoint - 确保 U2 服务基础可运行
  - 确保所有测试通过，ask the user if questions arise.

- [x] 3. GLM-4.6V 视觉分析迁移至 Python
  - [x] 3.1 实现 GlmVisionClient (`u2-server/vision.py`)
    - 使用 httpx 流式调用 GLM-4.6V API
    - 支持自定义 prompt 参数
    - 实现超时处理（120 秒）和错误处理
    - _Requirements: 3.1, 3.4, 3.5_

  - [x] 3.2 实现 VisionAgent (`u2-server/vision_agent.py`)
    - 从 TypeScript vision-agent.ts 迁移智能决策逻辑到 Python
    - 实现 run_task 循环（截图→分析→决策→执行）
    - 实现 parse_vision_response 解析 GLM 返回的 JSON 操作
    - 实现步骤上限控制
    - _Requirements: 3.2, 3.3_

  - [ ]* 3.3 编写 VisionAgent 属性测试
    - **Property 5: 智能任务步骤上限**
    - **Validates: Requirements 3.3**

  - [x] 3.4 在 server.py 中注册视觉分析端点
    - 实现 POST /vision/analyze 和 POST /vision/smart_task
    - 定义 VisionAnalyzeRequest、SmartTaskRequest 模型
    - _Requirements: 3.2, 3.3, 3.4_

- [x] 4. Checkpoint - 确保视觉分析功能可用
  - 确保所有测试通过，ask the user if questions arise.

- [x] 5. ScriptStore 脚本仓库实现
  - [x] 5.1 实现 ScriptStore (`u2-server/script_store.py`)
    - 实现脚本的 CRUD 操作（save、find、list_all、delete）
    - 实现 find_navigation 按 App 和目标页面查找导航脚本
    - 实现 mark_invalid、update_usage、update_validation
    - 实现 serialize/deserialize（JSON 文件读写）
    - 脚本存储在 `u2-server/scripts/` 目录
    - 每个脚本保存为独立 JSON 文件，文件名为脚本 ID
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ]* 5.2 编写 ScriptStore 属性测试
    - **Property 11: 脚本标识符唯一性**
    - **Property 12: 脚本按 App 和数据类型查找**
    - **Property 13: 脚本列表完整性**
    - **Property 14: 脚本无效标记与查找排除**
    - **Property 15: 脚本删除**
    - **Property 16: 脚本使用计数递增**
    - **Property 17: 脚本序列化/反序列化往返一致性**
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8**

- [x] 6. 数据采集核心实现
  - [x] 6.1 实现采集策略基类和三种策略 (`u2-server/strategies/`)
    - 创建 BaseStrategy 抽象基类（explore、execute 方法）
    - 实现 ApiStrategy（HTTP 直连已知 API）
    - 实现 RpaCopyStrategy（导航→长按→全选→复制→读剪贴板）
    - 实现 RpaOcrStrategy（导航→截图→GLM OCR→翻页→合并）
    - _Requirements: 6.1_

  - [x] 6.2 实现 Navigator (`u2-server/navigator.py`)
    - 实现 navigate_to：优先用已有脚本，无脚本则用 VisionAgent 探索
    - 实现 explore：调用 VisionAgent 自主探索到达目标页面
    - 实现 execute_script：按已保存脚本步骤执行导航
    - 探索成功后自动保存导航脚本
    - _Requirements: 6.3_

  - [x] 6.3 实现 DataCollector (`u2-server/collector.py`)
    - 实现策略优先级调度（api > rpa_copy > rpa_ocr）
    - 实现脚本优先逻辑（有有效脚本先用脚本）
    - 实现 force_strategy 参数支持
    - 采集成功后保存脚本到 ScriptStore
    - 返回标准化 JSON 结果
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 6.4 编写 DataCollector 属性测试
    - **Property 6: 数据采集策略优先级**
    - **Property 7: 脚本优先与探索回退**
    - **Property 8: 采集成功后脚本保存**
    - **Property 9: 强制策略限制**
    - **Property 10: 采集结果格式一致性**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.6, 6.7**

  - [x] 6.5 在 server.py 中注册数据采集端点
    - 实现 POST /collect、GET /scripts、POST /scripts/validate、DELETE /scripts/{id}
    - 定义 CollectRequest 模型
    - _Requirements: 6.1, 7.4_

- [x] 7. ScriptValidator 脚本验证器实现
  - [x] 7.1 实现 ScriptValidator (`u2-server/validator.py`)
    - 实现 validate_all：逐一验证所有脚本
    - 实现 validate_one：执行单个脚本并检查结果
    - 验证失败标记脚本无效，验证成功更新验证时间
    - 返回验证摘要（total、success、failure）
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 7.2 编写 ScriptValidator 属性测试
    - **Property 18: 脚本验证覆盖与结果摘要**
    - **Property 19: 验证失败标记无效**
    - **Property 20: 验证成功更新时间**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 8. Checkpoint - 确保 Python 服务完整可用
  - 确保所有测试通过，ask the user if questions arise.

- [x] 9. AutoX.js 集成
  - [x] 9.1 创建 AutoX.js 手机端 HTTP 服务脚本 (`autox/autox-server.js`)
    - 实现 HTTP 服务（端口 9500）
    - 实现 /click、/input、/find_element、/ocr、/clipboard、/run_script 端点
    - 使用 AutoX.js 无障碍服务 API
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 9.2 创建 frp 配置文件
    - 创建 `deploy/frps.toml`（frp 服务端配置）
    - 创建 `deploy/frpc.toml`（frp 客户端配置，隧道 9500 端口）
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 9.3 实现 AutoX 客户端 (`src/autox-client.ts`)
    - 实现 AutoXClient 类，通过 HTTP 调用 frp 映射端口
    - 实现 click、inputText、findElement、ocr、readClipboard、runScript、healthCheck
    - 实现连接失败检测和错误处理
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 9.4 编写 AutoX 客户端单元测试
    - 测试 frp 隧道断开时的错误处理
    - 测试各操作的请求格式
    - _Requirements: 4.8_

- [x] 10. Bun 入口层扩展
  - [x] 10.1 实现 U2 服务 HTTP 代理 (`src/u2-proxy.ts`)
    - 实现 callU2 函数，封装对 U2_Service 的 HTTP 调用
    - 实现连接检测和超时处理
    - 实现 U2 不可用时回退到 ADB 直连的逻辑
    - _Requirements: 9.2, 9.5_

  - [ ]* 10.2 编写 U2 代理属性测试
    - **Property 21: 设备操作指令转发至 U2**
    - **Validates: Requirements 9.2**

  - [x] 10.3 扩展 types.ts 新增类型定义
    - 新增 CommandType：collect_data、list_scripts、validate_scripts、autox_execute
    - 新增 CollectionScript、CollectionResult、AutoXSelector 等类型
    - _Requirements: 9.1_

  - [x] 10.4 扩展 skill-cli.ts 指令路由
    - 新增 collect_data、list_scripts、validate_scripts 指令处理（转发给 U2_Service）
    - 新增 autox_execute 指令处理（转发给 AutoX_Service）
    - 保持现有指令向后兼容
    - 设备操作指令优先走 U2_Service，不可用时回退 ADB
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 10.5 编写入口层扩展属性测试
    - **Property 22: AutoX 指令转发**
    - **Property 23: 现有指令向后兼容**
    - **Property 24: 统一响应格式**
    - **Validates: Requirements 9.3, 9.4, 9.6**

- [x] 11. Checkpoint - 确保所有组件集成正常
  - 确保所有测试通过，ask the user if questions arise.

- [x] 12. Skill 定义文件与部署配置
  - [x] 12.1 创建各 Skill 的 SKILL.md 文件
    - 更新现有 `SKILL.md`（mobile-rpa，新增对 U2 服务的说明）
    - 创建 `skills/mobile-u2-SKILL.md`（描述 U2 服务能力和接口）
    - 创建 `autox/SKILL.md`（描述 AutoX.js 能力和接口）
    - 创建 `skills/mobile-data-collector-SKILL.md`（描述数据采集能力和指令）
    - _Requirements: 1.1, 1.2_

  - [x] 12.2 编写完整部署指南 (`deploy/DEPLOY.md`)
    - 云服务器部署：uv 安装、Python 依赖、U2_Service 启动、frp 服务端
    - 手机端部署：AutoX.js APK 安装、无障碍权限、frp 客户端
    - uiautomator2 初始化（推送 agent 到手机）
    - 健康检查方法
    - 日常启动顺序
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 13. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Python 代码使用 `pytest` + `hypothesis` 进行测试，TypeScript 代码使用 `bun test` + `fast-check`
- Python 环境使用 `uv` 管理，不使用 pip 或 conda
- 所有设备操作通过 Mock 测试，不依赖真实设备
- Checkpoints 确保增量验证，每个阶段独立可用
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
