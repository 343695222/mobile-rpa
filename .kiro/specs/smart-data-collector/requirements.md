# 需求文档：智能数据采集系统

## 简介

本功能为 OpenClaw 移动端 RPA Skill 构建一个智能数据采集系统。系统在现有 Bun/TS Skill 基础上新增 Python FastAPI 服务层（u2-server），同时支持 uiautomator2 和 AutoX.js 两种 RPA 后端，实现多策略自动降级的数据采集（API 直连 > RPA 复制粘贴 > 截图 OCR）。系统具备脚本自动学习与复用能力，首次探索自动保存采集脚本，后续执行直接复用，并通过每日验证确保脚本持续有效。

## 术语表

- **U2_Server**: 基于 Python FastAPI 的设备操作服务，运行于云服务器 9400 端口，统一管理两种 RPA 后端
- **uiautomator2_Backend**: 基于 Python uiautomator2 库的设备操作后端，通过 ADB SSH 隧道连接 Android 设备
- **AutoX_Backend**: 基于 AutoX.js 的设备操作后端，AutoX.js 运行于 Android 手机上，通过 frp 隧道将 HTTP 服务暴露到云服务器
- **Device_Interface**: 统一设备操作接口，抽象 uiautomator2_Backend 和 AutoX_Backend 的差异，提供一致的操作 API
- **Data_Collector**: 数据采集调度器，按策略优先级调度采集任务，支持自动降级
- **Collection_Strategy**: 数据采集策略，包括 API 直连策略、RPA 复制粘贴策略、RPA 截图 OCR 策略
- **Script_Store**: 脚本仓库，存储已学习的采集脚本（JSON 格式），支持按 App 和数据类型检索
- **Script_Validator**: 脚本验证器，定期验证已保存脚本的有效性，失效脚本标记为无效
- **Navigator**: 智能导航管理器，负责从当前屏幕导航到目标 App 的目标页面
- **Vision_Client**: GLM-4.6V 视觉模型客户端（Python 版），用于截图分析和 OCR 识别
- **Skill_CLI**: 现有 Bun/TS 入口脚本，改造后将设备操作和采集指令转发给 U2_Server
- **frp_Tunnel**: frp 内网穿透隧道，将手机上 AutoX.js 的 HTTP 服务端口映射到云服务器

## 需求

### 需求 1：Python FastAPI 服务基础架构

**用户故事：** 作为开发者，我希望有一个基于 Python FastAPI 的服务作为设备操作和数据采集的统一后端，以便利用 uiautomator2 等 Python 生态工具获得更高性能的设备控制能力。

#### 验收标准

1. THE U2_Server SHALL 使用 uv 管理 Python 环境和依赖，项目根目录包含 pyproject.toml 配置文件
2. THE U2_Server SHALL 基于 FastAPI 框架构建，使用 uvicorn 作为 ASGI 服务器，监听 127.0.0.1:9400 端口
3. WHEN U2_Server 启动时，THE U2_Server SHALL 提供 GET /health 端点返回服务状态信息，包含版本号和已连接设备数量
4. THE U2_Server SHALL 将所有代码文件存放于项目根目录的 u2-server/ 子目录中
5. IF U2_Server 启动失败，THEN THE U2_Server SHALL 在标准错误输出中记录失败原因并以非零退出码退出

### 需求 2：uiautomator2 设备操作后端

**用户故事：** 作为开发者，我希望通过 uiautomator2 库控制 Android 设备，以便获得比原生 ADB 命令更快的截图、元素查找和中文输入能力。

#### 验收标准

