## ADDED Requirements

### Requirement: 调试面板入口
ChatSimulator 在作弊模式下 SHALL 显示额外的调试面板 UI。

#### Scenario: 调试面板可见
- **WHEN** `pond_cheat_mode === true`
- **THEN** ChatSimulator 底部显示"🔧 调试"分区，包含全部调试操作

#### Scenario: 非作弊模式隐藏
- **WHEN** `pond_cheat_mode === false`
- **THEN** ChatSimulator 整体不渲染（v-if=false）

### Requirement: 加减鳞币
调试面板 SHALL 提供加减鳞币功能。

#### Scenario: 加鳞币
- **WHEN** 操作者在调试面板选择目标鱼、输入正数额并执行
- **THEN** 目标鱼鳞币增加指定数额，生成风味事件"被不明力量赠与了 X 鳞币"

#### Scenario: 减鳞币
- **WHEN** 操作者输入负数额（扣除）
- **THEN** 目标鱼鳞币减少（最低0），生成风味事件"被不明力量取走了 X 鳞币"

### Requirement: 强制触发事件
调试面板 SHALL 提供强制触发被动事件功能。

#### Scenario: 选择事件类型触发
- **WHEN** 操作者在调试面板选择事件分组（danger/lucky/welfare/rare/flavor）并执行
- **THEN** 系统对该群立即触发一次对应分组事件，生成风味事件"一股不明力量搅动了鱼塘..."

### Requirement: 设置天气
调试面板 SHALL 提供覆盖当日天气功能。

#### Scenario: 覆盖天气
- **WHEN** 操作者在调试面板选择 7 种天气之一并确认
- **THEN** 当日天气被覆盖为所选类型（存 `pond_cheat_weather_override`），生成风味事件"天空异变..."

#### Scenario: 每日结算清除覆盖
- **WHEN** 每日结算执行
- **THEN** `pond_cheat_weather_override` 被清除，次日恢复随机天气

### Requirement: 秒杀与复活
调试面板 SHALL 提供秒杀和复活鱼功能。

#### Scenario: 秒杀鱼
- **WHEN** 操作者选择存活鱼并点击秒杀
- **THEN** 目标鱼 HP 归零、标记死亡、随机分配遗言，生成风味事件"被不明力量秒杀了"

#### Scenario: 复活鱼
- **WHEN** 操作者选择已死鱼并点击复活
- **THEN** 目标鱼 HP=1、is_alive=1、精力恢复至 max，生成风味事件"被不明力量复活了"
