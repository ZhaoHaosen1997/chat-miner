## ADDED Requirements

### Requirement: PipelineContext 构造绑定
PipelineContext 对象在构造时 SHALL 绑定 `pipeline`（管线标识）、`group_id`（群 ID）、`group_name`（群名称）、`model_config`（模型配置）。后续所有操作自动携带这些上下文，调用方无需重复传递。

#### Scenario: 构造周报上下文
- **WHEN** 调用 `PipelineContext("weekly", group_id=123, group_name="技术群", model_config=cfg)`
- **THEN** ctx 内部保存 pipeline="weekly", group_id=123, group_name="技术群", model_config=cfg

### Requirement: start_task 统一创建任务记录
`start_task(task_type, target)` SHALL 调用 `task_manager.create()` 创建内存任务，并返回 task 对象。管线通过 `ctx.task` 访问当前任务。

#### Scenario: 开始周报生成任务
- **WHEN** 调用 `ctx.start_task("generate_weekly", "2026-W25")`
- **THEN** `task_manager` 中新增一个类型为 "generate_weekly" 的任务，`ctx.task.task_id` 可访问

### Requirement: finish_task 自动持久化
`finish_task(success, error)` SHALL 调用 `task.finish()` 并自动调用 `save_task_record()` 写入数据库，使用 ctx 中绑定的 pipeline/group_id/group_name 填充记录字段。

#### Scenario: 成功完成任务
- **WHEN** 调用 `ctx.finish_task(success=True)`
- **THEN** `task_records` 表新增一条记录，status="done"，包含 task_id、group_id、task_type、耗时等信息

### Requirement: call_ai 自动记录日志
`call_ai(system_prompt, user_prompt, **kwargs)` SHALL 调用 `call_online_chat`，并自动传入 `pipeline`、`group_id`、`task_id`（取自 ctx）。调用方无需也不应手写这些日志参数。

#### Scenario: 周报 AI 调用自动日志
- **WHEN** 调用 `ctx.call_ai(system_prompt, user_prompt, temperature=0.8)`
- **THEN** `call_online_chat` 收到 `pipeline="weekly"`, `group_id=123`, `task_id=<当前task.task_id>`
- **AND** `ai_call_logs` 表新增一条记录，pipeline/group_id/task_id 均正确填充

#### Scenario: 无需手写日志参数
- **WHEN** 管线代码调用 `ctx.call_ai(sp, up)`
- **THEN** 代码中不出现 `pipeline=`、`group_id=`、`task_id=` 关键字

### Requirement: 不绑定任务也可调用 AI
PipelineContext SHALL 支持在未调用 `start_task()` 的情况下直接使用 `call_ai()`。此时 `task_id` 传空值，仅记录 pipeline 和 group_id。

#### Scenario: 健康检查类调用
- **WHEN** 构造 ctx 后直接调用 `ctx.call_ai(sp, up)`
- **THEN** AI 日志中 task_id 为空，pipeline 和 group_id 正常记录
