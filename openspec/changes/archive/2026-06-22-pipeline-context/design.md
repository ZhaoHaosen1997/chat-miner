## Context

当前 13 个 `call_online_chat` 调用点中，只有 4 个传了完整的 `pipeline` + `group_id`。各管线各自手写 `task_manager.create()`、`save_task_record()`、日志参数，写法互不相同。需要一个轻量封装层统一这些重复操作。

PipelineContext 不重写任何底层逻辑——它只是 `task_manager`、`call_online_chat`、`save_task_record` 的外观（Facade），自动注入上下文参数。

## Goals / Non-Goals

**Goals:**
- 提供 `PipelineContext` 对象，封装任务创建 + AI 调用 + 任务持久化
- 迁移 4 个在线 AI 调用汇聚函数：`_do_ai_generate`、`_call_ai_for_events`、`run_daily_pipeline_online`、`run_portrait_pipeline_online`
- 迁移后所有在线 AI 调用日志含完整 `pipeline` + `group_id`

**Non-Goals:**
- 不迁移本地模型路径
- 不迁移 `call_deepseek_chat` 包装器、健康检查、关系判断、趣味称号
- 不改变任何管线的业务逻辑、prompt 构建、API 接口
- 不改变 `_ai_generate` 的在线→本地降级逻辑（降级路径只调 `call_ollama_chat`，不涉及日志）

## Decisions

### D1: PipelineContext 是 Facade，不是新抽象层

```
PipelineContext
  ├─ .start_task()  → task_manager.create()     [复用]
  ├─ .update_task() → task.update()              [复用]
  ├─ .finish_task() → task.finish() + save_task_record() [复用]
  └─ .call_ai()     → call_online_chat()         [复用，自动注入参数]
```

不引入新的 task 抽象，不改变 `TaskInfo` 类。单纯把散落的调用收敛到一处。

### D2: call_ai 签名与 call_online_chat 对齐

`call_ai(system_prompt, user_prompt, **kwargs)` 把 kwargs 透传给 `call_online_chat`。`pipeline`、`group_id`、`task_id` 由 ctx 注入，kwargs 中不应再包含这三个参数。

### D3: 迁移用"替换"策略，不用"重写"

每个迁移点只改两样：
1. 构造 ctx 替代分散的变量
2. `call_online_chat(...)` → `ctx.call_ai(...)`（去掉手写的 pipeline=/group_id=）

其他代码（prompt 构建、结果解析、错误处理）原封不动。

### D4: 画像加 group_id 参数

`run_portrait_pipeline_online` 当前没有 `group_id` 参数。需要在其调用方传入。不影响画像的业务逻辑，只是多一个参数。

## Risks / Trade-offs

- **PipelineContext 成为新依赖** → 但它是纯 Facade，底层函数不变，测试可逐个管线独立进行
- **本地降级路径不受益** → 这是刻意设计，本地模型通过 Ollama 走不通 `call_online_chat`，不需要日志
- **call_deepseek_chat 包装器遗留** → 目前仅旧版降级路径在用，后续可逐步废弃或也走 ctx
