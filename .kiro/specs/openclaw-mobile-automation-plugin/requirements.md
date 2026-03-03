# 需求文档：OpenClaw 移动端自动化插件 (mobile-automation)

## 简介

本功能将现有的 mobile-rpa Skill 扩展为一个包含多个 Skill 的 OpenClaw 插件（Plugin）。插件名为 `mobile-automation`，包含四个 Skill：现有的 `mobile-rpa`（ADB 基础操作）、新增的 `mobile-u2`（基于 uiautomator2 的高性能 Python FastAPI 服务）、`mobile-autox`（基于 AutoX.js 的手机端 JavaScript 自动化）、以及 `mobile-data-collector`（多策略数据采集编排器）。三种设备访问方式（ADB 隧道、uiautomator2、AutoX.js）共存，Skill 之间可互相调用并共享资源。

## 术语表

- **OpenClaw**: AI Agent 平台，通过 Skill 扩展能力
- **Plugin**: OpenClaw 的能力扩展包，包含多个相关 Skill
- **Skill**: OpenClaw 的能力扩展单元，包含 SKILL.md 描述文件和支撑脚本
- **SKILL_MD**: Skill 的定义文件，包含 YAML frontmatter 和 Markdown 指令说明
- **U2_Service**: 基于 uiautomator2 和 FastAPI 的 Python 设备操作服务，运行于云服务器 9400 端口
- **AutoX_Service**: 运行于手机端的 AutoX.js HTTP 服务，通过 frp 隧道暴露到云服务器
- **Data_Collector**: 多策略数据采集编排器，协调使用不同自动化引擎采集 App 数据
- **Script_Store**: 脚本仓库，以 JSON 格式存储已学习的成功采集脚本供复用
- **Navigator**: 导航管理器，负责到达目标 App 的目标页面
- **Script_Validator**: 脚本验证器，定期验证已保存脚本的有效性
- **frp**: 快速反向代理工具，用于将手机端服务隧道到云服务器
- **uv**: Python 包管理工具，用于管理 Python 环境和依赖
- **GLM_Vision**: 智谱 GLM-4.6V 视觉语言模型，用于屏幕截图分析和智能决策
- **Bun_Entry**: 基于 Bun 运行时的 TypeScript 入口脚本 (skill-cli.ts)，作为 OpenClaw 的统一接口

## 需求

### 需求 1：插件结构与多 Skill 注册

**用户故事：** 作为 OpenClaw 用户，我希望移动端自动化能力以插件形式组织多个 Skill，以便按需调用不同的自动化能力。

#### 验收标准

1. THE Plugin SHALL 包含四个独立的 Skill 目录，每个目录包含各自的 SKILL_MD 文件：mobile-rpa、mobile-u2、mobile-autox、mobile-data-collector
2. WHEN OpenClaw Agent 加载插件目录时，THE Plugin SHALL 使所有 Skill 被正确识别并可独立调用
3. THE Bun_Entry SHALL 作为统一入口，根据配置将指令路由到对应的后端服务（U2_Service 或 AutoX_Service）
4. THE Plugin SHALL 支持 Skill 之间的资源共享，包括脚本仓库、操作模板和 GLM_Vision 客户端

### 需求 2：uiautomator2 Python 服务 (mobile-u2)

**用户故事：** 作为用户，我希望通过 uiautomator2 获得高性能的设备操作能力，以便大幅提升截图、元素查找和文本输入的速度。

#### 验收标准

1. THE U2_Service SHALL 以 FastAPI 应用形式运行于云服务器 9400 端口，使用 uv 管理 Python 环境和依赖
2. WHEN 收到截图请求时，THE U2_Service SHALL 通过 uiautomator2 获取设备截图并以 base64 格式返回
3. WHEN 收到点击请求时，THE U2_Service SHALL 通过 uiautomator2 在指定坐标执行点击操作
4. WHEN 收到文本输入请求时，THE U2_Service SHALL 通过 uiautomator2 输入指定文本，包括中文字符
5. WHEN 收到元素查找请求时，THE U2_Service SHALL 支持通过 text、resourceId 和 XPath 三种选择器查找元素
6. THE U2_Service SHALL 提供设备管理接口，包括列出设备、获取设备信息、启动和停止 App、获取当前前台 App
7. THE U2_Service SHALL 提供剪贴板读写接口
8. THE U2_Service SHALL 提供 UI 层级树获取接口
9. THE U2_Service SHALL 提供健康检查接口，返回服务运行状态
10. IF U2_Service 与设备的连接断开，THEN THE U2_Service SHALL 返回明确的连接错误信息

