## Context

Settings.vue 当前有 4 个 Tab：基础设置、高级选项、任务记录、创意工坊。鱼塘自动化设置块位于高级选项 Tab 闭合后，无 v-if 包裹，导致所有 Tab 下可见。创意工坊 Tab 实际承载鱼塘公告牌和自定义文本功能。

ChatSimulator 是一个浮动在鱼塘页面右下角的指令模拟器，始终可见。教程是 560px 宽的单栏弹窗，内联在 FishPond.vue 中。

## Goals / Non-Goals

**Goals:**
- 修复鱼塘设置块跨 Tab 出现的 bug
- 将鱼塘相关设置汇聚到一个 Tab 下（鱼塘设置）
- 提供作弊开关控制调试功能可见性和成就系统
- 模拟器增加实用调试操作
- 教程改为分栏布局，覆盖鱼塘核心知识

**Non-Goals:**
- 不改变现有成就称号检查逻辑（仅在调用处插入开关判断）
- 不持久化调试操作历史（风味事件除外）
- 不新增 npm/pip 依赖

## Decisions

### D1: 作弊开关存储 — app_settings 单 key

`pond_cheat_mode`（bool 类型，默认 false）。前端读取 `getAppSettings` 的返回值判断是否开启。

### D2: ChatSimulator 显隐控制 — v-if 而非 v-show

作弊 OFF 时 ChatSimulator 完全销毁（v-if=false），避免无用 API 调用和内存占用。

### D3: 调试操作与风味事件 — 每条操作写一条 fish_event

调试操作后自动调用 `db.add_fish_event(type="flavor", text="被不明力量xxx")`。使用统一前缀便于识别。

### D4: 天气覆盖 — 存 app_settings，当日生效

`pond_cheat_weather_override` key 存储覆盖天气 type。`_generate_weather()` 读取此 key，非空则直接返回覆盖值而非随机生成。每日结算后自动清除。

### D5: 教程分栏 — 左侧 nav + 右侧内容

纯前端重构，不涉及路由变更。左侧垂直 Tab 列表，右侧根据 active 切换内容。响应式：窄屏时 nav 在上方横向排列。

## Risks / Trade-offs

- **[R] 作弊模式下成就永久缺失**：非作弊期间错过的称号不会补发。→ 设计如此，作弊是塘主主动选择。
- **[R] 调试操作误用**：秒杀/复活可能导致鱼数据异常。→ 仅在作弊模式下可见，降低误触概率。
- **[R] 天气覆盖持久化**：忘记清除会导致天气停滞。→ 每日结算时自动清除覆盖值。
