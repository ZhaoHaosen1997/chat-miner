## Why

当前周报、月报、年报的数据来源是 Python 统计预处理后的碎片化摘要——AI 只看到"发言 123 条、情绪分 0.7、Top 关键词"，看不到完整对话上下文。这让报告缺乏"事件叙事"能力：系统知道某天大家聊了很多，但不知道"小明宣布拿到 offer，大家起哄让请客，最后决定周五吃火锅"这样的完整故事。事件探测功能填补这个空白，并且事件数据可以反哺画像和各类报告。

## What Changes

- **新增事件探测后端服务**：Python 扫描消息量尖峰找出候选时段 → 切分为固定大小消息窗口 → 调用 AI 从完整对话上下文中识别事件 → 去重合并后存入数据库
- **新增事件时间轴前端页面** (`/events`)：按时间排列事件卡片，支持按类型筛选，可查看事件关联的对话原文
- **事件数据反哺现有模块**：周报/月报/年报页面底部引用对应时段的事件，群友画像展示成员参与的事件列表
- **AI 并发限流**：asyncio.Semaphore 控制同时调用数，默认 3，放入高级设置可热调整
- **可配置参数**：窗口大小、重叠量、并发数、活跃群判定阈值等均放入 `app_settings` 高级设置
- **纯手动触发**：用户选择时间范围后点击"开始分析"，不自动运行，不自动更新

## Capabilities

### New Capabilities

- `event-detection`: 事件探测核心引擎——消息量尖峰检测、固定窗口切分、AI 并发分析、事件去重合并、数据库存储与查询
- `event-timeline`: 前端事件时间轴页面——按时间排列的事件卡、类型筛选、对话原文查看、时间范围选择
- `event-report-integration`: 事件数据反哺——周报/月报/年报页面引用事件、群友画像展示参与事件

### Modified Capabilities

（无——所有现有功能保持不变，事件功能为纯新增）

## Impact

- **新增文件**：`services/event_detector.py`、`frontend/src/views/Events.vue`、`frontend/src/components/EventTimeline.vue`
- **新增 API**：`POST /api/groups/{id}/events/detect`（触发分析）、`GET /api/groups/{id}/events`（事件列表）、`GET /api/groups/{id}/events/{event_id}`（事件详情）
- **新增数据库表**：`events`
- **修改文件**：`models/database.py`（新表）、`routers/report.py`（事件引用）、`routers/portrait.py`（事件参与）、`config.py` / `app_settings`（可配置参数）、`frontend/src/main.js`（新路由）、`frontend/src/api/index.js`（新 API）、周报/月报/年报/画像 Vue 组件（事件引用展示）
- **依赖**：无新增第三方依赖，复用现有 `online_model.py`、`parser.py`、`stats_engine.py`
