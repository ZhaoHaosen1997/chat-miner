## Why

v1.18.0 事件探测将 Phase 1（Python 尖峰检测）和 Phase 2（AI 逐窗口分析）捆绑在一个异步任务中，且在 Phase 2 开始前**全局删除**指定时间范围内的旧事件。这导致：任务中途崩溃或取消时，旧事件不可逆丢失、新事件不完整入库；固定 200 条消息窗口无视对话自然边界，一个事件可能被切碎或与无关消息混在一起。v1.18.1 将两步彻底拆分，以"持久化中间状态 + 自适应事件边界 + 队列串行分析"解决数据安全与质量问题。

## What Changes

- **Python 检测拆分独立**：`POST /detect` 只运行 Python 尖峰检测 + 自适应时间间隙切分，产出事件组列表持久化到新表 `event_windows`，秒级完成，不调 AI，不删旧数据
- **自适应事件组切分**：替换固定 200 条窗口为时间间隙自适应切分，使一个事件组 = 一段自然对话 = 一个候选事件，实现与 AI 分析的一对一映射
- **AI 分析拆为独立步骤**：新增 `POST /windows/{id}/analyze` 逐事件组分析，队列串行（替换 3 并发），AI 返回单个事件对象或空，分析完立即入库并标记窗口状态
- **前端两步交互**：检测完成后展示事件组列表（按月分组、时间倒序），每项含 Python 提取的摘要（时间/人数/消息预览），提供"一键分析"和逐条"分析"按钮，分析完自动刷新标记
- **窗口级别数据安全**：重新分析仅删除该窗口之前产出的事件，不再全局删除；旧事件保留至新分析成功
- **BREAKING**：`events` API 响应结构新增 `window_id` 字段；`POST /detect` 返回从 `{task_id}` 变为 `{windows: [...], count: N}`

## Capabilities

### New Capabilities

- `event-window-persistence`: 事件窗口持久化——event_windows 表、CRUD、状态流转（pending/analyzing/analyzed/empty）
- `adaptive-segmentation`: 自适应事件组切分——时间间隙检测、动态阈值、消息数上下界约束，替换固定窗口
- `event-window-analysis`: 逐事件组 AI 分析——单事件输出、队列串行调度、窗口级入库与状态更新
- `event-window-ui`: 前端事件组列表页——按月分组展示、摘要预览、一键分析 + 逐条分析、自动刷新

### Modified Capabilities

- `event-detection`: Phase 1 检测逻辑从"尖峰 + 固定窗口"改为"尖峰 + 自适应切分"；Phase 2 AI 分析从检测任务内联改为独立端点；删除全局 `delete_events_in_range` 调用
- `event-timeline`: 前端事件列表增加"待分析事件组"视图，与已分析事件共存；事件卡片增加 `window_id` 关联

## Impact

- **新增文件**：`routers/event_windows.py`（窗口分析 API）
- **新增数据库表**：`event_windows`
- **修改文件**：`services/event_detector.py`（自适应切分替换固定窗口）、`routers/events.py`（拆分 detect 和分析逻辑）、`models/database.py`（新表 + event_windows CRUD）、`frontend/src/views/Events.vue`（两步交互）、`frontend/src/components/EventTimeline.vue`（待分析视图）、`frontend/src/api/index.js`（新 API）
- **删除**：`routers/events.py` 中 `_run()` 异步任务的 Phase 2 内联循环
- **配置变更**：`EVENT_WINDOW_SIZE`(200)→废弃，新增 `EVENT_MIN_GAP_MINUTES`(15)、`EVENT_MIN_GROUP_SIZE`(10)、`EVENT_MAX_GROUP_SIZE`(500)
