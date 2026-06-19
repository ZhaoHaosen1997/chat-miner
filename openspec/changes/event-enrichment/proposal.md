## Why

v1.18.1 将事件探测拆分为两步，解决了数据安全问题，但事件模块仍以独立 Tab 页存在，与仪表盘割裂；事件详情只有卡片摘要，缺乏类似周报/月报那种"翻开即沉浸"的阅读体验。v1.18.2 将事件融入仪表盘（类比周报月报的位置），并打造有叙事张力的单事件详情页——Hero 渐变、关键时刻时间线、AI 故事化叙述——让事件从"功能"升维为"内容"。

## What Changes

- **仪表盘集成事件区域**：日历热力图下方、周报列表上方，新增"事件时间轴"卡片区块（Hero 预览 + 按月分组列表 + "扫描新事件"按钮）
- **新事件详情页 `/event/:eventId`**：类型自适应 Hero Banner、AI 叙事+角色卡双栏、关键时刻时间线、名场面金句，FloatingNav 左右翻页
- **事件分析丰富化**：AI Prompt 输出从 6 字段扩展到 10+ 字段（narrative, mood, key_moments, participant_roles, aftermath 等）
- **取消独立事件 Tab**：导航栏移除"事件"，`/events` 路由删除
- **键盘导航扩展**：↑↓ 切换报表类别新增事件层级（日报→事件→周报→月报→年报），←→ 事件翻页
- **BREAKING**：`/events` 路由移除；`events` 表新增 `report_json TEXT` 列；AI 事件分析 Prompt 输出格式变更

## Capabilities

### New Capabilities

- `event-detail-page`: 单事件详情页——Hero Banner（类型渐变）、AI 叙事+角色卡、关键时刻时间线、名场面金句、FloatingNav 翻页
- `event-dashboard-integration`: 仪表盘事件区域——Hero 预览卡片、按月分组列表、扫描按钮、点击跳转详情
- `event-prompt-enrichment`: AI 事件分析 Prompt 丰富化——narrative/mood/key_moments/participant_roles/aftermath 等新字段
- `event-keyboard-nav`: 键盘导航事件层级——↑↓ 在日报→事件→周报→月报→年报间切换，←→ 事件翻页

### Modified Capabilities

- `event-window-ui`: 候选事件卡片点击行为改为直接触发分析→跳转详情页；移除独立的"已分析事件"摘要列表
- `event-detection`: `events` 表新增 `report_json` 列；`_build_event_prompt` 和 `_parse_ai_response` 适配新 Prompt 输出格式
- `event-timeline`: `/events` 路由和独立事件 Tab 页移除，功能迁移至 Dashboard + `/event/:eventId`

## Impact

- **新增文件**：`frontend/src/views/EventDetail.vue`（事件详情页）、`frontend/src/components/EventHero.vue`（Hero Banner）、`frontend/src/components/EventDashboard.vue`（仪表盘事件区域）
- **修改文件**：`frontend/src/views/Dashboard.vue`（嵌入事件区域）、`frontend/src/views/Events.vue`（移除或重定向）、`frontend/src/main.js`（路由变更）、`frontend/src/components/Layout.vue`（移除事件Tab、键盘导航新增事件层级）、`services/event_detector.py`（Prompt 丰富化）、`models/database.py`（report_json 列）、`routers/event_windows.py`（适配新格式）
- **删除**：`/events` 路由、`frontend/src/components/EventTimeline.vue`（不再需要独立的已分析事件列表）、`frontend/src/components/EventCard.vue`（被 EventDetail 替代）
- **数据库迁移**：`ALTER TABLE events ADD COLUMN report_json TEXT DEFAULT ''`
