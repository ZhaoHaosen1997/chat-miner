## ADDED Requirements

### Requirement: 塘主可给鱼改名
系统 SHALL 允许塘主花费金库给任意存活鱼改名。

#### Scenario: 成功改名
- **WHEN** 塘主通过 `POST /api/groups/{gid}/fishpond/fish/{wxid}/rename` 提交新名称且金库余额 ≥ 30
- **THEN** 系统扣除金库 30 鳞币，更新鱼名，记录 treasury_log，返回成功

#### Scenario: 金库不足拒绝
- **WHEN** 塘主提交改名但金库余额 < 30
- **THEN** 系统返回错误"金库不足"

#### Scenario: 空名称拒绝
- **WHEN** 塘主提交空字符串或纯空白名称
- **THEN** 系统返回错误"名称不能为空"

#### Scenario: 名称长度限制
- **WHEN** 塘主提交超过 20 字符的名称
- **THEN** 系统返回错误"名称过长（最多20字符）"

### Requirement: 前端改名入口
前端 SHALL 在 FishCard 详情中提供改名入口。

#### Scenario: 改名按钮
- **WHEN** 用户打开任意存活鱼的 FishCard 详情
- **THEN** 鱼名旁边显示 ✏️ 编辑图标，点击弹出内联编辑框
