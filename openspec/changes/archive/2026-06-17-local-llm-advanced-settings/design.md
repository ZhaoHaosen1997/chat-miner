## Context

Chat-Miner 当前 AI 模型配置通过两条路径管理：`model_configs` 表（用户 CRUD 模型）和 `app_settings` 表（可热更新运行时参数）。本地模型和在线模型在基础设置页并列展示，造成小白用户困惑。在线模型失败时无条件降级到本地。Header 导航栏在 `currentGroup` 为空时整个隐藏（`v-if="currentGroup"`），导致新用户无群时无法进入设置。配置在线模型需要用户自行填写端点 URL 和模型名，门槛高。

已有基础设施：`app_settings` 三层配置体系、`_SETTINGS_DEFS` 注册表、版本化迁移函数、`load_app_settings_to_config()` 启动加载器。

## Goals / Non-Goals

**Goals:**
- 设置按钮全局可见：无论是否选择了群，设置入口始终可用
- 首次使用引导：未配置在线模型 API Key 时自动跳转设置页，提示完成配置
- Provider 预设：支持 DeepSeek、SenseNova、自定义三种，选择后自动填入端点和默认模型，用户只需粘贴 API Key
- 基础设置精简为两项：默认群组 + 一个在线模型（默认展开、直达编辑）
- 本地模型全量迁入高级选项：全局开关、本地模型 CRUD、AI 模型分配
- 全局开关 `local_llm_enabled`，默认关闭，阻断所有在线→本地降级
- 管道硬编码参数暴露到 app_settings
- 任务记录无群时显示所有群
- 升级不损坏旧用户数据
- 更新检查 Gitee 优先

**Non-Goals:**
- 不修改 config.py 硬编码值（保留兜底）
- 不新增 API 端点（复用现有 `/api/settings` CRUD）
- 不影响鱼塘系统、WeFlow、提示词管理等无关模块

## Decisions

### 1. Header 导航：设置按钮始终在 DOM 中

当前 `<nav v-if="currentGroup">` 包裹了所有导航按钮（包括设置），无群时整个 nav 销毁。改为设置按钮独立渲染，不使用 `v-if`，避免 DOM 重建导致事件丢失：

```html
<div class="flex items-center gap-1">
  <template v-if="currentGroup">
    <button v-for="item in groupNavItems" ...>  <!-- 仪表盘/画像/鱼塘 -->
  </template>
  <button @click="navTo('/settings')">⚙ 设置</button>  <!-- 始终渲染 -->
</div>
```

### 2. 首次运行引导

```python
# App.vue onMounted
if no online model has api_key configured:
    router.push('/settings')
```

设置页面检测到首次运行，顶部展示引导提示："请先配置在线 AI 模型，选择服务商并填入 API Key 即可开始分析群聊。"

### 3. Provider 预设

用户选择服务商后，端点 URL 和模型名自动填入，可选模型列表随之切换：

| 服务商 | 端点 | 默认模型 | 可选模型 |
|--------|------|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1/chat/completions` | `deepseek-v4-flash` | `deepseek-v4-flash`, `deepseek-v4-pro` |
| SenseNova | `https://token.sensenova.cn/v1/chat/completions` | `deepseek-v4-flash` | `deepseek-v4-flash`, `sensenova-6.7-flash-lite` |
| 自定义 | — | — | 用户自行填写 |

前端维护 `PROVIDER_PRESETS` 常量。选择后填充 `endpoint` 和 `model_name`。切换到自定义时清空，允许自由输入。

### 4. 基础设置页

仅两个卡片，在线模型卡片操作的是 `model_configs` 表中 `is_default=1` 的 online 记录：

```
┌─ 默认群组 ──────────────────────────────────┐
│  打开页面时自动进入该群                       │
│  [群选择下拉]                                 │
└──────────────────────────────────────────────┘

┌─ 在线模型（默认）───────────────────────────┐
│  服务商  [DeepSeek ▼]                         │
│  端点    [https://api.deepseek.com/...]       │
│  模型名  [deepseek-v4-flash ▼]               │
│  API Key [sk-xxxx]               [测试连接]   │
└──────────────────────────────────────────────┘
```

