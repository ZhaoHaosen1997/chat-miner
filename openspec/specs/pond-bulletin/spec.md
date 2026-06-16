## ADDED Requirements

### Requirement: 塘主可设置公告牌
系统 SHALL 允许塘主在设置页编辑鱼塘公告牌内容，并在鱼塘页面顶部展示。

#### Scenario: 编辑公告牌
- **WHEN** 塘主在设置页"鱼塘公告牌"输入框中编辑内容并保存
- **THEN** 内容存储到 `app_settings` 的 `pond_bulletin_board` key，类型为 string

#### Scenario: 公告牌展示
- **WHEN** 用户打开鱼塘页面且公告牌内容非空
- **THEN** PondManagement 顶部显示公告牌横幅，包含 📢 图标和公告内容

#### Scenario: 空公告牌隐藏
- **WHEN** 公告牌内容为空字符串
- **THEN** 公告牌横幅不显示

#### Scenario: 公告牌字数限制
- **WHEN** 塘主编辑公告牌内容
- **THEN** 最多 200 字符
