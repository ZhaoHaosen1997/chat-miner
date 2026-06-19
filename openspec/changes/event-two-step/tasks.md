## 1. 数据库迁移：event_windows 表 + events 表扩展

- [x] 1.1 `models/database.py` — 在 `init_db()` 中新增 `event_windows` 表（id, group_id, start_time, end_time, message_count, status, event_count, summary_json, event_id, created_at, analyzed_at），含索引 `idx_event_windows_group_time` 和 `idx_event_windows_group_status`
- [x] 1.2 `models/database.py` — 在 `_migrate_db()` 中新增 `ALTER TABLE events ADD COLUMN window_id INTEGER` 迁移逻辑
- [x] 1.3 `models/database.py` — 新增 CRUD 函数：`insert_windows()`, `get_windows()`, `update_window_status()`, `delete_windows_by_group()`, `get_window()`, `get_pending_windows_count()`
- [x] 1.4 **验证**：启动应用，确认 `event_windows` 表和 `events.window_id` 列自动创建，已有 events 数据未受影响

## 2. 自适应事件组切分：替换固定窗口

- [x] 2.1 `services/event_detector.py` — 新增 `_segment_by_time_gaps(msgs)` 函数：计算时间间隙、动态阈值（max(15min, min(P75×1.5, 60min))）、在超阈值处切分
- [x] 2.2 `services/event_detector.py` — 新增 `_post_process_groups(groups)` 函数：合并 < 10 条的小组、切分 > 500 条的大组（最小 50 条）
- [x] 2.3 `services/event_detector.py` — 新增 `_extract_group_summary(window_msgs)` 函数：提取时间范围、消息数、Top 发言者、消息预览（前 3-5 条）、时段分布
- [x] 2.4 `services/event_detector.py` — 修改 `find_candidate_windows()`：调用自适应切分 + 摘要提取，返回 `list[dict]` 格式 `[{messages, summary, start_time, end_time, message_count}]`（不再返回原始消息窗口列表）
- [x] 2.5 `config.py` — 新增配置项 `EVENT_MIN_GAP_MINUTES`(15), `EVENT_MIN_GROUP_SIZE`(10), `EVENT_MAX_GROUP_SIZE`(500)；`_SETTINGS_DEFS` 和 `KEY_ATTR_MAP` 同步更新
- [x] 2.6 **验证**：使用 test-group 数据，断点调试 `find_candidate_windows()` 输出，检查切分边界是否合理、摘要是否正确提取

## 3. 后端 API：事件窗口分析端点 + 检测端点改造

- [x] 3.1 `routers/event_windows.py` — 新建文件，创建 APIRouter(prefix="/api/groups/{group_id}/events/windows")
- [x] 3.2 `routers/event_windows.py` — `GET /` 获取窗口列表（支持 `?status=pending|analyzed|empty` 筛选），返回 `{code, data: [windows]}`
- [x] 3.3 `routers/event_windows.py` — `POST /{window_id}/analyze` 分析单个窗口：加载窗口消息 → 构建 Prompt → 调 AI → 解析单事件对象/null → 插入 events + 更新窗口状态。如果窗口已有 event_id，先删除旧事件
- [x] 3.4 `routers/event_windows.py` — `POST /analyze-all` 一键分析：获取所有 pending 窗口 → 后台 `asyncio.create_task` 串行逐个调用 analyze 逻辑 → 复用 `task_manager` 推送进度
- [x] 3.5 `services/event_detector.py` — 修改 `analyze_single_window()`：改为接收 event_window 字典而非原始消息列表；修改 `_build_event_prompt()`：Prompt 改为单事件输出格式（`{title, description, ...}` 或 null）
- [x] 3.6 `services/event_detector.py` — 修改 `_parse_ai_response()`：支持解析单个事件对象（新格式）和数组第一个元素（向后兼容旧 AI 行为）
- [x] 3.7 `routers/events.py` — 修改 `POST /detect`：移除 Phase 2 AI 分析循环（`_run()` 函数中的 `for window in windows` 部分和 `delete_events_in_range` 调用），改为调用 `find_candidate_windows()` + `insert_windows()` + 返回 `{windows: [...], count: N}`
- [x] 3.8 `routers/events.py` — 移除不再使用的 import（`analyze_single_window`, `is_window_analyzed`, `insert_events_incremental`, `delete_events_in_range`）
- [x] 3.9 `main.py` — 注册 `event_windows` router
- [x] 3.10 **验证**：通过 Swagger UI 测试完整流程 — POST /detect 返回窗口列表 → GET /windows 确认持久化 → POST /windows/{id}/analyze 确认分析入库 → 验证 window_id 关联正确

## 4. 前端：两步交互 + 事件组列表

- [x] 4.1 `frontend/src/api/index.js` — 新增 `getEventWindows()`, `analyzeWindow()`, `analyzeAllWindows()` API 函数
- [x] 4.2 `frontend/src/components/EventWindowCard.vue` — 新建组件：展示窗口摘要（时间、消息数、Top 发言者、消息预览）、状态徽标（pending/analyzing/analyzed/empty）、"分析"按钮（含 loading 态）
- [x] 4.3 `frontend/src/views/Events.vue` — 重构：检测完成后展示窗口列表（复用按月分组逻辑），"一键分析"按钮置于列表顶部，只在有待处理窗口时显示
- [x] 4.4 `frontend/src/views/Events.vue` — "一键分析"逻辑：串行调用 `analyzeWindow()`（前端轮询或用 analyze-all 端点），显示进度 `(N/M)`，完成后自动刷新窗口状态和事件列表
- [x] 4.5 `frontend/src/views/Events.vue` — 逐条分析逻辑：点击窗口卡的"分析"按钮 → 调用 `analyzeWindow(windowId)` → 按钮变 loading → 完成后自动刷新该卡片状态
- [x] 4.6 `frontend/src/components/EventTimeline.vue` — 支持同时展示窗口卡片和事件卡片（混合列表按时间排序）
- [x] 4.7 **验证**：前端完整交互流程 — 选择时间范围 → 点击"开始分析" → 窗口列表展示 → 点击单条"分析"确认事件生成 → 点击"一键分析"确认串行处理 → 确认已分析事件出现在时间轴中

## 5. 集成收尾：配置迁移 + 代码清理

- [x] 5.1 `models/database.py` — 在 `_migrate_db()` 中新增迁移：将 `EVENT_WINDOW_SIZE`/`EVENT_WINDOW_OVERLAP` 旧配置标记为 deprecated（不清除，仅忽略读取）
- [x] 5.2 `services/event_detector.py` — 移除 `_split_into_windows()` 函数（已被自适应切分替换）
- [x] 5.3 `services/event_detector.py` — 移除 `is_window_analyzed()` 函数（状态管理已迁移到 event_windows 表）
- [x] 5.4 `services/event_detector.py` — 移除 `insert_events_incremental()` 函数（入库逻辑移到 router 层，窗口级管理）
- [x] 5.5 全量回归：运行 `python -m uvicorn main:app --host 0.0.0.0 --port 28856`，验证日报分析、周报、月报、画像事件引用均不受影响
- [x] 5.6 **验证**：使用 test-group 完整跑通 — 导入新数据 → 事件检测 → 逐条分析 → 一键分析 → 查看周报引用 → 确认无异常
