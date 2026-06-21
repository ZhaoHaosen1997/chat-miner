## Why

P1 AI 调用日志基础设施已就绪（`call_online_chat` 支持 `pipeline`/`group_id`/`task_id` 参数、数据库 `ai_call_logs` 表、前端 `/ai-logs` 页面），但覆盖不全：事件管线缺 `group_id`、前端交互粗糙（独立路由、无分页、无上下文长度字段、任务记录跳页而非就地查看）。补完这些核心缺口，让日志真正可用。

## What Changes

- **事件管线补传 group_id**：`_call_ai_for_events` 已有 `pipeline="event"`，补充 `group_id` 参数传递
- **单窗口事件分析生成任务记录**：`api_analyze_window` 当前无 task record，需创建 `event_window` 类型任务记录，让事件分析可追踪
- **任务记录下拉补事件分析类型**：TaskHistory 类型筛选下拉新增"事件分析"选项（覆盖 `event_window` 和 `event_window_batch`）
- **数据库加 input/output 长度列**：`ai_call_logs` 表新增 `input_chars`（system + user prompt 总字符数）和 `output_chars`（AI 响应字符数），`AILogger.log()` 自动计算写入
- **AI 日志页面移入设置**：从独立路由 `/ai-logs` 迁移为 Settings 页面的第5个 tab "AI日志"
- **后端 API 加分页**：`/api/ai-logs` 支持 `offset` 参数
- **前端加分页控件**：替代当前硬编码 `limit: 50`
- **任务记录弹窗查看 AI 日志**：TaskHistory 中"查看 AI 调用日志"从跳转改为就地弹窗

## Capabilities

### New Capabilities

- `ai-call-logs`: AI 调用日志的完整记录和展示——记录每次 AI 调用（管线、群、模型、输入输出长度、耗时、成功/失败），支持按管线/任务筛选，分页浏览，从任务记录弹窗关联查看

### Modified Capabilities

（无）

## Impact

- **数据库**：`ai_call_logs` 表新增 `input_chars`、`output_chars` 列（ALTER TABLE 兼容旧表）
- **后端**：`services/event_detector.py` 的 `_call_ai_for_events` 签名加 `group_id` 参数；`services/ai_logger.py` 的 `AILogger.log()` 加字段计算；`routers/ai_logs.py` 加 `offset` 分页
- **前端**：`AiCallLogs.vue` 重构为 Settings tab 嵌入组件；`Settings.vue` 新增 tab；`TaskHistory.vue` 新增弹窗；`main.js` 移除 `/ai-logs` 路由
- **路由变更**：`/ai-logs` 路由移除（**BREAKING** 仅对收藏该书签的用户，非 API 层面破坏）
