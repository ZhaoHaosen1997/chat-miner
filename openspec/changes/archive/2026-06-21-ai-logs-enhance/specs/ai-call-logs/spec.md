## ADDED Requirements

### Requirement: AI 调用自动记录
所有通过 `call_online_chat` 发起的在线模型调用 SHALL 自动记录到 `ai_call_logs` 表。调用方传入 `pipeline` 时，即触发日志写入。记录内容 MUST 包含：管线标识、群 ID（如有）、模型名、输入字符数、输出字符数、耗时、成功/失败状态。

#### Scenario: 日报管线调用被记录
- **WHEN** 日报管线调用 `call_online_chat(pipeline="daily", group_id=123, ...)` 
- **THEN** `ai_call_logs` 表新增一条记录，pipeline="daily"，group_id=123，input_chars=system+user prompt 总长度，output_chars=响应长度

#### Scenario: 事件管线调用记录含群 ID
- **WHEN** 事件管线调用 `call_online_chat(pipeline="event", group_id=456, ...)`
- **THEN** `ai_call_logs` 表新增一条记录，pipeline="event"，group_id=456

#### Scenario: 未传 pipeline 则不记录
- **WHEN** 调用方未传 `pipeline` 参数
- **THEN** 不写入 `ai_call_logs` 记录

### Requirement: 上下文长度字段
`ai_call_logs` 表 SHALL 包含 `input_chars` 和 `output_chars` 两个整数字段，分别记录单次 AI 调用的输入字符数（system_prompt + user_prompt 总长度）和输出字符数（AI 响应长度），方便用户评估上下文使用情况。

#### Scenario: 日志展示输入输出长度
- **WHEN** 用户查看 AI 调用日志列表
- **THEN** 每条日志显示输入字符数和输出字符数（如 "入 4.2k / 出 1.8k"）

### Requirement: 按任务查看 AI 日志
用户 SHALL 能从任务记录页面查看该任务的所有 AI 调用日志。点击"查看 AI 调用日志"时 MUST 以弹窗方式就地展示，不跳转到独立页面。

#### Scenario: 任务记录弹窗查看 AI 日志
- **WHEN** 用户在任务记录展开某条 AI 分析类任务，点击"查看 AI 调用日志"
- **THEN** 弹窗展示该 task_id 对应的所有 AI 调用日志列表

#### Scenario: 非 AI 任务不显示链接
- **WHEN** 某任务类型不属于 AI 分析类（如 JSON 导入、WeFlow 同步）
- **THEN** 任务详情不显示"查看 AI 调用日志"链接

### Requirement: AI 日志分页浏览
AI 日志 API SHALL 支持 `offset` 分页参数。前端 MUST 提供分页控件（上一页/下一页），默认每页 50 条。

#### Scenario: 分页浏览日志
- **WHEN** 用户在 AI 日志页面点击"下一页"
- **THEN** 加载并显示后续 50 条日志记录

### Requirement: AI 日志作为设置页面 Tab
AI 调用日志 SHALL 作为 Settings 页面的独立 tab "AI日志" 呈现，不再拥有独立路由 `/ai-logs`。

#### Scenario: 切换至 AI 日志 tab
- **WHEN** 用户在设置页面点击"AI日志"tab
- **THEN** 显示 AI 调用日志列表，含筛选栏、分页控件、输入输出长度信息

### Requirement: 事件分析生成任务记录
单窗口事件分析（`/api/groups/{gid}/events/windows/{window_id}/analyze`）SHALL 创建 `event_window` 类型任务记录，记录开始时间、耗时、成功/失败状态，与批量事件分析（`event_window_batch`）一起出现在任务记录页面。

#### Scenario: 单窗口事件分析生成任务
- **WHEN** 用户对某个事件窗口发起 AI 分析
- **THEN** `task_records` 表新增一条 `event_window` 类型记录，分析完成后更新状态

#### Scenario: 任务记录筛选事件分析
- **WHEN** 用户在任务记录页面选择"事件分析"类型筛选
- **THEN** 列表同时显示 `event_window`（单窗口）和 `event_window_batch`（批量）的任务记录
