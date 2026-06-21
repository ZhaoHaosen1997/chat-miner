## 1. PipelineContext 类实现

- [x] 1.1 创建 `services/pipeline_context.py`，实现 `PipelineContext` 类
- [x] 1.2 `__init__` 绑定 `pipeline`、`group_id`、`group_name`、`model_config`，创建 `_task` 属性初始为空
- [x] 1.3 `start_task(task_type, target)` → `task_manager.create()`，存储到 `self._task`
- [x] 1.4 `finish_task(success, error)` → `task.finish()` + `save_task_record()`
- [x] 1.5 `call_ai(system_prompt, user_prompt, **kwargs)` → `call_online_chat` 自动注入 `pipeline=self.pipeline`、`group_id=self.group_id`、`task_id=self._task.task_id`（如有）

## 2. _ai_generate 迁移（周/月/年报）

- [x] 2.1 `_do_ai_generate` 中 `call_online_chat(...)` 替换为 `ctx.call_ai(...)`
- [x] 2.2 构造 ctx：`PipelineContext(pipeline, group_id, group_name, model_config)`，pipeline 由调用方传入
- [x] 2.3 移除手写的梗注入逻辑中与 ctx 无关的部分（梗注入保留，仅去掉日志参数手写）
- [x] 2.4 验证 6 个调用方（周刊v2/v1、月刊v2/v1、年报、年报降级）的 `pipeline`/`group_id` 自动写入 ai_call_logs

## 3. 事件管线迁移

- [x] 3.1 `_call_ai_for_events` 中 `call_online_chat(...)` 替换为 `ctx.call_ai(...)`
- [x] 3.2 构造 ctx：`PipelineContext("event", group_id, group_name, primary_model_config)`
- [x] 3.3 单窗口分析：ctx 关联其 `event_window` task
- [x] 3.4 批量分析：ctx 关联其 `event_window_batch` task

## 4. 日报 + 画像迁移

- [x] 4.1 `run_daily_pipeline_online` 中 `call_online_chat(...)` 替换为 `ctx.call_ai(...)`
- [x] 4.2 `run_portrait_pipeline_online` 加 `group_id: int = 0` 参数；`call_online_chat(...)` 替换为 `ctx.call_ai(...)`
- [x] 4.3 画像调用方传入 `group_id`（溯源找到调用 `run_portrait_pipeline_online` 的地方）

## 5. 验证

- [x] 5.1 启动服务，确认无报错
- [x] 5.2 触发周报生成，检查 `ai_call_logs` 中 pipeline="weekly"、group_id 正确
- [x] 5.3 触发事件分析，检查 AI 日志含 pipeline="event"、group_id
- [x] 5.4 触发日报生成，检查 AI 日志 pipeline="daily" 不受影响
- [x] 5.5 Settings → AI日志 tab 中按 pipeline 筛选各管线均正常
