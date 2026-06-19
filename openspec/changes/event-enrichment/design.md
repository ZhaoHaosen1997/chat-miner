## Context

v1.18.1 完成了事件两步拆分（检测→分析），但事件模块仍独立于仪表盘。v1.18.2 将事件融入仪表盘，并参考周报/月报的"沉浸式阅读"模式打造事件详情页——Hero 渐变、关键时刻时间线、AI 故事化叙述。

## Goals / Non-Goals

**Goals:**
- 事件模块嵌入仪表盘（日历下方、周报上方），取消独立 `/events` Tab
- 新事件详情页 `/event/:eventId`：类型自适应 Hero + AI 叙事 + 关键时刻时间线 + 名场面金句 + 左右翻页
- AI Prompt 丰富化：从 6 字段扩展到 10+ 字段（narrative, mood, key_moments, participant_roles, aftermath）
- 候选事件点击→直接触发分析→完成后跳转详情页
- ↑↓ 键盘导航新增事件层级（日报→事件→周报→月报→年报）
- 移除对话原文展示

**Non-Goals:**
- 事件搜索/全文检索
- 事件编辑/手动修改
- 事件分享/导出
- 事件聚合/人物关联图谱

## Decisions

### 1. 事件详情页路由：`/event/:eventId`

**选择**：`/event/:eventId`（单数），参数为 `events` 表主键。

**理由**：与周报 `/weekly/:weekId`、月报 `/monthly/:monthId` 格式一致。`eventId` 即数据库 `events.id`。

### 2. AI Prompt 丰富化：新输出格式

**选择**：AI 返回单个事件对象，扩增至 10+ 字段。

```json
{
  "headline": "关于方案A的最终决议",
  "narrative": "那天下午，张三在群里抛出了方案A...（2-3段故事化叙述）",
  "event_type": "decision",
  "mood": "激烈",
  "mood_emoji": "🔥",
  "participants": [
    {"name": "张三", "role": "主角"},
    {"name": "李四", "role": "反对者"}
  ],
  "key_moments": [
    {"time": "14:23", "description": "张三抛出方案A", "quote": "我觉得这是最优解"}
  ],
  "key_quotes": ["方案A唯一的缺点就是太完美了 — 张三"],
  "aftermath": "全票通过后，李四发了个表情包缓解尴尬...",
  "time_span": {"start": "14:23", "end": "15:45"}
}
```

**理由**：丰富字段直接映射详情页的各个区块（narrative→叙事区、key_moments→时间线、key_quotes→金句区），减少前端拼接。mood 字段未来可用于 Dashboard 的情绪筛选。

### 3. 数据存储：`report_json` TEXT 列

**选择**：在 `events` 表新增 `report_json TEXT DEFAULT ''`，存储完整 AI 返回 JSON。现有字段（title, description, event_type 等）保留作为索引/筛选的冗余字段。

**理由**：与 `daily_reports.report` 列（TEXT 存 JSON）模式一致。结构化字段（event_type, start_time）用于 WHERE/ORDER BY 查询，report_json 用于详情页渲染。

### 4. 仪表盘集成：Hero 卡片 + 列表模式

**选择**：Dashboard 事件区域含 Hero 预览（最新一个已分析事件）和按月分组折叠列表（类似周报/月报列表）。

**理由**：复用 Dashboard 已有的 Latest Weekly/Monthly 卡片设计语言，保持视觉一致。

### 5. 候选事件点击行为

**选择**：点击候选事件列表项 → 调用 `POST /windows/{id}/analyze` → 等待分析完成 → 自动跳转 `/event/:eventId`。

**理由**：用户不需要中间状态页面，一键直达。

### 6. 键盘导航扩展

**选择**：在 `Layout.vue` 的 `reportTypeSwitch` 中插入事件层级：

```
Annual ←→ Monthly ←→ Weekly ←→ Event ←→ Daily
  ↑                                                        ↑
最高                                                    最低
```

↑(W) 向更高聚合度，↓(S) 向更细粒度。

**理由**：事件是"一天内的片段"，比日报（一天）更细，放在日报和周报之间逻辑正确。如果当前在事件详情页，↑ 跳到日报，↓ 跳到周报。

### 7. 配色：事件类型驱动渐变

| 类型 | 渐变 | 氛围 |
|------|------|------|
| decision | `#DC2626 → #EA580C → #F59E0B` | 庄重、权威 |
| discussion | `#4F46E5 → #818CF8 → #A78BFA` | 理性、深度 |
| social | `#E11D48 → #F472B6 → #FBCFE8` | 热烈、亲密 |
| announcement | `#059669 → #34D399 → #6EE7B7` | 新鲜、重要 |
| meme | `#9333EA → #D946EF → #FBBF24` | 荒诞、炸裂 |

## Risks / Trade-offs

- **[R] AI Prompt 变长**：新格式要求更多输出字段 → token 消耗上升 → **Mitigation**：字段均为可选（AI 根据对话内容选择填写），空字段不占 token
- **[R] 旧事件数据不兼容**：已有 events 无 `report_json` → **Mitigation**：详情页检测 `report_json` 为空时降级到旧格式渲染（使用现有 description/participants/key_quotes）
- **[R] Dashboard 内容密度上升**：新增事件区域 → **Mitigation**：默认只显示 Hero 卡片 + 最新 1-2 个月，其余折叠

## Migration Plan

1. 数据库迁移：`ALTER TABLE events ADD COLUMN report_json TEXT DEFAULT ''`
2. 部署后旧事件降级渲染（无 report_json 时用旧字段组合展示）
3. 重新分析旧窗口可生成新格式事件
4. 前端路由：`/events` → 重定向到 `/`（Dashboard）

## Open Questions

- 事件详情页上下键的行为：是"最近事件"还是"同月事件"还是"全部事件按时间序"？→ 按全部事件时间序（与 FloatingNav 的← →一致）
- 候选事件列表在 Dashboard 中是全部展示还是只展示最近的？→ 按月折叠，只展开最新月份
