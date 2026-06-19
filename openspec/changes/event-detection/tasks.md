## 1. 数据库与配置

- [x] 1.1 在 `models/database.py` 的 `init_db()` 中新增 `events` 表（字段见 design.md §5）
- [x] 1.2 在 `config.py` 的 `_SETTINGS_DEFS` 和 `KEY_ATTR_MAP` 中新增事件探测配置项：`event_window_size`(200), `event_window_overlap`(20), `event_ai_concurrency`(3), `event_active_group_threshold`(30), `event_active_peak_absolute`(80), `event_quiet_peak_multiplier`(3)
- [x] 1.3 在 `models/database.py` 新增迁移，INSERT 默认 `prompt_profiles` 行：`analysis_type='event_detection'`, 默认 System Prompt（群聊历史学家+八卦记者+脱口秀段子手风格，见 design.md §8）

## 2. 事件探测核心服务

- [x] 2.1 创建 `services/event_detector.py`，实现 `detect_events(group_id, date_start, date_end)` 主函数
- [x] 2.2 实现 Phase 1 — `_detect_peaks()`：计算小时消息量，判定群活跃度，检测尖峰，合并相邻尖峰为候选时段
- [x] 2.3 实现 `_split_windows()`：将候选时段按窗口大小切分（含重叠），处理不足一个窗口的边界情况
- [x] 2.4 实现 `_build_event_prompt()`：从 `get_default_prompt('event_detection')` 获取 System Prompt（无 DB 配置时用硬编码 fallback），User Prompt 为对话原文 `[HH:MM] 发送者: 内容` 格式 + 群名
- [x] 2.5 实现 Phase 2 — `_analyze_windows()`：asyncio.Semaphore 限流并发调用 AI，解析 JSON 返回
- [x] 2.6 实现 Phase 3 — `_post_process()`：跨窗口事件去重合并（时间范围重叠 + 标题相似度），成员名→ID 解析
- [x] 2.7 实现 `_classify_group_activity()`：根据日均小时消息量判定活跃/安静群

## 3. 后端 API 路由

- [x] 3.1 创建 `routers/events.py`，注册路由到 `main.py`
- [x] 3.2 `POST /api/groups/{id}/events/detect`：接收 `{date_start, date_end}`，创建异步任务，返回 `task_id`
- [x] 3.3 `GET /api/groups/{id}/events`：查询事件列表，支持 `type`/`date_from`/`date_to` 筛选，按 `start_time` 倒序
- [x] 3.4 `GET /api/groups/{id}/events/{event_id}`：返回事件详情 + 关联的原始消息上下文

## 4. 前端 API 层

- [x] 4.1 在 `frontend/src/api/index.js` 中新增 `detectEvents(groupId, dateStart, dateEnd)`、`getEvents(groupId, params)`、`getEventDetail(groupId, eventId)` 三个 API 函数

## 5. 前端事件时间轴页面

- [x] 5.1 创建 `frontend/src/views/Events.vue`：主页面框架（时间范围选择器 + 开始分析按钮 + 类型筛选栏 + 时间轴容器 + 空状态/加载状态/错误状态）
- [x] 5.2 创建 `frontend/src/components/EventTimeline.vue`：按月份分组渲染事件卡列表
- [x] 5.3 创建 `frontend/src/components/EventCard.vue`：单个事件卡片（类型图标、标题、描述、参与成员、关键金句、时间跨度）
- [x] 5.4 实现类型筛选功能（全部/决策/讨论/社交/公告/梗）
- [x] 5.5 实现"查看完整对话"功能（弹窗或展开显示事件关联的原始消息）
- [x] 5.6 集成异步任务状态轮询（复用现有 `activeTaskId` 机制，任务完成后自动刷新事件列表）

## 6. 路由与导航

- [x] 6.1 在 `frontend/src/main.js` 中新增 `/events` 路由映射到 `Events.vue`
- [x] 6.2 在 `frontend/src/App.vue` 导航栏中新增"事件"入口（使用 `Clock` Lucide 图标）

## 7. 报告与画像集成

- [x] 7.1 在 `WeeklyReport.vue` 底部新增"📅 本周事件"区块，调用 `/api/groups/{id}/events` 按周范围筛选展示
- [x] 7.2 在 `MonthlyReport.vue` 底部新增"📅 本月事件回顾"区块
- [x] 7.3 在 `AnnualReport.vue` 底部新增"📅 年度事件"区块（取消息数最多的 Top 10）
- [x] 7.4 在 `PortraitDetail.vue` 新增"参与的关键事件"区块，筛选该成员参与的事件并按时间排列

## 8. 高级设置 UI

- [x] 8.1 在 `frontend/src/views/Settings.vue` 的"高级设置"区域新增事件探测配置组：AI并发数、窗口消息数、窗口重叠数、活跃群判定阈值、活跃群绝对阈值、安静群倍数阈值
- [x] 8.2 在 Prompt 配置（prompt_profiles 管理界面）中支持 `event_detection` 类型的 System Prompt 编辑，与其他分析类型并列
