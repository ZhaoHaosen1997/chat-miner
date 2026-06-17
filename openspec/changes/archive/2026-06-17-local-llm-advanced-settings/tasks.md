## 1. 数据库与配置层

- [x] 1.1 config.py 新增 8 个属性 + VERSION=1.17.0
- [x] 1.2 _SETTINGS_DEFS 新增 8 个配置项
- [x] 1.3 KEY_ATTR_MAP 新增对应映射
- [x] 1.4 _migrate_v1_17_0() + init_db() 调用
- [x] 1.5 验证迁移：旧 DB 升级后 local_llm_enabled=true，新装=false

## 2. 后端降级门控

- [x] 2.1 pipelines.py 硬编码常量改为 config 读取
- [x] 2.2 run_daily_pipeline_online() 降级加 LOCAL_LLM_ENABLED 检查
- [x] 2.3 run_portrait_pipeline_online() 降级加 LOCAL_LLM_ENABLED 检查
- [x] 2.4 resolve_model_with_fallback() online->local 跨类型降级加检查
- [x] 2.5 weekly_report.py 两处降级加检查
- [x] 2.6 验证：在线不可用时降级阻断

## 3. 更新检查优化

- [x] 3.1 updater.py Gitee 优先，GitHub 备用

## 4. Header 导航修复

- [x] 4.1 Layout.vue：设置按钮从 v-if="currentGroup" 拆出，始终渲染
- [x] 4.2 navItems 拆分为 groupNavItems + 独立设置按钮
- [x] 4.3 验证：无群/有群切换时设置按钮始终可点击

## 5. 首次运行引导

- [x] 5.1 App.vue onMounted：检测在线模型 api_key 全空时 router.push('/settings')
- [x] 5.2 Settings.vue 基础 Tab 顶部引导提示条（showFirstRunBanner）
- [x] 5.3 验证：清空 API Key 重启自动跳转设置页

## 6. 基础设置重构

- [x] 6.1 移除 AI 模型分配、本地模型列表、添加模型按钮、在线模型列表
- [x] 6.2 保留默认群组卡片
- [x] 6.3 新增在线模型卡片：操作 is_default=1 的 online 模型
- [x] 6.4 Provider 下拉（DeepSeek/SenseNova/自定义），自动填入 endpoint + model_name
- [x] 6.5 验证：基础设置仅两个卡片

## 7. 高级设置重构

- [x] 7.1 顶部警告提示条
- [x] 7.2 本地大模型卡片：开关 + 服务地址 + 降级模型名
- [x] 7.3 在线模型配置卡片：CRUD 列表 + 添加按钮
- [x] 7.4 本地模型配置卡片：CRUD 列表 + 添加按钮
- [x] 7.5 AI 模型分配卡片：下拉列出所有模型（在线+本地）
- [x] 7.6 管道执行参数卡片
- [x] 7.7 保留现有卡片（超时重试/报告参数/周期阈值/GPU锁/过滤词/其他）
- [x] 7.8 验证：高级选项按顺序展示

## 8. 任务记录无群行为

- [x] 8.1 无群时 API groupId=undefined，后端自动返回全部任务
- [x] 8.2 验证：无群时看到所有群任务，有群时过滤

## 9. 本地大模型服务地址

- [x] 9.1 app_settings 新增 local_llm_host
- [x] 9.2 config.py 新增 LOCAL_LLM_HOST
- [x] 9.3 高级选项本地大模型卡片展示和编辑

## 10. 版本号与最终验证

- [x] 10.1 config.py VERSION = "1.17.0"
- [ ] 10.2 全流程测试
- [ ] 10.3 升级测试
