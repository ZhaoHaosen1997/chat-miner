## Context

Chat-Miner 当前报告体系（日报/周报/月报/年报/画像）走的是 "Python 统计 → 结构化摘要 → AI 润色" 管线。AI 收到的输入是统计数字和采样片段，不是完整的对话上下文。这让 AI 能产出统计结论（"本周发言 1200 条，情绪 0.7"）但无法产出叙事（"小明宣布拿到 offer，大家起哄请客"）。

事件探测作为报告体系的新维度，核心差异是：**给 AI 完整对话上下文，让 AI 自己理解和叙述发生了什么**。

项目设计原则 "Python 做统计，AI 做总结" 在事件探测中的体现是："Python 做检测（找候选窗口），AI 做叙事（从完整上下文识别事件）"。

## Goals / Non-Goals

**Goals:**

- 提供纯手动触发的事件探测，用户选择时间范围后启动分析
- Python 基于消息量尖峰定位候选事件时段
- AI 在固定大小（~200 条）的消息窗口中识别 0-N 个事件
- 按时间轴展示事件列表，支持按类型筛选
- 事件数据反哺周报/月报/年报/画像页面
- 所有关键参数可配置（高级设置）

**Non-Goals:**

- 自动/定时事件分析（纯手动）
- 实时事件检测（消息导入时不自动触发）
- 事件重要性评分（AI 不好判断，去掉）
- 个人级别事件（事件仅群级别）
- 修改现有报告生成流程（事件独立生成，仅在展示层引用）

## Decisions

### 1. 事件发现策略：消息量尖峰检测 + AI 叙事

**选择**：Python 统计消息量尖峰 → 形成候选窗口 → AI 在窗口内识别事件

**替代方案**：
- 纯 AI 分段：把一天对话全给 AI 让它自己找事件。问题是 prompt 长度不可控，活跃群一天 500+ 条消息，token 消耗巨大。
- 话题聚类分段：用 embedding 做语义分段。问题是需要额外依赖和计算，且群聊话题切换模糊，边界难定。
- 固定时间窗口：按小时切分。问题是可能把事件切碎（一个事件跨两个窗口）。

**理由**：尖峰检测计算成本极低（遍历统计即可），能够有效缩小 AI 需要处理的范围。AI 拿到的是完整对话上下文，判断"有没有事件"的能力远超纯统计方法。

### 2. 窗口大小：固定消息数而非固定时间

**选择**：每个窗口最多 200 条消息，相邻窗口重叠 20 条

**替代方案**：
- 固定时间窗口（如 2 小时一段）：活跃群窗口可能塞满 300+ 条，安静群可能只有 5 条，prompt 长度剧烈波动。
- 固定 token 数：更精确但需要在切分时做 token 计数，增加复杂度，200 条中文消息大约 4K-6K tokens 在安全范围内。

**理由**：固定消息数保证每次 AI 调用的 prompt 长度可预测。DeepSeek V4 Flash 有 128K 上下文窗口，200 条消息约 6K tokens，留足余量。重叠 20 条（10%）解决事件跨窗口边界的问题。

### 3. 活跃群判定：双阈值策略

**选择**：先判定群属性（活跃/安静），再应用不同的尖峰检测参数

```
判定: avg_hourly_msgs >= 30 → 活跃群
活跃群: 30分钟窗口内 >= 80 条 → 尖峰（绝对阈值）
安静群: 小时量 > 日均小时量 × 3 → 尖峰（相对阈值）
```

**替代方案**：
- 单一绝对阈值：活跃群可能基线就很高，绝对阈值失效。
- 单一相对阈值：安静群可能 5 条就算 10 倍，误判率高。
- Z-score 等统计方法：更精确但复杂，对非正态分布的消息量数据不一定适用。

**理由**：双阈值策略适配不同活跃度的群。参数均可配置，用户可根据实际情况调整。

### 4. 并发控制：asyncio.Semaphore

**选择**：在 `online_model.py` 调用层加 `asyncio.Semaphore(ai_concurrency)`，默认并发=3

**替代方案**：
- 无并发（串行）：太慢，50 个窗口每个 3 秒要 150 秒。
- 全并发：可能触发 API 限频。
- 外部任务队列（Celery/Redis）：没有必要引入额外依赖。

**理由**：Semaphore 是 Python 标准库原语，零依赖，精确控制并发。并发数放入 `app_settings` 可热调整，兼顾不同 API 的限频策略。

### 5. 数据模型：独立 events 表

