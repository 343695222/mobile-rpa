# 需求文档：OpenClaw 移动端 RPA Skill

## 简介

本功能为 OpenClaw 平台实现一个移动端 RPA（机器人流程自动化）Skill，使 OpenClaw AI Agent 能够通过 ADB（Android Debug Bridge）自动化控制 Android 手机。该 Skill 支持屏幕状态感知、自动化交互操作、预定义操作模板，以及通过 OpenClaw 消息指令触发自动化流程。

## 术语表

- **OpenClaw**: 一个 AI Agent 平台，通过 Skill 扩展能力，Skill 以 `SKILL.md` 文件定义
- **Skill**: OpenClaw 的能力扩展单元，包含 `SKILL.md` 描述文件和支撑脚本，存放于 `~/.openclaw/workspace/skills/` 目录
- **SKILL.md**: Skill 的定义文件，包含 YAML frontmatter（name, description, requires, install）和 Markdown 指令说明
- **ADB**: Android Debug Bridge，Android 调试桥接工具，用于与 Android 设备通信
- **Accessibility_Tree**: Android 无障碍树，描述当前屏幕 UI 元素层级结构的数据
- **Operation_Template**: 操作模板，预定义的可复用自动化操作序列，以 JSON 格式存储
- **Template_Engine**: 模板引擎，负责加载、解析、验证和执行操作模板的组件
- **Screen_Parser**: 屏幕解析器，负责通过 ADB 获取并解析 Accessibility Tree 的组件
- **Action_Executor**: 动作执行器，负责将抽象操作指令转换为 ADB 命令并执行的组件
- **RPA_Loop**: RPA 循环，感知-推理-执行的自动化控制循环

## 需求

### 需求 1：Skill 结构与注册

**用户故事：** 作为 OpenClaw 用户，我希望该移动端 RPA 能力以标准 Skill 形式注册到 OpenClaw，以便 AI Agent 能够自动发现和调用该 Skill。

#### 验收标准

1. THE Skill SHALL 包含一个符合 OpenClaw 规范的 `SKILL.md` 文件，其中定义 name、description、requires 和 install 字段
2. WHEN OpenClaw Agent 加载 Skill 目录时，THE Skill SHALL 被正确识别并可供调用
3. THE SKILL.md SHALL 包含清晰的自然语言指令，描述该 Skill 的能力范围和调用方式
4. THE Skill SHALL 将所有文件存放于 `~/.openclaw/workspace/skills/mobile-rpa/` 目录下

### 需求 2：ADB 设备连接与管理

**用户故事：** 作为用户，我希望 Skill 能够通过 ADB 连接和管理 Android 设备，以便对目标手机进行自动化操作。

#### 验收标准

1. WHEN Skill 启动时，THE Action_Executor SHALL 通过 ADB 检测已连接的 Android 设备列表
2. IF 没有检测到已连接设备，THEN THE Action_Executor SHALL 返回明确的错误信息，说明无可用设备
3. WHEN 多个设备连接时，THE Action_Executor SHALL 支持通过设备序列号指定目标设备
4. THE Action_Executor SHALL 在执行操作前验证目标设备的 ADB 连接状态
5. IF 操作执行过程中设备断开连接，THEN THE Action_Executor SHALL 停止当前操作并报告连接丢失错误

### 需求 3：屏幕状态感知

**用户故事：** 作为用户，我希望 Skill 能够读取手机当前屏幕状态，以便 AI Agent 理解屏幕内容并做出决策。

#### 验收标准

1. WHEN 请求屏幕状态时，THE Screen_Parser SHALL 通过 ADB 获取当前屏幕的 Accessibility Tree
2. THE Screen_Parser SHALL 将原始 Accessibility Tree 解析为结构化的 UI 元素列表，包含元素类型、文本内容、坐标位置和可交互状态
3. WHEN 解析 Accessibility Tree 时，THE Screen_Parser SHALL 过滤不可见和不可交互的元素，仅保留有意义的 UI 元素
4. THE Screen_Parser SHALL 为每个可交互元素分配唯一标识符，便于后续操作引用
5. WHEN 连续两次获取屏幕状态时，THE Screen_Parser SHALL 支持计算两次状态之间的差异（diff）
6. IF ADB 获取 Accessibility Tree 失败，THEN THE Screen_Parser SHALL 返回描述性错误信息

### 需求 4：基础操作执行

**用户故事：** 作为用户，我希望 Skill 能够执行基础的手机操作（点击、输入、滑动等），以便实现自动化交互。

#### 验收标准