1. THE uiautomator2_Backend SHALL 通过 ADB SSH 隧道连接设备，支持通过设备序列号指定目标设备
2. WHEN 收到截图请求时，THE uiautomator2_Backend SHALL 调用 uiautomator2 的 screenshot 方法获取屏幕截图并返回 base64 编码的 PNG 图片
3. WHEN 收到点击请求时，THE uiautomator2_Backend SHALL 在指定坐标位置执行点击操作
4. WHEN 收到滑动请求时，THE uiautomator2_Backend SHALL 执行从起点到终点的滑动操作，支持指定滑动时长
5. WHEN 收到文本输入请求时，THE uiautomator2_Backend SHALL 使用 uiautomator2 的 send_keys 方法输入文本，支持中文字符
6. WHEN 收到元素查找请求时，THE uiautomator2_Backend SHALL 支持通过 text、resourceId、xpath 三种方式查找 UI 元素
7. THE uiautomator2_Backend SHALL 支持读取和写入设备剪贴板内容
8. WHEN 收到 App 管理请求时，THE uiautomator2_Backend SHALL 支持启动、停止 App 以及查询当前前台 App 信息
9. WHEN 收到 UI 层级树请求时，THE uiautomator2_Backend SHALL 返回当前屏幕的完整 UI 层级结构（XML 格式）
10. IF 设备未连接或操作执行失败，THEN THE uiautomator2_Backend SHALL 返回包含错误类型和描述信息的错误响应

### 需求 3：AutoX.js 设备操作后端

**用户故事：** 作为开发者，我希望同时支持 AutoX.js 作为备选 RPA 后端，以便对比两种方案的稳定性和性能，选择更适合的方案。

#### 验收标准

1. THE AutoX_Backend SHALL 通过 frp_Tunnel 连接运行在手机上的 AutoX.js HTTP 服务
2. WHEN 收到设备操作请求时，THE AutoX_Backend SHALL 将请求转换为 AutoX.js HTTP API 调用并转发到 frp 隧道地址
3. THE AutoX_Backend SHALL 支持与 uiautomator2_Backend 相同的操作集合：截图、点击、滑动、文本输入、元素查找
4. IF frp_Tunnel 连接不可用，THEN THE AutoX_Backend SHALL 返回连接错误并建议检查 frp 隧道状态
5. THE AutoX_Backend SHALL 支持配置 frp 隧道的目标地址和端口

### 需求 4：统一设备操作接口

**用户故事：** 作为开发者，我希望两种 RPA 后端共享统一的操作接口，以便上层业务代码无需关心底层使用哪种后端，并可在运行时切换。

#### 验收标准

1. THE Device_Interface SHALL 定义统一的抽象接口，包含截图、点击、滑动、文本输入、元素查找、剪贴板操作、App 管理等方法
2. THE uiautomator2_Backend 和 AutoX_Backend SHALL 分别实现 Device_Interface 的所有方法
3. WHEN 收到设备操作请求时，THE U2_Server SHALL 根据请求参数或全局配置选择对应的后端执行操作
4. WHEN 切换后端时，THE U2_Server SHALL 支持通过 API 调用在运行时切换默认后端，无需重启服务
5. THE U2_Server SHALL 提供 GET /backends 端点返回当前可用后端列表及各后端的连接状态

### 需求 5：视觉分析服务（Python 版）

**用户故事：** 作为开发者，我希望将 GLM-4.6V 视觉分析能力迁移到 Python 服务中，以便数据采集流程可以在 Python 层内完成截图分析，减少跨进程调用开销。

#### 验收标准

1. THE Vision_Client SHALL 调用 GLM-4.6V API 进行图片分析，支持流式接收响应
2. WHEN 收到视觉分析请求时，THE Vision_Client SHALL 接受 base64 编码的图片和自然语言 prompt，返回分析结果文本
3. IF GLM API 调用失败或超时，THEN THE Vision_Client SHALL 返回包含错误类型和描述的错误响应
4. THE Vision_Client SHALL 使用 httpx 异步 HTTP 客户端发送请求，超时时间设置为 120 秒
5. THE U2_Server SHALL 提供 POST /vision/analyze 端点，接受 deviceId 和 prompt 参数，自动截图并调用 Vision_Client 分析

