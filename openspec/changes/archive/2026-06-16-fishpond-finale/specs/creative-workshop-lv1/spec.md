## ADDED Requirements

### Requirement: 自定义风味文本
系统 SHALL 允许用户在设置页编辑自定义风味文本，与内置风味文本池合并使用。

#### Scenario: 编辑自定义风味文本
- **WHEN** 用户在设置页"创意工坊"Tab 的"自定义风味文本"textarea 中每行输入一条文本并保存
- **THEN** 内容以 JSON 数组存储到 `app_settings` 的 `custom_flavor_texts` key

#### Scenario: 合并到事件池
- **WHEN** 被动事件骰到"风味文本"兜底
- **THEN** 系统从内置 FLAVOR_EVENTS + 用户自定义风味文本的合并池中随机选择

### Requirement: 自定义遗言
系统 SHALL 允许用户编辑自定义鱼遗言，与内置遗言池合并使用。

#### Scenario: 编辑自定义遗言
- **WHEN** 用户在设置页"创意工坊"Tab 的"自定义遗言"textarea 中每行输入一条文本并保存
- **THEN** 内容以 JSON 数组存储到 `app_settings` 的 `custom_last_words` key

#### Scenario: 合并到遗言池
- **WHEN** 鱼死亡需要随机选择遗言
- **THEN** 系统从内置 FISH_LAST_WORDS + 用户自定义遗言的合并池中随机选择

### Requirement: 自定义状态语
系统 SHALL 允许用户编辑自定义无聊状态语，与内置池合并使用。

#### Scenario: 编辑自定义状态语
- **WHEN** 用户在设置页"创意工坊"Tab 的"自定义状态语"textarea 中每行输入一条文本并保存
- **THEN** 内容以 JSON 数组存储到 `app_settings` 的 `custom_daily_status` key

#### Scenario: 合并到状态池
- **WHEN** 鱼当日无特别事件需要随机状态语
- **THEN** 系统从内置 BORED_STATUSES + 用户自定义状态语的合并池中随机选择

### Requirement: 字数限制与恢复默认
系统 SHALL 对每个 textarea 限制最大 5000 字符，并提供"恢复默认"按钮。

#### Scenario: 字数超限拒绝
- **WHEN** 用户输入超过 5000 字符
- **THEN** 前端显示警告，保存按钮禁用

#### Scenario: 恢复默认
- **WHEN** 用户点击"恢复默认"按钮
- **THEN** 对应 textarea 清空，app_settings 值重置为 `[]`