1. WHEN 收到点击指令时，THE Action_Executor SHALL 通过 ADB 在指定坐标位置执行点击操作
2. WHEN 收到文本输入指令时，THE Action_Executor SHALL 通过 ADB 在当前焦点元素输入指定文本
3. WHEN 收到滑动指令时，THE Action_Executor SHALL 通过 ADB 执行从起点到终点的滑动操作
4. WHEN 收到按键指令时，THE Action_Executor SHALL 通过 ADB 发送指定的按键事件（如返回键、Home 键）
5. WHEN 收到等待指令时，THE Action_Executor SHALL 暂停指定的毫秒数后继续执行
6. THE Action_Executor SHALL 在每次操作执行后返回操作结果状态（成功或失败及原因）
7. IF 操作执行超时，THEN THE Action_Executor SHALL 终止该操作并返回超时错误

### 需求 5：操作模板定义与管理

**用户故事：** 作为用户，我希望能够预定义和封装常用的操作序列为模板，以便快速复用自动化流程。

#### 验收标准

1. THE Template_Engine SHALL 支持以 JSON 格式定义操作模板，包含模板名称、描述、参数定义和操作步骤序列
2. WHEN 加载操作模板时，THE Template_Engine SHALL 验证模板格式的正确性，包括必填字段和步骤结构
3. THE Template_Engine SHALL 支持模板参数化，允许在模板步骤中使用 `{{paramName}}` 占位符引用参数
4. WHEN 执行模板时，THE Template_Engine SHALL 将参数值替换到模板步骤中的占位符位置
5. IF 模板中存在未提供值的必填参数，THEN THE Template_Engine SHALL 拒绝执行并列出缺失的参数
6. THE Template_Engine SHALL 支持从 `templates/` 目录加载所有可用模板
7. WHEN 列出可用模板时，THE Template_Engine SHALL 返回每个模板的名称、描述和所需参数列表
8. THE Template_Engine SHALL 支持模板的序列化和反序列化，将模板对象与 JSON 文件互相转换

### 需求 5b：从自由探索中自动封装模板

**用户故事：** 作为用户，我希望 Skill 在首次自由探索完成任务后，能够自动将执行过的操作步骤封装为可复用的操作模板，以便后续直接调用。

#### 验收标准

1. WHEN 自由探索模式完成一个任务时，THE RPA_Loop SHALL 记录完整的操作历史，包含每一步的操作类型、参数和屏幕状态上下文
2. WHEN 自由探索成功完成后，THE Template_Engine SHALL 支持将操作历史自动转换为操作模板
3. WHEN 从操作历史生成模板时，THE Template_Engine SHALL 识别操作步骤中的可变部分并将其提取为模板参数
4. WHEN 生成模板后，THE Template_Engine SHALL 将模板保存到 `templates/` 目录并赋予用户可读的名称
5. WHEN 用户再次发出相同类型的任务指令时，THE Skill SHALL 优先查找匹配的已封装模板并以模板模式执行

### 需求 6：RPA 自动化循环（双模式）

**用户故事：** 作为用户，我希望 Skill 支持两种执行模式——自由探索模式和模板执行模式，以便首次自由完成任务后自动封装为模板供后续复用。

#### 验收标准

1. WHEN 收到自动化任务且无匹配模板时，THE RPA_Loop SHALL 进入自由探索模式，执行"感知屏幕状态 → 确定下一步操作 → 执行操作"的循环
2. WHEN 收到自动化任务且存在匹配模板时，THE RPA_Loop SHALL 进入模板执行模式，按模板步骤顺序执行操作
3. THE RPA_Loop SHALL 在每次循环中记录当前步骤编号、屏幕状态摘要和执行的操作
4. WHEN 循环步骤数达到预设上限时，THE RPA_Loop SHALL 停止循环并报告未能在限定步骤内完成任务
5. IF 连续三次执行相同操作且屏幕状态未变化，THEN THE RPA_Loop SHALL 检测为卡住状态并尝试替代操作
6. WHEN 自由探索模式成功完成任务时，THE RPA_Loop SHALL 返回成功结果、执行历史记录，并触发模板自动封装流程
7. WHEN 模板执行模式完成时，THE RPA_Loop SHALL 返回执行结果及每个步骤的执行状态

### 需求 7：指令接口与输出格式

**用户故事：** 作为 OpenClaw 用户，我希望通过自然语言指令触发 Skill 的各项功能，并获得结构化的执行结果。

#### 验收标准

1. THE Skill SHALL 支持以下指令类型：设备查询、屏幕获取、单步操作、模板执行、自动化任务
2. WHEN 收到指令时，THE Skill SHALL 以 JSON 格式返回执行结果，包含 status、message 和 data 字段
3. IF 收到无法识别的指令，THEN THE Skill SHALL 返回错误信息并列出支持的指令类型
4. WHEN 执行自动化任务时，THE Skill SHALL 在每个步骤完成后输出中间状态信息
5. THE Skill SHALL 将所有指令执行记录写入日志文件，包含时间戳、指令内容和执行结果
