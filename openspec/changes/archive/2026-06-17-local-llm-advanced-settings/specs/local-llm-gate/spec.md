## ADDED Requirements

### Requirement: 本地大模型全局开关

系统 SHALL 提供 `local_llm_enabled` 配置项（bool 类型，默认 false），作为本地大模型功能的全局开关。

#### Scenario: 新安装默认关闭
- **WHEN** 全新安装 Chat-Miner 且数据库中无任何 `model_type='local'` 的模型配置记录
- **THEN** `local_llm_enabled` 默认值为 `false`

#### Scenario: 旧用户升级自动开启
- **WHEN** 从 1.16.x 或更早版本升级到 1.17.x，且数据库 `model_configs` 表中存在 `model_type='local'` 的记录
- **THEN** 系统自动设置 `local_llm_enabled=true`

#### Scenario: 开关关闭时本地模型不可用
- **WHEN** `local_llm_enabled=false`
- **THEN** 高级选项中本地模型配置列表仍可管理，但降级链路被阻断
- **AND** 基础设置页不展示任何本地模型相关内容（1.17.0 起基础设置页已移除所有本地模型管理）

#### Scenario: 开关开启时本地模型可用
- **WHEN** `local_llm_enabled=true`
- **THEN** 高级选项中本地模型可正常用于降级和分析任务

### Requirement: 本地大模型服务地址可配置

系统 SHALL 提供 `local_llm_host` 配置项（string 类型，默认 `http://localhost:11434`），作为 Ollama 服务的默认连接地址。

#### Scenario: 修改 Ollama 服务地址
- **WHEN** 用户在高级设置修改本地大模型服务地址并保存
- **THEN** 随后添加本地模型时 endpoint 默认使用该地址

### Requirement: 降级链路门控

当 `local_llm_enabled=false` 时，所有在线模型失败后的降级路径 SHALL 被阻断，不降级到本地模型。

#### Scenario: 日报在线模型失败时阻断降级
- **WHEN** `run_daily_pipeline_online()` 中在线模型调用失败，且 `local_llm_enabled=false`
- **THEN** 系统不调用 `run_daily_pipeline()`，记录日志并返回包含错误信息的空结果

#### Scenario: 画像在线模型失败时阻断降级
- **WHEN** `run_portrait_pipeline_online()` 中在线模型调用失败，且 `local_llm_enabled=false`
- **THEN** 系统不调用 `run_portrait_pipeline()`，记录日志并返回包含错误信息的空结果

#### Scenario: 周报/月报在线模型失败时阻断降级
- **WHEN** `weekly_report.py` 中在线模型调用失败，且 `local_llm_enabled=false`
- **THEN** 系统不降级到本地 Ollama，记录日志并返回错误

#### Scenario: resolve_model_with_fallback 跨类型降级被阻断
- **WHEN** `resolve_model_with_fallback("online", ...)` 解析兜底模型，且 `local_llm_enabled=false`
- **THEN** fallback 不返回 local 类型模型配置

#### Scenario: 开关开启时降级行为不变
- **WHEN** `local_llm_enabled=true` 且在线模型调用失败
- **THEN** 降级行为与 1.16.x 版本完全一致，自动切换到本地模型管线

### Requirement: 降级失败错误信息

降级被阻断时，系统 SHALL 返回明确的中文错误信息，告知用户原因。

#### Scenario: 任务状态中的降级阻断提示
- **WHEN** 降级被 `local_llm_enabled` 开关阻断
- **THEN** 任务状态中 step 字段包含"本地模型已禁用"等中文提示

#### Scenario: 日志中的降级阻断记录
- **WHEN** 降级被阻断
- **THEN** 系统以 WARNING 级别记录日志，包含模型类型、任务类型、开关状态