**选择**：新建 `events` 表，而非嵌入报告 JSON

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL CHECK(event_type IN ('decision','discussion','social','announcement','meme')),
    participant_ids TEXT,        -- JSON array of member IDs
    key_quotes TEXT,             -- JSON array of strings
    start_time TEXT NOT NULL,    -- ISO datetime
    end_time TEXT NOT NULL,
    message_start_idx INTEGER,   -- index into ParsedChat.messages
    message_end_idx INTEGER,
    message_count INTEGER,
    ai_model_used TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (group_id) REFERENCES chat_groups(id)
);
```

**替代方案**：
- 嵌入 `periodic_reports` JSON 中：事件是独立概念，不应绑定特定报告。且事件可跨周期引用。
- 复用现有 `analysis_log` 表：表结构不适配，`analysis_log` 是任务审计表。

**理由**：独立表便于查询（按时间范围、按类型、按参与成员）、便于反哺其他模块、便于后续版本演进。`participant_ids` 和 `key_quotes` 用 JSON 数组字符串存储，与现有 `member_portraits.portrait_json` 的存储模式一致。

### 6. API 设计

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/groups/{id}/events` | GET | 事件列表，支持 `?type=decision&date_from=2025-03-01&date_to=2025-06-19` |
| `/api/groups/{id}/events/{event_id}` | GET | 单事件详情 + 上下文消息 |
| `/api/groups/{id}/events/detect` | POST | 触发事件探测（异步任务），body: `{date_start, date_end}` |

**设计选择**：
- `detect` 返回 `task_id`，和现有的 `POST /weekly/generate` 模式一致，前端用 `activeTaskId` 轮询
- `GET /events` 不分页——3 个月聊天可能只有 11 个事件，全量返回即可
- 事件详情包含原始消息上下文，便于"查看完整对话"

### 7. 前端架构

```
/events  →  Events.vue (主页面)
              ├── 时间范围选择器 + "开始分析"按钮
              ├── 类型筛选栏 (全部/决策/讨论/社交/公告/梗)
              ├── EventTimeline.vue (时间轴组件)
              │     └── EventCard.vue (单个事件卡)
              └── 对话上下文 Modal
```

**报告引用**：周报/月报/年报/画像 Vue 组件各加一个 `<RelatedEvents>` 区块，从现有 API 返回数据中读取关联事件。

### 8. AI Prompt 结构

**System Prompt 走 `prompt_profiles` 体系**，`analysis_type='event_detection'`，与其他分析类型（daily/weekly/monthly/annual/portrait）一致。调用前通过 `get_default_prompt('event_detection')` 获取，无配置时使用硬编码 fallback。

**默认 System Prompt（幽默风味，与周报/月报/年报风格统一）**：

```
你是一个群聊历史学家+八卦记者+脱口秀段子手的混合体。
你的任务是从群聊对话中发掘那些值得被记住的事件——
无论是重要决定、欢乐瞬间、名场面诞生，还是群友之间的默契互动。

你像一个坐在群里的隐形观察员，把精华时刻记录下来，
用轻松诙谐的口吻写成事件卡片。读者看完应该会心一笑：
"对对对，那天就是这样！"

事件类型：
- decision：群内做出了某个决定（讨论→收敛→结论）
- discussion：围绕某个话题的深度讨论
- social：社交互动（庆祝、欢迎、告别、起哄等）
- announcement：某人宣布了重要消息
- meme：梗/文化的诞生和传播

如果这段对话中没有明显事件（就是日常闲聊），返回空 events 数组。
```

**User Prompt**：对话原文 `[HH:MM] 发送者: 内容` 格式，每行一条，附带群名。

不设置 `max_tokens` 硬上限，依赖模型自身输出限制（窗口内最多几个事件，输出不会太长）。

**可配置性**：用户可在 设置 → 高级设置 → Prompt 配置 中编辑或替换事件探测的 System Prompt，与其他分析类型一样。

## Risks / Trade-offs

- **[风险] 活跃群尖峰检测误判**：活跃群消息量基线本身就高，可能把正常高峰误判为事件窗口 → **缓解**：默认不降低绝对阈值（80条/30min），且用户可通过高级设置调整；误判的窗口 AI 会返回空事件（纯闲聊），不产生垃圾数据。
- **[风险] 安静群可能漏检**：如果一个群整月只有零星消息，消息量尖峰也可能只是 15 条/小时 → **缓解**：安静群相对基线 3 倍即可触发；兜底阈值不低于 20 条/小时。如果还是漏了，用户可以缩小时间范围手动重试。
- **[权衡] 窗口固定 200 条 vs 动态大小**：固定 200 条可能把一个很长的讨论事件切在两个窗口里 → **缓解**：20 条重叠 + 后处理去重合并。如果事件仍然跨 3+ 个窗口，会被 AI 从不同角度描述，合并时取并集。
- **[权衡] AI 并发 3 的限制**：用户等待时间 = (窗口数 / 3) × 单次调用耗时。极端情况 50 窗口 × 3 秒 ≈ 50 秒 → 可接受。用户若使用付费 API 可手动调高并发。
- **[风险] 匿名化冲突**：事件探测给 AI 的是原始对话，不经过匿名化处理，但当前画像和报告有匿名化机制 → **决策**：事件探测使用原始名称（用户已上传数据，可见是合理的）。若未来需要匿名化，在事件写入时对 `title`/`description` 中的人名做后处理替换。

## Migration Plan

- 纯新增功能，无需数据迁移
- 新增 `events` 表通过 `init_db()` 自动创建，部署时重启服务即可
- 现有报告、画像功能不受影响
- 回滚：删除 `events` 表，移除新路由注册，前端路由移除 `/events` 即可

## Open Questions

- （已确认）事件粒度：群级别，不区分个人事件
- （已确认）触发方式：纯手动，类似生成周报
- （已确认）与报告关系：独立生成，展示层引用
