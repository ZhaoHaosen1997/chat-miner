## Why

设置页面的鱼塘自动化设置块因缺少 tab 条件包裹，出现在所有 tab 下，体验混乱。创意工坊 Tab 名不副实——其内容全是鱼塘相关设置而非"创意工坊"。同时鱼塘缺少调试入口和系统化教程，塘主学习和排查问题不便。

## What Changes

- **Settings 重构**：Tab "创意工坊"改名为"鱼塘设置"；将鱼塘自动化块移入该 Tab 内，修复在所有 Tab 下出现的 bug
- **命名统一**："静默鱼塘"改名为"鱼塘自动化"
- **允许作弊开关**：新增 `pond_cheat_mode` 设置项。ON 时停止成就称号检查、显示 ChatSimulator；OFF 时恢复正常
- **ChatSimulator 调试面板**：作弊模式下新增加减鳞币、强制触发事件、设置天气、秒杀/复活鱼，操作生成"被不明力量xxx"风味事件
- **教程分栏**：教程弹窗改为左侧导航+右侧内容的双栏布局，4 个专栏（鱼塘教程/D20系统/指令参考/作弊模式），每栏简要描述

## Capabilities

### New Capabilities

- `cheat-mode`: 允许作弊开关 — 控制成就系统启停和调试面板可见性
- `simulator-debug`: 模拟器调试面板 — 鳞币操作、事件触发、天气覆盖、鱼生死管理
- `tutorial-split`: 教程分栏 — 双栏布局，4 个独立内容区

### Modified Capabilities

- `creative-workshop-lv1`: Tab 重命名为"鱼塘设置"，合并鱼塘自动化设置（原 settings 结构变更）
- `pond-bulletin`: 跟随 Tab 重命名，仍在鱼塘设置 Tab 内

## Impact

- **前端重**：`Settings.vue`（Tab 结构重构 + 新开关）、`ChatSimulator.vue`（调试面板）、`FishPond.vue`（教程分栏 + 作弊模式条件渲染）
- **后端轻**：`services/fish_pond.py`（成就跳过、调试 API）、`routers/fish_pond.py`（调试端点）、`models/database.py`（新增 `pond_cheat_mode` setting key）
