## ADDED Requirements

### Requirement: 设置按钮全局可见

系统 SHALL 在 Header 导航栏中始终渲染设置按钮，无论是否选择了群。

#### Scenario: 无群时设置按钮可见
- **WHEN** 用户未选择任何群（currentGroup 为 null）
- **THEN** Header 中仍显示设置按钮，用户可点击进入设置页面
- **AND** 设置按钮始终存在于 DOM 中，不因 currentGroup 变化而销毁重建

#### Scenario: 有群时导航不变
- **WHEN** 用户选择了群
- **THEN** Header 导航布局与当前版本一致：仪表盘、群友画像、群鱼塘、设置

### Requirement: 首次运行引导

系统 SHALL 在检测到所有在线模型的 api_key 均为空时，自动跳转到设置页面，并展示引导提示。

#### Scenario: 首次运行自动跳转
- **WHEN** 应用启动且所有 model_configs 中 model_type='online' 的记录 api_key 均为空
- **THEN** 系统自动跳转到 `/#/settings`
- **AND** 基础设置 Tab 顶部展示引导提示"请先配置在线 AI 模型，选择服务商并填入 API Key"

#### Scenario: 已有配置时不跳转
- **WHEN** 存在至少一条 api_key 非空的在线模型配置
- **THEN** 系统正常进入首页，不自动跳转

### Requirement: Provider 预设

基础设置"在线模型"卡片 SHALL 提供服务商选择器，包含 DeepSeek、SenseNova、自定义三个选项。选择服务商后自动填入端点 URL 和默认模型名。

#### Scenario: 选择 DeepSeek
- **WHEN** 用户选择服务商为 DeepSeek
- **THEN** 端点自动填入 `https://api.deepseek.com/v1/chat/completions`
- **AND** 模型名下拉可选 `deepseek-v4-flash`（默认）、`deepseek-v4-pro`

#### Scenario: 选择 SenseNova
- **WHEN** 用户选择服务商为 SenseNova
- **THEN** 端点自动填入 `https://token.sensenova.cn/v1/chat/completions`
- **AND** 模型名下拉可选 `deepseek-v4-flash`（默认）、`sensenova-6.7-flash-lite`

#### Scenario: 选择自定义
- **WHEN** 用户选择服务商为"自定义"
- **THEN** 端点和模型名输入框清空，允许用户自由填写

### Requirement: 基础设置页精简

基础设置 Tab SHALL 仅包含两个卡片：默认群组、在线模型。移除本地模型列表、AI 模型分配、添加模型按钮。

#### Scenario: 仅显示两个卡片
- **WHEN** 用户进入基础设置 Tab
- **THEN** 页面展示"默认群组"和"在线模型"两个卡片，不显示其他内容

#### Scenario: 在线模型卡片默认展开
- **WHEN** 用户进入基础设置 Tab
- **THEN** 在线模型卡片的所有字段（服务商、端点、模型名、API Key、测试连接）默认可见，无需点击展开

#### Scenario: 编辑后保存
- **WHEN** 用户修改在线模型的任意字段并失焦
- **THEN** 系统调用 updateModelConfig 即时保存
- **AND** 该模型的修改同步反映在高级选项的"在线模型配置"列表中

#### Scenario: 基础设置编辑的是默认在线模型
- **WHEN** 用户进入基础设置的在线模型卡片
- **THEN** 卡片展示 `model_configs` 表中 `is_default=1` 的 online 模型
- **AND** 若无此类模型则自动创建一条空记录并标记为默认

### Requirement: 在线模型多配置管理

高级选项 Tab SHALL 包含"在线模型配置"卡片，列出所有在线模型并支持 CRUD 操作。`is_default=1` 的模型标注 `[默认]`，与基础设置的"在线模型"是同一数据源。

#### Scenario: 在线模型列表展示
- **WHEN** 用户进入高级选项 Tab
- **THEN** "在线模型配置"卡片列出所有 `model_type='online'` 的模型，默认模型标注 `[默认]`

#### Scenario: 添加在线模型
- **WHEN** 用户点击"添加"按钮
- **THEN** 弹出添加表单（类型预填为"在线"），支持 Provider 预设（DeepSeek/SenseNova/自定义）

#### Scenario: 删除非默认模型
- **WHEN** 用户删除一个非默认的在线模型
- **THEN** 删除成功，列表刷新

#### Scenario: 保护默认模型
- **WHEN** 用户尝试删除 `is_default=1` 的在线模型
- **THEN** 系统提示"默认模型不可删除，请先设置其他模型为默认"

### Requirement: 本地模型管理迁入高级选项

高级选项 Tab SHALL 包含"本地大模型"设置区域（全局开关 + 服务地址 + 降级模型名）和"本地模型配置"卡片（列表 CRUD + 添加按钮）。

#### Scenario: 本地模型 CRUD 在高级选项中
- **WHEN** 用户进入高级选项 Tab
- **THEN** 页面展示"本地大模型"开关区域和"本地模型配置"列表
- **AND** 用户可添加、编辑、删除、测试连接、设为默认

#### Scenario: AI 模型分配列出所有模型
- **WHEN** 用户进入高级选项 Tab 的 AI 模型分配区域
- **THEN** 每日分析和画像分析的下拉框列出所有已配置的模型（在线和本地），按类型分组，标注默认
- **AND** 用户可选择具体某个模型，而非仅选择类型

### Requirement: 模型选择兜底链

系统 SHALL 按以下优先级选择分析模型：用户指定 model_id → 在线默认（is_default=1 的 online）→ 本地默认（is_default=1 的 local，需 local_llm_enabled=true）→ 本地降级模型（local_llm_fallback_model）。

#### Scenario: 未指定模型时使用在线默认
- **WHEN** 用户发起分析任务但未指定 model_id
- **THEN** 系统使用 `is_default=1` 的 online 模型
- **AND** 若在线模型失败且 local_llm_enabled=true，降级到本地默认
- **AND** 若 local_llm_enabled=false，返回错误不降级

### Requirement: 高级选项布局顺序

高级选项卡片 SHALL 按以下顺序排列：本地大模型 → 在线模型配置 → 本地模型配置 → AI 模型分配 → 管道执行参数 → 在线模型超时与重试 → 报告生成参数 → 周期报告阈值 → GPU 分布式锁 → 过滤词管理 → 其他设置。

### Requirement: 任务记录无群时显示全部

任务记录页面 SHALL 在未选择群时展示所有群的任务记录，选择群后过滤为当前群。

#### Scenario: 无群时显示全部
- **WHEN** 用户未选择群且进入任务记录 Tab
- **THEN** 展示所有群的历史任务记录

#### Scenario: 有群时过滤当前群
- **WHEN** 用户选择了群且进入任务记录 Tab
- **THEN** 仅展示当前群的任务记录（行为与当前版本一致）
