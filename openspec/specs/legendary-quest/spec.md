## ADDED Requirements

### Requirement: 传奇鱼任务触发条件
系统 SHALL 允许 stage 为"传说"且 level ≥ 8 的存活鱼发起传奇试炼。

#### Scenario: 满足条件可挑战
- **WHEN** 鱼的 stage 为"传说"且 level ≥ 8
- **THEN** 前端 FishCard 显示"⚔️ 传奇试炼"按钮

#### Scenario: 不满足条件不可见
- **WHEN** 鱼不满足触发条件
- **THEN** "传奇试炼"按钮不可见

### Requirement: 三步连续挑战
系统 SHALL 提供 3 步连续检定挑战，每步使用 d20 能力检定。

#### Scenario: 第一步 — 力量试炼
- **WHEN** 鱼发起传奇试炼第一步
- **THEN** 系统执行 DC15 STR 检定（带性格修正和熟练加值），成功则进入第二步，失败则本日挑战结束

#### Scenario: 第二步 — 智慧试炼
- **WHEN** 鱼通过第一步后继续
- **THEN** 系统执行 DC18 WIS 检定，成功则进入第三步，失败则本日挑战结束

#### Scenario: 第三步 — 意志试炼
- **WHEN** 鱼通过第二步后继续
- **THEN** 系统执行 DC20 CHA 检定，成功则全部通关，失败则本日挑战结束

### Requirement: 挑战限制
系统 SHALL 对传奇试炼施加每日次数和一生一次的限制。

#### Scenario: 每日限一次
- **WHEN** 鱼在当日已尝试过传奇试炼（无论成功或失败）
- **THEN** 当日不可再次挑战，返回"今日已挑战过，明天再来"

#### Scenario: 一生一次
- **WHEN** 鱼已全部通关（legendary_quest_step = 4）
- **THEN** 不可再次挑战

#### Scenario: 精力消耗
- **WHEN** 鱼发起传奇试炼
- **THEN** 消耗 50 点精力；精力不足时拒绝挑战

### Requirement: 通关奖励
系统 SHALL 在鱼全部通关后授予永久 buff。

#### Scenario: 永久全检定优势
- **WHEN** 鱼通过全部 3 步试炼
- **THEN** 该鱼的所有后续 d20 检定获得永久优势（advantage），并在 fish_events 中记录全塘广播事件

#### Scenario: 通关称号
- **WHEN** 鱼全部通关
- **THEN** 该鱼获得"传奇"后缀标识，前端 FishCard 展示特殊边框或徽章