### 需求 6：智能导航管理器

**用户故事：** 作为用户，我希望系统能自动导航到目标 App 的目标页面，以便数据采集前无需手动操作手机到达指定位置。

#### 验收标准

1. WHEN 收到导航请求时，THE Navigator SHALL 首先查找 Script_Store 中是否存在匹配的导航脚本
2. WHEN 存在有效的导航脚本时，THE Navigator SHALL 按脚本步骤顺序执行导航操作
3. WHEN 不存在匹配的导航脚本时，THE Navigator SHALL 使用 Vision_Client 进行视觉引导的自主探索导航
4. WHEN 自主探索导航成功到达目标页面时，THE Navigator SHALL 将导航步骤自动保存为脚本到 Script_Store
5. IF 导航过程中操作失败或超过最大步骤数限制，THEN THE Navigator SHALL 停止导航并返回失败原因
6. THE Navigator SHALL 在导航前启动目标 App，在导航过程中记录每一步的操作类型和参数

### 需求 7：数据采集策略系统

**用户故事：** 作为用户，我希望系统按照 API 直连 > RPA 复制粘贴 > 截图 OCR 的优先级自动选择采集策略，以便在保证成功率的同时获得最佳采集速度。

#### 验收标准

1. THE Data_Collector SHALL 按照 API 直连、RPA 复制粘贴、RPA 截图 OCR 的优先级顺序尝试各采集策略
2. WHEN 高优先级策略采集失败时，THE Data_Collector SHALL 自动降级到下一优先级策略继续尝试
3. WHEN API 直连策略执行时，THE Collection_Strategy SHALL 通过 HTTP 客户端直接调用已配置的 API 端点获取数据
4. WHEN RPA 复制粘贴策略执行时，THE Collection_Strategy SHALL 导航到目标页面后通过长按、全选、复制操作获取文本数据，再从剪贴板读取
5. WHEN RPA 截图 OCR 策略执行时，THE Collection_Strategy SHALL 导航到目标页面后截图，调用 Vision_Client 提取结构化数据，支持滑动翻页采集多页数据
6. WHEN 采集成功时，THE Data_Collector SHALL 将采集结果标准化为 JSON 格式返回，包含 items 列表和使用的策略名称
7. IF 所有策略均失败，THEN THE Data_Collector SHALL 返回错误响应，包含每个策略的失败原因
8. WHEN 收到采集请求时，THE Data_Collector SHALL 支持通过 forceStrategy 参数强制指定使用某一策略

### 需求 8：脚本仓库

**用户故事：** 作为用户，我希望系统在首次探索成功后自动保存采集脚本，后续相同任务直接复用已保存的脚本，以便大幅提升重复采集的速度。

#### 验收标准

1. THE Script_Store SHALL 以 JSON 文件格式存储采集脚本，每个脚本包含 App 名称、数据类型、策略类型、操作步骤和元数据
2. WHEN 采集任务首次探索成功时，THE Script_Store SHALL 自动保存采集脚本，包含导航步骤和数据提取配置
3. WHEN 收到采集请求时，THE Data_Collector SHALL 优先查找 Script_Store 中匹配的有效脚本并复用
4. THE Script_Store SHALL 支持按 App 名称和数据类型检索匹配的脚本
5. THE Script_Store SHALL 为每个脚本记录元数据，包含创建时间、最后使用时间、使用次数和有效性标记
6. WHEN 脚本执行失败时，THE Script_Store SHALL 将该脚本标记为无效
7. THE Script_Store SHALL 将所有脚本文件存放于 u2-server/scripts/ 目录中
8. THE Script_Store SHALL 支持脚本的序列化和反序列化，将脚本对象与 JSON 文件互相转换

### 需求 9：脚本验证器

**用户故事：** 作为用户，我希望系统每日自动验证已保存脚本的有效性，以便及时发现因 App 更新导致失效的脚本并触发重新探索。

#### 验收标准

