## 1. 数据库 + Prompt 迁移

- [x] 1.1 `models/database.py` — `_migrate_v1_18_2` 新增 `ALTER TABLE events ADD COLUMN report_json TEXT DEFAULT ''`
- [x] 1.2 `models/database.py` — `insert_events` 函数新增 `report_json` 列写入
- [x] 1.3 `services/event_detector.py` — `_build_event_prompt` 更新 json_instruction，追加 narrative/mood/key_moments/participant_roles/aftermath 等字段
- [x] 1.4 `services/event_detector.py` — `_parse_ai_response` 适配新字段提取（participants 从字符串数组变为对象数组 `[{name, role}]`）
- [x] 1.5 `routers/event_windows.py` — `_save_event_result` 新增 `report_json` 字段写入
- [x] 1.6 **验证**：启动应用确认 migration 执行 → 手动触发一条事件分析 → 数据库检查 `report_json` 列有内容

## 2. 事件详情页 `/event/:eventId`

- [x] 2.1 `frontend/src/views/EventDetail.vue` — 新建：类型自适应 Hero Banner（5 种渐变配色）、headline 大标题、统计条
- [x] 2.2 `frontend/src/views/EventDetail.vue` — 叙事+角色卡双栏：narrative 正文 + participants 角色徽标
- [x] 2.3 `frontend/src/views/EventDetail.vue` — 关键时刻时间线：key_moments 竖向时间轴（dot + description + quote）
- [x] 2.4 `frontend/src/views/EventDetail.vue` — 名场面金句：key_quotes 引用样式（左边框 + 斜体 + 署名）
- [x] 2.5 `frontend/src/views/EventDetail.vue` — FloatingNav 集成：← → 事件翻页，调 `getEvents` 获取相邻事件 ID
- [x] 2.6 `frontend/src/views/EventDetail.vue` — 旧事件降级：report_json 为空时用 description/key_quotes 渲染
- [x] 2.7 `frontend/src/api/index.js` — 新增 `getEventDetail` 适配 report_json 反序列化；新增 `getAdjacentEvents` 获取翻页数据
- [x] 2.8 `routers/events.py` — 新增相邻事件查询逻辑或在现有 `get_event` 中附加 prev/next event_id
- [x] 2.9 `frontend/src/main.js` — 新增路由 `/event/:eventId` → EventDetail，props: true
- [x] 2.10 **验证**：启动应用 → 访问 `/event/:id` → Hero 颜色正确 → 叙事/角色/时间线/金句四个区块均正常渲染 → ← → 翻页流畅

## 3. 仪表盘事件集成

- [x] 3.1 `frontend/src/views/Dashboard.vue` — 新增 events 数据状态（`dashboardEvents`, `dashboardWindows`）
- [x] 3.2 `frontend/src/views/Dashboard.vue` — 最新事件 Hero 卡片（位于日历下方、周报上方），点击跳转 `/event/:id`
- [x] 3.3 `frontend/src/views/Dashboard.vue` — 按月分组事件列表（复用周报月报的展开/收起模式），默认展开最新月份
- [x] 3.4 `frontend/src/views/Dashboard.vue` — 候选窗口行内"分析"按钮：点击 → 调 API → loading → 成功后跳转 `/event/:id`
- [x] 3.5 `frontend/src/views/Dashboard.vue` — "扫描新事件"按钮：调用 `POST /events/detect` → 刷新事件列表
- [x] 3.6 `frontend/src/views/Dashboard.vue` — 空状态：无事件无窗口时显示引导文案
- [x] 3.7 `frontend/src/api/index.js` — 新增 `getEventsForDashboard(gid)` 返回事件+窗口混合列表
- [x] 3.8 **验证**：Dashboard 页面 → 确认事件区域在日历下方 → Hero 卡片可点 → 列表可展开/折叠 → "扫描新事件"可触发

## 4. 导航重构

- [x] 4.1 `frontend/src/components/Layout.vue` — groupNavItems 移除"事件"Tab
- [x] 4.2 `frontend/src/components/Layout.vue` — `reportTypeSwitch` 新增事件层级：daily↔event↔weekly↔monthly↔annual，event↔daily 按日期匹配，event↔weekly 按周匹配
- [x] 4.3 `frontend/src/main.js` — `/events` 路由改为 redirect 到 `/`
- [x] 4.4 `frontend/src/main.js` — 移除 Events 组件 import
- [x] 4.5 **验证**：导航栏无"事件"Tab → ↑↓ 键在日报/事件/周报之间切换正确 → `/events` 自动跳转仪表盘

## 5. 清理

- [x] 5.1 删除 `frontend/src/views/Events.vue`
- [x] 5.2 删除 `frontend/src/components/EventTimeline.vue`
- [x] 5.3 删除 `frontend/src/components/EventWindowCard.vue`
- [x] 5.4 删除 `frontend/src/components/EventCard.vue`
- [x] 5.5 `frontend/src/api/index.js` — 移除不再使用的 `getEventWindows`, `analyzeAllWindows` 等旧 API 函数（保留 `analyzeWindow` 用于候选窗口分析）
- [x] 5.6 **验证**：全量编译无报错 → Dashboard 正常加载 → 事件详情页正常 → 周报/月报/年报正常
