## ADDED Requirements

### Requirement: 允许作弊开关
系统 SHALL 在设置页提供"允许作弊"开关，存储在 `app_settings.pond_cheat_mode`（bool，默认 false）。

#### Scenario: 开启作弊
- **WHEN** 用户在鱼塘设置 Tab 中开启"允许作弊"
- **THEN** 成就系统停止检查新称号（不弹 toast），鱼塘页面显示 ChatSimulator 指令模拟器

#### Scenario: 关闭作弊
- **WHEN** 用户关闭"允许作弊"
- **THEN** 成就系统恢复正常运作，鱼塘页面隐藏 ChatSimulator

### Requirement: 成就跳过
系统 SHALL 在作弊模式开启时跳过 `check_all_titles()` 调用。

#### Scenario: 作弊模式下的成就调用
- **WHEN** 触发称号检查且 `pond_cheat_mode === true`
- **THEN** 函数立即返回，不执行任何检查或写入
