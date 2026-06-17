## Why

发行版用户绝大多数是电脑小白，不懂如何配置本地大模型（Ollama）。当前本地模型和在线模型并列展示在基础设置页，既造成困惑，又导致在线模型失败时无条件降级到本地——对未配置本地模型的用户徒增无意义的等待和错误。同时，代码中存在多处硬编码参数（重试次数、超时、熔断阈值等），高级用户无法按需调优。

## What Changes

- **设置按钮全局化**：修复 Header 导航，设置按钮始终可见，不依赖群选择
- **首次使用引导**：无在线模型 API Key 时自动跳转设置页，引导完成配置
- **Provider 预设**：支持 DeepSeek / SenseNova / 自定义三种服务商，选择后自动填入端点和模型，用户只需粘贴 API Key
- **基础设置精简**：仅保留"默认群组"和"在线模型"两个卡片，在线模型单条直接编辑，无列表无添加按钮
- **本地模型全量迁入高级选项**：全局开关、本地模型 CRUD 列表、AI 模型分配、管道执行参数均放在高级选项
- **新增本地大模型全局开关**：`local_llm_enabled`（默认 false），关闭时阻断所有在线→本地降级
- **新增 6 个可配置项**：`local_llm_enabled`、`local_llm_host`、`local_llm_fallback_model`、`pipeline_max_retries`、`pipeline_step_timeout`、`pipeline_circuit_breaker_threshold`、`pipeline_circuit_breaker_cooldown`
- **升级兼容**：旧用户检测到已有本地模型后自动开启 `local_llm_enabled=true`
- **任务记录全局化**：无群时显示所有群的任务，有群时过滤当前群
- **更新检查优化**：`updater.py` 中 Gitee 优先于 GitHub

## Capabilities

### New Capabilities

- `local-llm-gate`: 本地大模型全局开关 + 服务地址配置，关闭时阻断所有在线→本地降级路径
- `pipeline-tuning`: 管道执行参数可配置化
- `settings-page-reorg`: 设置页面全局重构——Header 导航修复、首次使用引导、Provider 预设、基础设置精简、本地模型迁入高级、任务记录全局化

### Modified Capabilities

<!-- No existing capabilities are modified at the spec level -->

## Impact

- **后端**: `models/database.py`、`services/pipelines.py`、`services/model_config.py`、`services/weekly_report.py`、`services/updater.py`
- **前端**: `Layout.vue`（Header 导航）、`Settings.vue`（全面重构）、`TaskHistory.vue`（无群行为）、`App.vue`（首次运行检测）
- **数据**: `app_settings` 表新增 7 条记录，`_migrate_v1_17_0()` 自动迁移
- **config.py**: 新增配置属性，保留硬编码兜底
- **API**: 无需新增端点
- **无破坏性变更**：旧用户升级后本地模型功能自动保持开启
