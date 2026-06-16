## 1. 后端：作弊模式基础

- [x] 1.1 `_SETTINGS_DEFS` 新增 `pond_cheat_mode`（bool，默认 false），config.py 添加默认值
- [x] 1.2 `services/fish_pond.py` 的 `_check_keeper_titles()` 增加作弊模式守卫（读取 config，true 时直接 return）
- [x] 1.3 新增 `pond_cheat_weather_override` setting key（string），用于调试天气覆盖

## 2. 后端：调试 API

- [x] 2.1 `POST /api/groups/{gid}/fishpond/debug/coins` — body: {wxid, amount}，加减鳞币 + 风味事件
- [x] 2.2 `POST /api/groups/{gid}/fishpond/debug/trigger-event` — body: {event_group}，强制触发事件 + 风味事件
- [x] 2.3 `POST /api/groups/{gid}/fishpond/debug/weather` — body: {weather_type}，覆盖天气 + 风味事件
- [x] 2.4 `POST /api/groups/{gid}/fishpond/debug/kill` — body: {wxid}，秒杀鱼 + 遗言 + 风味事件
- [x] 2.5 `POST /api/groups/{gid}/fishpond/debug/revive` — body: {wxid}，复活鱼 + 风味事件
- [x] 2.6 所有调试端点增加作弊模式校验（非作弊模式返回 403）

## 3. 后端：天气覆盖集成

- [x] 3.1 `_generate_weather()` 读取 `pond_cheat_weather_override`，非空时直接返回覆盖值
- [x] 3.2 `settle_all_fish()` 末尾清除 `pond_cheat_weather_override`

## 4. Settings 重构

- [x] 4.1 Tab "创意工坊"改名为"鱼塘设置"（emoji: 🐟）
- [x] 4.2 将鱼塘自动化块（开关+间隔）移入鱼塘设置 Tab 的 `v-if` 内，删除旧的跨 Tab 渲染代码
- [x] 4.3 "静默鱼塘"文案改为"鱼塘自动化"
- [x] 4.4 新增"允许作弊"开关 UI，绑定 `pond_cheat_mode` setting

## 5. ChatSimulator 显隐 + 调试面板

- [x] 5.1 FishPond.vue 中 ChatSimulator 包裹 `v-if="cheatMode"`，从 `getAppSettings` 读取状态
- [x] 5.2 ChatSimulator.vue 新增调试面板分区（作弊模式下显示）
- [x] 5.3 实现鳞币操作 UI（wxid 下拉 + 数额输入 + 执行按钮）
- [x] 5.4 实现触发事件 UI（分组下拉选择 + 触发按钮）
- [x] 5.5 实现天气覆盖 UI（7 选 1 下拉 + 设置按钮）
- [x] 5.6 实现秒杀/复活 UI（wxid 选择 + 确认按钮）

## 6. 教程分栏

- [x] 6.1 教程弹窗改为双栏布局（左侧 nav 120px，右侧内容 flex-1）
- [x] 6.2 实现左侧 4 项导航切换（🐟鱼塘教程 / 🎲D20系统 / 📋指令参考 / 🎮作弊模式）
- [x] 6.3 编写"🐟 鱼塘教程"内容（基本概念/养成/指令/结算/自动化）
- [x] 6.4 编写"🎲 D20系统"内容（六维/检定/熟练/性格修正/大成功大失败）
- [x] 6.5 编写"📋 指令参考"内容（全部指令速查表）
- [x] 6.6 编写"🎮 作弊模式"内容（开启方式/调试功能/注意事项）