- 编辑的就是 DB 中 `is_default=1` 的 online 模型
- 若 DB 中无在线模型，自动创建一条 `is_default=1` 的空记录
- 这条模型在高级选项"在线模型配置"列表中同样可见，标记为 `[默认]`

### 5. 高级选项页

```
┌─ ⚠️ 谨 慎 修 改 ─────────────────────────────┐

┌─ 本地大模型 ──────── [开关] ─────────────────┐
│  服务地址   [http://localhost:11434]           │
│  降级模型名 [qwen3.5:9b          ]            │
└──────────────────────────────────────────────┘

┌─ 在线模型配置 ──── [+ 添加] ────────────────┐
│  DeepSeek V4 · deepseek-v4-flash  [默认] ⋯  │ ← 和基础设置同一条
│  SenseNova  · sensenova-6.7...        ⋯     │
└──────────────────────────────────────────────┘

┌─ 本地模型配置 ──── [+ 添加] ────────────────┐
│  Ollama · qwen2.5:14b  [默认]  [编辑] [删除] │
└──────────────────────────────────────────────┘

┌─ AI 模型分配 ─────────────────────────────┐
│  每日分析 [DeepSeek V4 (在线)     ▼]       │ ← 下拉列出所有模型
│  画像分析 [Ollama (本地)          ▼]       │   按类型分组，标注 [默认]
│  未选择时兜底：日报→在线默认，画像→在线默认 │
└────────────────────────────────────────────┘

┌─ 管道执行参数 ───────── 重试/超时/熔断 ──────┐
┌─ 在线模型超时 & 重试 ────────────────────────┐
┌─ 报告生成参数 ───────────────────────────────┐
┌─ 周期报告阈值 ───────────────────────────────┐
┌─ GPU 分布式锁 ───────────────────────────────┐
┌─ 过滤词管理 ─────────────────────────────────┐
┌─ 其他（画像/日志/WeFlow/轮询/提示词）────────┐
```

### 6. AI 模型选择的兜底链

日报和画像分析时的模型选择逻辑：

```
用户指定了 model_id → 使用指定模型
未指定              → 使用在线默认（is_default=1 的 online 模型）
在线模型调用失败     → local_llm_enabled=true 时降级到本地默认
                      local_llm_enabled=false 时返回错误
本地子任务重试       → 本地默认，失败再用 local_llm_fallback_model
```

### 7. 数据一致性

- 基础设置编辑的是 `is_default=1` 的 online 模型
- 高级选项"在线模型配置"列表展示所有 online 模型，`is_default=1` 的标 `[默认]`
- 高级选项可新增/编辑/删除在线模型，设为默认的操作与当前 `setDefaultModel` API 一致
- 两边编辑同一默认模型时，通过 `model_configs` CRUD API 自然同步

### 8. 任务记录：无群时显示全部

```javascript
// TaskHistory.vue / routers
if (group_id) → filter by group_id
else → show all tasks
```

### 9. 降级门控

所有在线→本地降级路径在进入本地管线前检查 `config.LOCAL_LLM_ENABLED`。

### 8. 配置加载链 + 迁移（不变）

`config.py → DB app_settings → load_app_settings_to_config()`。
`_migrate_v1_17_0()` 检测已有本地模型记录，自动设置 `local_llm_enabled=true`。

### 9. 更新检查（不变）

`updater.py` Gitee 优先。

## Risks / Trade-offs

- **[风险] Header nav 按钮排序/可点击问题**：之前修改设置按钮导航时，切换有群/无群导致按钮排序错乱、不可点击。→ **缓解**：设置按钮始终在 DOM 中独立渲染（不用 v-if），群相关按钮用 `<template v-if>` 包裹。Vue 的 `<template>` 条件渲染不会引入额外 DOM 节点，避免兄弟元素重排。

- **[风险] 旧用户升级时本地模型被误关**：迁移检测 `model_configs WHERE model_type='local' COUNT > 0`。由于默认种子数据包含一条 local 记录，任何启动过的历史 DB 都会检测到。使用 `ON CONFLICT DO UPDATE SET value='true'` 确保覆盖 `_seed_app_settings` 先写入的 false。

- **[取舍] 基础设置无模型列表**：小白用户无法管理多个模型。→ **取舍**：符合目标用户画像，高级用户在高级选项中管理多模型。

## Open Questions

- 无