### 需求 3：GLM-4.6V 视觉分析迁移至 Python

**用户故事：** 作为用户，我希望视觉分析能力迁移到 Python 服务中，以便与 uiautomator2 的高速截图配合使用，减少数据传输开销。

#### 验收标准

1. THE U2_Service SHALL 包含 GLM_Vision 客户端，支持通过 httpx 流式调用 GLM-4.6V API
2. WHEN 收到视觉分析请求时，THE U2_Service SHALL 对指定设备截图并发送给 GLM_Vision 进行分析，返回分析结果
3. WHEN 收到智能任务请求时，THE U2_Service SHALL 执行"截图→GLM分析→决定操作→执行操作"的循环，直到任务完成或达到步骤上限
4. THE U2_Service 的视觉分析接口 SHALL 接受自定义 prompt 参数
5. IF GLM_Vision API 调用失败或超时，THEN THE U2_Service SHALL 返回包含错误详情的响应

### 需求 4：AutoX.js 手机端自动化 (mobile-autox)

**用户故事：** 作为用户，我希望通过 AutoX.js 在手机端直接运行 JavaScript 自动化脚本，以便利用无障碍服务实现更灵活的自动化操作。

#### 验收标准

1. THE AutoX_Service SHALL 在手机端运行 HTTP 服务（端口 9500），通过 frp 隧道映射到云服务器的指定端口
2. WHEN 收到点击请求时，THE AutoX_Service SHALL 通过无障碍服务在指定坐标或指定元素上执行点击
3. WHEN 收到文本输入请求时，THE AutoX_Service SHALL 在当前焦点元素输入指定文本
4. WHEN 收到元素查找请求时，THE AutoX_Service SHALL 通过无障碍服务查找匹配的 UI 元素
5. WHEN 收到 OCR 请求时，THE AutoX_Service SHALL 使用内置 Paddle OCR 识别屏幕文字
6. WHEN 收到剪贴板读取请求时，THE AutoX_Service SHALL 返回当前剪贴板内容
7. WHEN 收到自定义脚本执行请求时，THE AutoX_Service SHALL 执行提供的 JavaScript 脚本并返回执行结果
8. IF AutoX_Service 的 frp 隧道断开，THEN THE Bun_Entry SHALL 检测连接失败并返回隧道不可用的错误信息

### 需求 5：frp 隧道配置与管理

**用户故事：** 作为用户，我希望 frp 隧道能够稳定地将手机端 AutoX.js 服务暴露到云服务器，以便从云端远程调用手机端自动化能力。

#### 验收标准

1. THE Plugin SHALL 提供 frp 服务端配置文件，用于在云服务器上运行 frp 服务端
2. THE Plugin SHALL 提供 frp 客户端配置文件，用于在手机端将 AutoX_Service 的 HTTP 端口隧道到云服务器
3. WHEN frp 隧道建立成功时，THE 云服务器 SHALL 能够通过 localhost 加映射端口访问 AutoX_Service
4. THE Plugin SHALL 提供完整的部署指南，包括 AutoX.js APK 安装、无障碍权限设置、frp 客户端配置和 frp 服务端配置

### 需求 6：多策略数据采集 (mobile-data-collector)

**用户故事：** 作为用户，我希望系统能够从任意 App 智能采集数据，自动选择最优采集策略，并将成功的采集流程保存为可复用脚本。

#### 验收标准

1. WHEN 收到数据采集指令时，THE Data_Collector SHALL 按优先级依次尝试采集策略：API 直连优先，其次 RPA 剪贴板复制，最后截图 OCR
2. WHEN 已存在针对目标 App 和数据类型的有效脚本时，THE Data_Collector SHALL 优先使用已保存脚本执行采集
3. WHEN 无可用脚本时，THE Data_Collector SHALL 使用 Navigator 通过智能任务探索到达目标页面，然后按策略优先级尝试采集
4. WHEN 采集成功时，THE Data_Collector SHALL 将采集流程保存为脚本到 Script_Store 中
5. THE Data_Collector SHALL 支持通过配置指定使用 U2_Service 或 AutoX_Service 作为底层自动化引擎
6. WHEN 收到强制策略参数时，THE Data_Collector SHALL 仅使用指定的策略进行采集
7. THE Data_Collector SHALL 以标准化 JSON 格式返回采集到的数据

