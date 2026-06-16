## 1. 数据库迁移

- [x] 1.1 创建 `fish_relationships` 表（id, group_id, fish_wxid_a, fish_wxid_b, relation_type, strength, created_at，UNIQUE(group_id, a, b, type)）
- [x] 1.2 `fish_pond` 新增 `legendary_quest_step INTEGER DEFAULT 0`
- [x] 1.3 `_SETTINGS_DEFS` 注册 4 个新 key：`pond_bulletin_board`(string)、`custom_flavor_texts`(string)、`custom_last_words`(string)、`custom_daily_status`(string)
- [x] 1.4 编写 `_migrate_v1_16_4(conn)` 迁移函数并加入 `_migrate_db()` 调用链

## 2. 天气统一 + 扩展

- [x] 2.1 修改 `_generate_weather()` 签名为 `(date_str)`，移除 `group_id` 参数，seed 改为 `f"weather_{date_str}"`
- [x] 2.2 扩展天气类型从 4→7 种（+双彩虹 3%、沙尘暴 7%、流星雨 2%），调整概率分布
- [x] 2.3 添加 3 种新天气的效果字段（happiness_bonus, sandstorm_penalty, meteor_bonus 等）
- [x] 2.4 更新 `settle_all_fish()` 和 `get_pond_snapshot()` 中 `_generate_weather()` 的调用参数

## 3. 季节系统

- [x] 3.1 实现 `_get_season()` 函数：根据当前月份返回季节（春/夏/秋/冬）+ emoji + 效果描述
- [x] 3.2 在 `settle_all_fish()` 中集成季节 buff（春 growth×1.1 / 夏 竞速选美×1.5 / 秋 宝藏+15% / 冬 稀有×2）
- [x] 3.3 换季检测：对比上次记录的季节，切换时写入 flavor event 通知
- [x] 3.4 `get_pond_snapshot()` 返回 `season` 字段供前端消费

## 4. 鱼际关系网

- [x] 4.1 在 `settle_all_fish()` 末尾实现 `_build_relationships(group_id, date_str)` — 扫描当日 fish_events，统计友谊/劲敌并 upsert
- [x] 4.2 实现首次运行保护：仅扫描最近 30 天（`fish_relationships` 为空时）
- [x] 4.3 `models/database.py` 新增 `upsert_fish_relationship()` 和 `get_fish_relationships(wxid)` 查询函数
- [x] 4.4 API: `GET /api/groups/{gid}/fishpond/fish/{wxid}/relationships` 返回关系列表

## 5. 传奇鱼任务

- [x] 5.1 API: `POST /api/groups/{gid}/fishpond/fish/{wxid}/legendary-quest` — 执行一步检定（根据 legendary_quest_step）
- [x] 5.2 实现 3 步检定逻辑（DC15 STR → DC18 WIS → DC20 CHA），每日限 1 次（app_settings 日期追踪），一生一次，消耗 50 精力
- [x] 5.3 通关奖励：`legendary_quest_step = 4`，写入 personality_traits 标记"传奇"永久优势
- [x] 5.4 通关时写入全塘广播 fish_event
- [x] 5.5 API: `GET /api/groups/{gid}/fishpond/fish/{wxid}/legendary-quest-status` 返回当前步骤和今日是否已挑战

## 6. 轻量定制：改名 + 公告牌 + 创意工坊

- [x] 6.1 API: 改名端点已存在（`POST /fish/{wxid}/rename`），复用现有实现
- [x] 6.2 API: `GET/POST /api/groups/{gid}/fishpond/bulletin` — 读写公告牌（app_settings pond_bulletin_board）
- [x] 6.3 在 `passive_events.py` 中实现文本池合并：`ALL_FLAVOR_TEXTS = FLAVOR_EVENTS + custom`（同理遗言和状态语）
- [x] 6.4 `routers/settings.py` 注册创意工坊 3 个 key 的读写（通过 _SETTINGS_DEFS 和 _seed_app_settings 自动处理）

## 7. 前端：FishCard 改造

- [x] 7.1 FishCard 底部新增"朋友圈"区域，调用 relationships API 展示关系列表（emoji+鱼名+标签）
- [x] 7.2 鱼名旁添加 ✏️ 编辑按钮，点击弹出内联输入框，调用 rename API
- [x] 7.3 传奇鱼（stage=传说 + level≥8）显示"⚔️ 传奇试炼"按钮，调用 legendary-quest API，展示挑战结果

## 8. 前端：PondManagement 改造

- [x] 8.1 顶部展示当前季节 + 天气（emoji + 名称 + 效果描述）
- [x] 8.2 公告牌横幅（📢 + bulletin 内容），空则隐藏
- [x] 8.3 传奇鱼任务状态展示（如有鱼正在挑战中）

## 9. 前端：FishTank 季节/天气动画

- [x] 9.1 4 季 CSS 粒子动画（春樱/夏泡/秋叶/冬雪），实现在 FishTank.vue 背景层
- [x] 9.2 7 种天气 CSS 叠加动画（雨滴/暴风雨闪电/彩虹光晕/双彩虹/沙尘暴/流星），实现在 FishTank.vue 前景覆盖层
- [x] 9.3 季节和天气动画可独立叠加（季节为背景粒子，天气为前景半透明层）

## 10. 前端：Settings 创意工坊 Tab

- [x] 10.1 Settings.vue 新增"创意工坊"Tab（🎨 图标）
- [x] 10.2 3 个 textarea：自定义风味文本 / 自定义遗言 / 自定义状态语（每行一条，max 5000 字符）
- [x] 10.3 每个 textarea 配"保存"和"恢复默认"按钮
- [x] 10.4 公告牌编辑区（单行 input，max 200 字符）

## 11. 集成验证

- [x] 11.1 启动开发服务器，确认数据库迁移成功（新表+新列+新 settings 都存在）
- [x] 11.2 手动触发每日结算，验证天气全群统一、季节 buff 生效、关系自动生成
- [x] 11.3 创建一条传说+8级测试鱼，验证传奇试炼完整流程
- [x] 11.4 验证改名 API + 创意工坊文本合并
- [x] 11.5 前端检查：FishCard 朋友圈、季节/天气动画、公告牌、创意工坊 Tab
