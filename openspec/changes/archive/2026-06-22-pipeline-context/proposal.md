## Why

当前各管线在调用 AI 时重复做三件事：创建任务记录、调 `call_online_chat`（手写 `pipeline`/`group_id` 参数）、保存任务记录。写法各不相同，导致 **13 个 AI 调用点中 8 个缺失日志参数**。需要一个统一的 PipelineContext 对象封装这些重复逻辑，让管线只关心业务，日志和任务记录自动就位。

## What Changes

- **新增 `PipelineContext` 类**：封装 `task_manager` + `call_online_chat` + `save_task_record`，构造时绑定 `pipeline`/`group_id`/`group_name`/`model_config`，提供 `start_task()` / `call_ai()` / `finish_task()` 三个方法
- **`_ai_generate` 迁移**：周报/月报/年报的 AI 调用通过 ctx 走，自动补全 `pipeline`/`group_id`/`task_id`
- **事件管线迁移**：`_call_ai_for_events` 通过 ctx 走
- **日报/画像迁移**：`run_daily_pipeline_online` / `run_portrait_pipeline_online` 通过 ctx 走；画像补 `group_id` 参数
- **不迁移**：本地模型路径、`call_deepseek_chat` 包装器、健康检查、关系判断、趣味称号——这些不在本次范围

## Capabilities

### New Capabilities

- `pipeline-context`: 统一的管线执行上下文，封装任务生命周期和 AI 调用日志记录

### Modified Capabilities

- `ai-call-logs`: PipelineContext 成为 AI 日志的唯一写入入口，替代各管线手写 `pipeline`/`group_id` 参数的散落模式

## Impact

- **新增文件**：`services/pipeline_context.py`
- **修改文件**：`services/weekly_report.py`（`_do_ai_generate`）、`services/event_detector.py`（`_call_ai_for_events`）、`services/pipelines.py`（日报+画像在线函数）
- **不影响**：所有管线的业务逻辑、prompt 构建、数据提取均不变；API 接口不变
