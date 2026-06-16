## Why

鱼塘系统经过 v1.16.0~v1.16.3 四个子版本的迭代，已具备精力驱动、性格修正、被动事件、金库经营等核心玩法。但目前的鱼塘是"孤岛"——鱼与鱼之间没有互动记录，环境没有季节变化，体感单调。同时用户缺乏对鱼塘内容的定制能力。本次 v1.16.4 是鱼塘系统的终章版本，以最小成本补齐互动深度、环境变化、终局挑战和轻度定制四个维度，宣告鱼塘系统正式完成。

## What Changes

- **鱼际关系网（简版）**：每日结算时从事件日志自动生成鱼际关系（友谊/劲敌），FishCard 详情展示朋友圈文字列表
- **季节系统**：4 季基于真实月份自动切换，每季有独立 buff/debuff，前端 CSS 粒子动画（春樱/夏泡/秋叶/冬雪）
- **天气统一+扩展**：全服统一天气（修复当前 per-group 天气不一致问题），从 4 种扩到 7 种，每日换一次
- **传奇鱼任务**：传说阶段 + 等级 ≥8 的鱼可挑战 3 步试炼（STR/WIS/CHA），一生一次，通关永久获得全检定优势
- **轻量定制**：塘主可给鱼改名（金库消耗）、设置鱼塘公告牌、在设置页编辑自定义风味文本/遗言/状态语
- **BREAKING**：`_generate_weather()` 签名从 `(group_id, date_str)` 改为 `(date_str)`，天气不再按群区分

## Capabilities

### New Capabilities

- `fish-relationships`: 鱼际关系网 — 每日结算自动生成 2 种关系（友谊/劲敌），FishCard 展示朋友圈
- `season-system`: 季节系统 — 4 季按月自动切换，全局 buff/debuff，前端 CSS 动画
- `weather-global`: 全服统一天气 — 7 种天气类型，每日更换，CSS 动画叠加层
- `legendary-quest`: 传奇鱼任务 — 3 步连续检定挑战，一生一次，通关永久 buff
- `fish-rename`: 自定义鱼名 — 塘主花费金库给鱼改名
- `pond-bulletin`: 鱼塘公告牌 — 塘主在设置页编辑 slogan，鱼塘顶部展示
- `creative-workshop-lv1`: 创意工坊 Lv1 — 用户可编辑自定义风味文本、遗言、状态语，与内置池合并

### Modified Capabilities

（无——当前 openspec/specs/ 为空，鱼塘系统此前未建立 spec）

## Impact

- **数据库**: 新表 `fish_relationships`；`fish_pond` 新增 `legendary_quest_step` 列；`app_settings` 新增 4 个 key（`pond_bulletin_board`, `custom_flavor_texts`, `custom_last_words`, `custom_daily_status`）
- **后端**: `services/fish_pond.py`（关系计算、季节、天气扩展、传奇任务、改名、公告牌）、`services/passive_events.py`（关系触发挂钩、传奇检定）、`routers/fish_pond.py`（新增 API）、`routers/settings.py`（新增 setting key）、`models/database.py`（迁移、新表、seed）
- **前端**: `FishCard.vue`（朋友圈列表、改名入口）、`PondManagement.vue`（季节展示、公告牌）、`FishTank.vue`（季节/天气 CSS 动画）、`Settings.vue`（创意工坊 Tab）
- **无外部依赖变更**: 不新增 npm/pip 包
