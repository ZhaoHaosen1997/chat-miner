## Context

P1 AI 调用日志系统（`ai_call_logs` 表 + `AILogger` + 前端 AiCallLogs.vue）已上线，但存在三个核心缺口：

1. 事件管线 `_call_ai_for_events` 传了 `pipeline="event"` 但调用方 `_analyze_window_with_ai` 明明有 `group_id` 却没往下传，导致事件日志缺群标识
2. 单窗口事件分析 `api_analyze_window` 没有生成任务记录，事件分析在任务历史中不可追踪
3. 任务记录类型下拉缺少"事件分析"筛选项（已有 `event_window_batch` 批量任务但 UI 不认）
4. 前端独立路由 `/ai-logs` 割裂体验——用户在任务记录看到 AI 日志链接，点击却跳到另一个页面的带参数筛选
5. 日志缺少 input/output 长度字段，无法快速判断 AI 上下文使用量

## Goals / Non-Goals

**Goals:**
- 事件管线的 AI 调用完整记录（补 group_id）
- 单窗口事件分析生成任务记录 + 任务记录下拉补"事件分析"类型
- AI 日志页面整合到设置页，使用体验连贯
- 任务记录弹窗查看 AI 日志
- 日志携带 input/output 字符数，方便评估上下文
- API 分页

**Non-Goals:**
- `_ai_generate`（周/月/年报）、画像、关系判断的日志参数补全（留后续版本）
- JSON 语法高亮（后续）
- 日志导出/搜索功能

## Decisions

### D1: input_chars / output_chars 放在记录时计算，不在查询时计算

**选择**：在 `AILogger.log()` 内部计算 `input_chars = len(system_prompt) + len(user_prompt)`、`output_chars = len(response_raw)`，存入数据库。

**理由**：计算成本几乎为零，存入列后查询直接读，不依赖 prompt 字段的长度函数。同时兼容历史数据（NULL → 显示为 0）。

### D2: AiCallLogs 作为 Settings 子组件而非独立路由

**选择**：删除 `/ai-logs` 路由，`AiCallLogs.vue` 重构为纯组件（接收 props 或通过 inject 获取上下文），由 `Settings.vue` 在 `activeTab === 'aiLogs'` 时渲染。

**理由**：设置页面已是4个 tab 的聚合页，AI 日志与设置侧的"高级选项"关联紧密（日志保留天数就在同一页）。用户在一个页面内切换 tab 比跳路由更流畅。

**替代方案**：保留独立路由但加导航链接。不选，因为用户明确要求移到设置页。

### D3: 任务日志弹窗复用 AiCallLogs 组件逻辑但以独立 Modal 形式

**选择**：`TaskHistory.vue` 中新增一个 Modal，内部嵌入简化的日志列表（`task_id` 固定为当前任务），不支持筛选切换。AiCallLogs 核心逻辑抽取为 composable 或直接在 Modal 内重复请求。

**实际做法**：在 TaskHistory 中新增 data 和 method，Modal 内调用 `getAiCallLogs({task_id: r.id, limit: 100})`，做一个小型内嵌列表。不抽取 composable（过度工程）。

### D4: 数据库兼容旧表

**选择**：`_migrate_db` 中用 `ALTER TABLE ai_call_logs ADD COLUMN` 补两列，默认值 0。SQLite 不支持 `IF NOT EXISTS` 对列，用 try/except 包裹。

**理由**：已部署实例的 `ai_call_logs` 表无这两列，必须迁移。新装实例则 CREATE TABLE 直接包含。

### D5: 单窗口事件分析任务类型命名

**选择**：`event_window` 类型对应单窗口分析，与已有的 `event_window_batch`（批量）区分。两者同属"事件分析"大类，TaskHistory 筛选时合并展示。

**理由**：`event_window` 与已有 `event_window_batch` 的命名风格一致，前端同标签筛选时直观。单窗口分析是同步等 AI 响应的，用 task record 包裹可以记录耗时和失败信息。

## Risks / Trade-offs

- **数据库迁移在启动时执行** → SQLite 的 ALTER TABLE 在已有表上轻量操作，风险低。try/except 兜底重复列。
- **移除 `/ai-logs` 路由** → 如果有人收藏了该 URL，会 404。影响面极小（内部工具，非公开 API）。
- **弹窗内列表不支持分页** → 单任务 AI 调用通常不超过 10 条，limit=100 足够。

## Migration Plan

1. 部署新代码
2. 启动时 `_migrate_db` 自动对已有 `ai_call_logs` 表执行 ALTER TABLE ADD COLUMN
3. 前端路由变更随 JS bundle 更新生效，无需用户操作
4. 无需回滚预案（新列有默认值，不影响已有查询）
