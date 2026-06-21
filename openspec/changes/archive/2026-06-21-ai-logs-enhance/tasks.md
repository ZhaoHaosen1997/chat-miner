## 1. 数据库迁移

- [x] 1.1 `ai_call_logs` 新增 `input_chars INTEGER DEFAULT 0` 列
- [x] 1.2 `ai_call_logs` 新增 `output_chars INTEGER DEFAULT 0` 列
- [x] 1.3 `_migrate_db` 加 try/except ALTER TABLE 兼容旧表

## 2. 后端：日志字段计算

- [x] 2.1 `AILogger.log()` 计算 `input_chars = len(system_prompt) + len(user_prompt)`，`output_chars = len(response_raw)`，写入数据库
- [x] 2.2 `add_ai_call_log` 函数签名新增 `input_chars` 和 `output_chars` 参数
- [x] 2.3 `call_online_chat` 中传给 `AILogger.log()` 的参数适配新字段

## 3. 后端：事件管线补传 group_id

- [x] 3.1 `_call_ai_for_events` 函数签名新增 `group_id: int = 0` 参数
- [x] 3.2 两处 `call_online_chat` 调用（主模型 + fallback）传入 `group_id=group_id`
- [x] 3.3 `_analyze_window_with_ai` 调用 `_call_ai_for_events` 时传入 `group_id=group_id`

## 4. 后端：单窗口事件分析生成任务记录

- [x] 4.1 `api_analyze_window` 中创建 `event_window` 类型 task record（`task_manager.create("event_window", group_id, ...)`)
- [x] 4.2 分析完成后更新 task 状态（成功/失败），记录耗时至 `task_records`
- [x] 4.3 完成后 `task.finish(success=True/False)`

## 5. 后端：API 分页

- [x] 5.1 `/api/ai-logs` 端点支持 `offset` 查询参数（默认 0）
- [x] 5.2 `get_ai_call_logs` 函数签名新增 `offset` 参数
- [x] 5.3 API 返回 `{"code": 200, "data": {"logs": [...], "total": N}}` 含总数便于前端分页

## 6. 前端：AiCallLogs 改造为 Settings Tab 组件

- [x] 6.1 AiCallLogs.vue 移除页面 chrome（返回按钮、独立 header），改为纯内容组件
- [x] 6.2 列表每行新增 `input_chars` / `output_chars` 显示（如 "入 4.2k / 出 1.8k"）
- [x] 6.3 添加分页控件（上一页/下一页，显示当前页/总页数）
- [x] 6.4 移除硬编码 `limit: 50`，改为 page/offset 驱动

## 7. 前端：Settings 新增 AI 日志 Tab

- [x] 7.1 Settings.vue `activeTab` 新增 `'aiLogs'` 值
- [x] 7.2 Tab 栏新增"AI日志"按钮
- [x] 7.3 `activeTab==='aiLogs'` 时渲染 AiCallLogs 组件
- [x] 7.4 Settings 引入并注册 AiCallLogs 组件

## 8. 前端：移除独立路由

- [x] 8.1 `main.js` 删除 `/ai-logs` 路由和 AiCallLogs 的 route-level import
- [x] 8.2 确认无其他页面通过 `router.push('/ai-logs')` 跳转

## 9. 前端：TaskHistory 弹窗查看 AI 日志 + 事件分析类型

- [x] 9.1 TaskHistory.vue 新增 `showAiLogsModal` / `aiLogsForTask` 状态
- [x] 9.2 "查看 AI 调用日志"链接从 `<router-link>` 改为 `@click` 打开弹窗
- [x] 9.3 Modal 内调用 `getAiCallLogs({task_id: r.id, limit: 100})` 加载日志
- [x] 9.4 Modal 内渲染简化日志列表（pipeline, model, 入/出长度, duration, success, time）
- [x] 9.5 Modal 内单条日志展开查看 prompt/response（复用 formatJSON 逻辑）
- [x] 9.6 类型筛选下拉新增"事件分析"选项（覆盖 `event_window` + `event_window_batch`）
- [x] 9.7 TYPE_MAP 新增 `event_window` 和 `event_window_batch` 映射

## 10. 验证

- [x] 10.1 启动 `uvicorn main:app --port 28856`，确认数据库迁移无报错
- [x] 10.2 触发一次单窗口事件分析，确认 `task_records` 新增 `event_window` 记录
- [x] 10.3 检查 `ai_call_logs` 表事件相关记录含 group_id
- [x] 10.4 前端 Settings → AI日志 tab，确认分页和长度字段正常展示
- [x] 10.5 任务记录筛选"事件分析"，确认显示单窗口+批量任务
- [x] 10.6 任务记录展开分析类任务，点"查看 AI 调用日志"弹窗展示
