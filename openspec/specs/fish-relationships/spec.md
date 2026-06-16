## ADDED Requirements

### Requirement: 鱼际关系自动生成
系统 SHALL 在每日结算时，扫描当日 `fish_events` 表，自动更新鱼与鱼之间的关系。

#### Scenario: 友谊关系生成
- **WHEN** 两条鱼在同一天内共同经历了 3 次及以上群体事件（type 为 race/storm/rainbow/acid_rain/feed_ship/bubble_party/underwater_concert 等群体类事件）
- **THEN** 系统在 `fish_relationships` 表中创建或升级一条 relation_type="friendship" 的记录

#### Scenario: 劲敌关系生成
- **WHEN** 两条鱼之间发生了 3 次及以上 battle 事件
- **THEN** 系统在 `fish_relationships` 表中创建或升级一条 relation_type="rivalry" 的记录

#### Scenario: 首次运行仅计算近期
- **WHEN** `fish_relationships` 表为空（首次运行）
- **THEN** 系统仅扫描最近 30 天的 fish_events，而非全量历史

### Requirement: 鱼际关系查询
系统 SHALL 提供 API 查询任意存活鱼的关系列表。

#### Scenario: 查询鱼的朋友圈
- **WHEN** 前端请求 `GET /api/groups/{gid}/fishpond/fish/{wxid}/relationships`
- **THEN** 返回该鱼的所有关系，每条包含对方鱼名、emoji、关系类型、强度（触发次数）

### Requirement: 关系展示
前端 SHALL 在 FishCard 详情视图中展示该鱼的"朋友圈"文字列表。

#### Scenario: 展示关系列表
- **WHEN** 用户打开任意鱼的 FishCard 详情
- **THEN** 卡片底部显示"朋友圈"区域，列出所有有关系的好友/宿敌（emoji + 鱼名 + 关系标签），按关系强度降序排列