1. WHEN 触发脚本验证时，THE Script_Validator SHALL 逐个执行 Script_Store 中所有标记为有效的脚本的导航步骤
2. WHEN 脚本的导航步骤全部执行成功时，THE Script_Validator SHALL 保持该脚本的有效标记不变
3. WHEN 脚本的导航步骤执行失败时，THE Script_Validator SHALL 将该脚本标记为无效并记录失败原因
4. THE Script_Validator SHALL 返回验证报告，包含验证的脚本总数、有效数量、失效数量和每个脚本的验证结果
5. THE U2_Server SHALL 提供 POST /scripts/validate 端点触发脚本验证，接受 deviceId 参数

### 需求 10：Bun/TS 层改造

**用户故事：** 作为开发者，我希望现有 Bun/TS Skill 入口保持向后兼容，同时将设备操作和新增采集指令转发给 Python 服务，以便 OpenClaw Agent 的调用方式不变。

#### 验收标准

1. THE Skill_CLI SHALL 保持现有指令（list_devices、get_screen、execute_action、run_template、run_task、list_templates、screenshot、analyze_screen、smart_task）的接口格式不变
2. WHEN 收到新增指令（collect_data、list_scripts、validate_scripts）时，THE Skill_CLI SHALL 通过 HTTP 将请求转发给 U2_Server 对应的端点
3. THE Skill_CLI SHALL 通过环境变量 U2_SERVER 配置 Python 服务地址，默认值为 http://localhost:9400
4. IF U2_Server 不可达，THEN THE Skill_CLI SHALL 返回错误响应，提示 Python 服务未启动
5. WHEN 转发请求时，THE Skill_CLI SHALL 将 U2_Server 的响应格式转换为现有 SkillResponse 格式（status、message、data）

### 需求 11：新增指令定义

**用户故事：** 作为 OpenClaw 用户，我希望通过新增指令触发数据采集、脚本管理等功能，以便 AI Agent 能够调用智能数据采集能力。

#### 验收标准

1. WHEN 收到 collect_data 指令时，THE Skill_CLI SHALL 将 deviceId、app、dataType、query、forceStrategy 参数转发给 U2_Server 的 POST /collect 端点
2. WHEN 收到 list_scripts 指令时，THE Skill_CLI SHALL 调用 U2_Server 的 GET /scripts 端点并返回所有已保存脚本的摘要列表
3. WHEN 收到 validate_scripts 指令时，THE Skill_CLI SHALL 将 deviceId 参数转发给 U2_Server 的 POST /scripts/validate 端点并返回验证报告
4. THE Skill_CLI SHALL 在 SKILL.md 文件中添加新增指令的自然语言描述，说明 collect_data、list_scripts、validate_scripts 的用途和参数

### 需求 12：部署文档

**用户故事：** 作为开发者，我希望有完整的部署文档覆盖 frp 隧道配置、AutoX.js 安装、uiautomator2 初始化和 uv 环境搭建，以便能够从零开始完成整个系统的部署。

#### 验收标准

1. THE 部署文档 SHALL 包含 uv 安装和 Python 环境初始化的完整步骤
2. THE 部署文档 SHALL 包含 uiautomator2 在云服务器上的初始化步骤，包括通过 ADB SSH 隧道推送 agent 到手机
3. THE 部署文档 SHALL 包含 frp 服务端（云服务器）和客户端（手机端）的配置文件示例和启动命令
4. THE 部署文档 SHALL 包含 AutoX.js 在 Android 手机上的安装和 HTTP 服务启动步骤
5. THE 部署文档 SHALL 包含 U2_Server 的启动命令和后台运行配置
6. THE 部署文档 SHALL 包含日常启动顺序说明，涵盖 SSH 隧道、frp 隧道、Python 服务的启动顺序
7. THE 部署文档 SHALL 包含常见问题排查指南，覆盖设备连接失败、frp 隧道断开、Python 服务启动失败等场景