### 需求 7：脚本仓库管理

**用户故事：** 作为用户，我希望成功的采集脚本能够被保存和管理，以便后续直接复用而无需重新探索。

#### 验收标准

1. THE Script_Store SHALL 以 JSON 文件格式存储采集脚本，每个脚本包含目标 App、数据类型、采集策略、导航步骤和提取配置
2. WHEN 保存新脚本时，THE Script_Store SHALL 为脚本分配唯一标识符并记录创建时间
3. WHEN 查找脚本时，THE Script_Store SHALL 根据 App 名称和数据类型匹配已保存的有效脚本
4. WHEN 列出脚本时，THE Script_Store SHALL 返回所有脚本的摘要信息，包括标识符、App、数据类型、策略和有效性状态
5. THE Script_Store SHALL 支持将脚本标记为无效状态
6. THE Script_Store SHALL 支持删除指定脚本
7. WHEN 脚本被成功使用时，THE Script_Store SHALL 更新脚本的最后使用时间和使用次数
8. THE Script_Store SHALL 支持脚本的序列化和反序列化，将脚本对象与 JSON 文件互相转换

### 需求 8：脚本验证

**用户故事：** 作为用户，我希望系统能够定期验证已保存脚本的有效性，以便及时发现失效脚本并触发重新探索。

#### 验收标准

1. WHEN 收到验证指令时，THE Script_Validator SHALL 逐一执行所有已保存脚本的采集流程并检查是否仍能成功采集数据
2. WHEN 脚本验证失败时，THE Script_Validator SHALL 将该脚本标记为无效状态
3. WHEN 脚本验证成功时，THE Script_Validator SHALL 更新脚本的最后验证时间
4. THE Script_Validator SHALL 返回验证结果摘要，包括验证总数、成功数和失败数

### 需求 9：Bun 入口层扩展

**用户故事：** 作为 OpenClaw 用户，我希望通过现有的 Bun/TypeScript 入口脚本访问所有新增功能，以便保持与 OpenClaw 的接口兼容性。

#### 验收标准

1. THE Bun_Entry SHALL 新增以下指令类型：collect_data、list_scripts、validate_scripts、autox_execute
2. WHEN 收到设备操作类指令时，THE Bun_Entry SHALL 将请求转发给 U2_Service（HTTP 调用 localhost:9400）
3. WHEN 收到 AutoX 相关指令时，THE Bun_Entry SHALL 将请求转发给 AutoX_Service（HTTP 调用 frp 映射端口）
4. THE Bun_Entry SHALL 保持现有指令（list_devices、get_screen、execute_action、run_template、run_task、list_templates、screenshot、analyze_screen、smart_task）的向后兼容性
5. IF U2_Service 不可用，THEN THE Bun_Entry SHALL 回退到现有的 ADB 直连方式执行设备操作
6. THE Bun_Entry SHALL 以统一的 JSON 格式（status、message、data）返回所有指令的执行结果

### 需求 10：部署与环境配置

**用户故事：** 作为运维人员，我希望有完整的部署指南，以便在云服务器和手机上正确配置所有组件。

#### 验收标准

1. THE Plugin SHALL 提供云服务器部署指南，包括 uv 安装、Python 依赖安装、U2_Service 启动和 frp 服务端配置
2. THE Plugin SHALL 提供手机端部署指南，包括 AutoX.js APK 安装、无障碍权限设置和 frp 客户端配置
3. THE Plugin SHALL 提供 uiautomator2 初始化指南，包括向手机推送 agent 的步骤
4. WHEN 所有组件部署完成后，THE Plugin SHALL 支持三种设备访问方式共存：ADB SSH 隧道、uiautomator2（通过 ADB）、AutoX.js（通过 frp 隧道）
5. THE Plugin SHALL 提供各组件的健康检查方法，用于验证部署是否成功
