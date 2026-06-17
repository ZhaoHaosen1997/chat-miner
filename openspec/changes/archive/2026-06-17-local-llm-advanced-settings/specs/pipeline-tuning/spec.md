## ADDED Requirements

### Requirement: 管道重试次数可配置

系统 SHALL 提供 `pipeline_max_retries` 配置项（int 类型，默认 3），控制子任务管道的最大重试次数。配置值通过 `load_app_settings_to_config()` 覆盖 `config.PIPELINE_MAX_RETRIES`，config.py 中保留默认值 3 作为兜底。

#### Scenario: 未配置时使用默认值
- **WHEN** `app_settings` 表中无 `pipeline_max_retries` 记录
- **THEN** `_run_sub()` 使用 config.py 中的硬编码默认值 3 次重试

#### Scenario: 用户修改重试次数后即时生效
- **WHEN** 用户通过设置页面将 `pipeline_max_retries` 修改为 5 并保存
- **THEN** 下次分析任务启动时 `_run_sub()` 使用新值 5

### Requirement: 管道单步超时可配置

系统 SHALL 提供 `pipeline_step_timeout` 配置项（int 类型，默认 90 秒），控制单个子任务的超时时间。

#### Scenario: 用户增大超时后适应慢模型
- **WHEN** 用户将 `pipeline_step_timeout` 修改为 180 并保存
- **THEN** 每个子任务调用使用 180 秒超时

### Requirement: 熔断阈值可配置

系统 SHALL 提供 `pipeline_circuit_breaker_threshold`（int 类型，默认 5）和 `pipeline_circuit_breaker_cooldown`（int 类型，默认 30 秒），控制管道熔断器的触发条件和冷却时间。

#### Scenario: 降低熔断阈值使其更敏感
- **WHEN** 用户将 `pipeline_circuit_breaker_threshold` 修改为 3
- **THEN** 连续 3 次子任务失败后熔断器触发，后续子任务直接跳过直至冷却结束

#### Scenario: 延长冷却时间
- **WHEN** 用户将 `pipeline_circuit_breaker_cooldown` 修改为 60
- **THEN** 熔断触发后等待 60 秒才恢复

### Requirement: 本地模型降级模型名可配置

系统 SHALL 提供 `local_llm_fallback_model` 配置项（string 类型，默认 `qwen3.5:9b`），当子任务主模型失败时使用此模型重试。

#### Scenario: 用户替换降级模型
- **WHEN** 用户将 `local_llm_fallback_model` 修改为 `qwen2.5:7b` 并保存
- **THEN** `_run_sub()` 在重试阶段使用 `qwen2.5:7b` 而非默认的 `qwen3.5:9b`

### Requirement: 配置项持久化与加载

所有新增配置项 SHALL 遵循现有三层配置体系：config.py 硬编码兜底 → DB app_settings 覆盖 → `load_app_settings_to_config()` 启动加载。

#### Scenario: 配置项在服务重启后保持
- **WHEN** 用户修改 `pipeline_max_retries=5` 后重启服务
- **THEN** 服务启动后 `config.PIPELINE_MAX_RETRIES` 值为 5

#### Scenario: DB 值异常时回退到默认
- **WHEN** `app_settings` 中 `pipeline_max_retries` 的值无法转换为 int（如被误写为字符串 "abc"）
- **THEN** `load_app_settings_to_config()` 记录 WARNING 日志，使用 config.py 中的默认值 3
