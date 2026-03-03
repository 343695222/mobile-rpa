# Implementation Plan: GUI-Plus 集成

## Overview

将 OpenClaw 平台从 GLM-4V/4.6V 迁移到阿里云百炼平台多模型架构。按自底向上顺序实现：先建模型客户端和操作映射，再适配 VisionAgent，最后更新服务层和 agent.py。

## Tasks

- [x] 1. 创建百炼平台客户端模块和操作映射模块
  - [x] 1.1 创建 `u2-server/dashscope_client.py`，实现 GuiPlusClient 类
    - 实现 `decide(base64_image, task_prompt, history)` 异步方法
    - 实现 `smart_size(original_width, original_height, model_x, model_y, max_pixels)` 静态方法
    - 实现 `_build_messages` 方法构建 OpenAI 兼容消息列表
    - 实现 `_parse_response` 方法解析 GUI-Plus JSON 响应（thought/action/parameters）
    - 定义 `GUI_PLUS_SYSTEM_PROMPT` 常量（手机场景适配版）
    - 支持 `vl_high_resolution_images` 参数和 DASHSCOPE_API_KEY 环境变量
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 12.1, 12.2, 12.3_

  - [x] 1.2 在 `u2-server/dashscope_client.py` 中实现 DashScopeVLClient 类
    - 实现 `analyze(base64_image, prompt)` 异步方法，接口与 GlmVisionClient 完全兼容
    - 返回格式：`{"success": bool, "description": str, "model": str, "error"?: str}`
    - 使用 OpenAI 兼容 API 流式接收响应
    - _Requirements: 7.2, 7.3_

  - [x] 1.3 在 `u2-server/dashscope_client.py` 中实现 DashScopeTextClient 类
    - 实现 `chat(messages)` 异步方法，返回模型文本响应
    - 使用 qwen-turbo 模型，共用 DASHSCOPE_API_KEY
    - _Requirements: 7.4, 7.5_

  - [x] 1.4 创建 `u2-server/action_mapper.py`，实现 ActionMapper 类
    - 实现 `map_action(action, parameters)` 静态方法
    - 实现 CLICK→tap、TYPE→input_text、SCROLL→swipe、KEY_PRESS→key_event 映射
    - 定义 KEY_MAP 按键名到 Android KeyEvent 代码映射
    - SCROLL 方向映射：根据 direction 计算 swipe 起止坐标
    - FINISH/FAIL 返回 None（任务终止信号）
    - 未知 action 类型返回错误信息而非抛出异常
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 11.5_

  - [ ]* 1.5 为 smart_size 编写属性测试
    - **Property 1: smart_size 坐标映射往返一致性**
    - **Validates: Requirements 3.5**

  - [ ]* 1.6 为 GuiPlusClient 响应解析编写属性测试
    - **Property 2: GuiPlusClient 响应解析正确性**
    - **Validates: Requirements 1.4**

  - [ ]* 1.7 为 GuiPlusClient 错误处理编写属性测试
    - **Property 3: GuiPlusClient 错误处理完备性**
    - **Validates: Requirements 1.5, 11.1, 11.2, 11.3**

  - [ ]* 1.8 为 ActionMapper 编写属性测试
    - **Property 4: ActionMapper 操作映射有效性**
    - **Property 5: ActionMapper 未知操作优雅处理**
    - **Validates: Requirements 5.6, 11.5**

- [x] 2. Checkpoint - 确保客户端和映射模块测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 适配 VisionAgent 决策循环
  - [x] 3.1 修改 `u2-server/vision_agent.py`，适配 GuiPlusClient
    - 构造参数从 `vision_client: GlmVisionClient` 改为 `gui_plus_client: GuiPlusClient`
    - `decide_next_action` 改为调用 `GuiPlusClient.decide()` 并通过 `ActionMapper.map_action()` 转换操作
    - 新增 `_parse_gui_plus_response` 方法处理 thought/action/parameters 格式
    - FINISH → 任务成功完成，FAIL → 任务失败
    - SafetyGuard 检查使用映射后的操作字典和 thought 字段
    - 移除旧的 SYSTEM_PROMPT 常量（由 GuiPlusClient 管理）
    - 保留 run_task 返回格式（success/stepsCompleted/steps/message）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 9.1, 9.2, 9.3_

  - [ ]* 3.2 为 VisionAgent 返回格式编写属性测试
    - **Property 6: VisionAgent 返回格式一致性**
    - **Validates: Requirements 4.6**

  - [ ]* 3.3 为 VisionAgent SafetyGuard 集成编写属性测试
    - **Property 7: VisionAgent SafetyGuard 集成**
    - **Validates: Requirements 9.1**

- [x] 4. Checkpoint - 确保 VisionAgent 适配测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 更新 FastAPI 服务层和 agent.py
  - [x] 5.1 修改 `u2-server/server.py`，替换模型客户端初始化
    - 从 DASHSCOPE_API_KEY 读取密钥，支持 DASHSCOPE_GUI_MODEL/VL_MODEL/TEXT_MODEL 环境变量
    - 用 GuiPlusClient 初始化 VisionAgent
    - 用 DashScopeVLClient 替代 GlmVisionClient 用于 /vision/analyze 和 RpaOcrStrategy
    - 更新 DataCollector 和 Navigator 的依赖注入
    - DASHSCOPE_API_KEY 未设置时记录警告
    - 保留所有 API 端点路径和请求/响应格式不变
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.4, 10.1, 10.2, 10.3, 10.4, 11.4_

  - [x] 5.2 修改 `u2-server/server_autox.py`，替换模型客户端初始化
    - 用 GuiPlusClient + DashScopeVLClient 替代 GlmVisionClient
    - 将 /vision/smart_task 的内联决策循环替换为 VisionAgent 调用
    - /vision/analyze 使用 DashScopeVLClient
    - 保留所有 API 端点路径和请求/响应格式不变
    - _Requirements: 8.1, 8.3, 8.5_

  - [x] 5.3 修改 `u2-server/agent.py`，替换 GLM 文本调用
    - 用 DashScopeTextClient 替代 call_glm 函数
    - 更新 GLM_API_URL/GLM_API_KEY/GLM_MODEL 为百炼平台配置
    - summarize_result 函数使用 DashScopeTextClient.chat()
    - _Requirements: 7.4, 7.5_

  - [x] 5.4 修改 `u2-server/collector.py`，更新类型注解
    - 构造参数 vision_client 类型从 GlmVisionClient 改为 DashScopeVLClient
    - 更新 import 语句
    - _Requirements: 10.1, 10.2, 10.4_

- [x] 6. Final checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 属性测试使用 Hypothesis 库，每个属性最少 100 次迭代
- GlmVisionClient（vision.py）保留不删除，作为备用
- 所有百炼模型共用 DASHSCOPE_API_KEY 环境变量
