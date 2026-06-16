## ADDED Requirements

### Requirement: 季节自动切换
系统 SHALL 根据当前真实月份自动确定季节，全服统一。

#### Scenario: 春季（3-5月）
- **WHEN** 当前月份为 3、4 或 5 月
- **THEN** 季节为"🌸 春"，效果为"全体鱼 growth +10%"

#### Scenario: 夏季（6-8月）
- **WHEN** 当前月份为 6、7 或 8 月
- **THEN** 季节为"☀️ 夏"，效果为"竞速/选美奖励 ×1.5"

#### Scenario: 秋季（9-11月）
- **WHEN** 当前月份为 9、10 或 11 月
- **THEN** 季节为"🍂 秋"，效果为"宝藏概率 +15%，鳞币收益 +20%"

#### Scenario: 冬季（12-2月）
- **WHEN** 当前月份为 12、1 或 2 月
- **THEN** 季节为"❄️ 冬"，效果为"稀有事件概率 ×2"

### Requirement: 季节效果应用
系统 SHALL 在每日结算时将季节 buff/debuff 应用到全群鱼。

#### Scenario: 春季成长加成
- **WHEN** 当前季节为春且执行每日结算
- **THEN** 所有存活鱼的当日 growth 增量乘以 1.1（向上取整）

#### Scenario: 换季通知
- **WHEN** 季节发生切换（月份跨季）
- **THEN** 系统在 fish_events 中记录一条 flavor 类型事件，内容为换季通知

### Requirement: 季节前端动画
前端 SHALL 在 FishTank 视图中渲染与当前季节对应的 CSS 动画背景。

#### Scenario: 季节粒子动画
- **WHEN** 用户打开鱼塘页面
- **THEN** FishTank 背景显示当前季节对应的粒子动画（春：樱花飘落 / 夏：气泡上升 / 秋：落叶旋转 / 冬：雪花飘落）
