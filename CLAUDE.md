# CLAUDE.md

## ⚠️ 数据保护红线

- **严禁操作生产数据**：`data/` 下文件是用户数据，不得删除、修改、清空，除非用户明确说可以。
- **发行版更新**：不得使旧版用户数据丢失或程序崩溃。部署只替换代码，不动 `data/` 和 `config.json`。
- **测试**：用 `test-group` 或创建新群，不动已有群的数据。
- **本地开发端口**：28856。启动：`python -m uvicorn main:app --host 0.0.0.0 --port 28856`

## 项目概况

Chat-Miner — 微信/QQ 群聊分析工具。用户上传导出 JSON，AI 生成每日报告和群友画像。Vue3 SPA 前端，FastAPI 后端，SQLite 存储。v1.17.x 起在线模型为主力，本地 Ollama 默认关闭。v1.19.x 完成底座重构：消息格式化共享层、PipelineContext 统一 AI 调用入口、jieba 分词、金字塔采样策略。

## WSL 生产部署

```bash
# 部署前确认无分析任务运行中
wsl -d DebianDev -- bash /mnt/c/mycode/chat-miner/deploy.sh

# 服务管理
wsl -d DebianDev -- sudo systemctl status chat-miner
wsl -d DebianDev -- sudo systemctl restart chat-miner
wsl -d DebianDev -- sudo journalctl -u chat-miner -f
```

访问：`http://localhost:8856`（前后端同端口）

## 开发运行

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
# 双终端：uvicorn + vite，或 start.bat 一键启动
```

## 关键模式

- **API 响应**：`{"code": 200, "message": "...", "data": {...}}`
- **配置体系**：`config.py`（兜底）→ DB `app_settings`（可热更新）。新增配置项需同时更新 `_SETTINGS_DEFS` 和 `KEY_ATTR_MAP`。
- **消息格式化**：`services/message_formatter.py` 统一 PII 过滤 + stable_id 映射 + 内容截断。各管线（日报/画像/事件/梗百科）调用共享函数，不再各自实现。
- **PipelineContext**：`services/pipeline_context.py` 统一 AI 调用入口，自动注入 task_id + ai_logger 参数。新增管线必须通过 `PipelineContext.call_online()` / `call_local()` 调用 AI。
- **AI 调用日志**：`services/ai_logger.py` 记录所有 AI 调用的 Prompt、响应、Token、耗时、状态。前端设置页「AI 日志」tab 查看。
- **采样策略**：`services/sampler.py` 金字塔压缩——日报用原始消息，周报用日报 one_line 摘要，月报用周报 headline，年报用月报 headline。不再使用 interestingness 评分。
- **前端状态**：`provide/inject` — `currentGroup`, `triggerRefresh`, `activeTaskId`
- **前端路由**（Hash）：`/` 仪表盘, `/report/:date`, `/portraits`, `/portrait/:memberId`, `/weekly/:weekId`, `/monthly/:monthId`, `/annual/:yearId`, `/fishpond`, `/fish-report/:date`, `/event/:eventId`, `/memes`, `/comprehensive/:personaId`, `/settings`, `/tasks`
- **JSON 安全**：消息内容一律 `(m.get("content") or "").strip()`
- **设计原则**："Python 做统计，AI 做总结" — AI 只接收 ≤300 字符的结构化摘要

## Git

- 提交中文 + 版本 tag。禁止提交 `docs/`。用户确认测试通过后再 commit。
- 版本号：新功能大版本独立提交，bug fix 最后一位 +1。
- **双推**：`origin` → 内网 Gitea（默认）+ GitHub。`github` → 仅 GitHub。

## 踩坑记录

- **bat 文件只用 ASCII**，中文在 cmd 控制台乱码。
- **nsi 文件中文需 GBK 编码**，不能用 UTF-8。
- **Git Bash `/D` 陷阱**：调用 makensis 等 Windows 工具用 `cmd //c "makensis /DVERSION=..."` 包装。
- **PyInstaller 构建后杀软锁文件**：用 Python `zipfile` 替代 PowerShell，加重试延迟。
- **`_get_merged_data_path` 是纯路径计算函数，不要加 `.exists()` 检查**。它的调用方 `sync_messages_incremental` 用它决定往哪里**写入** merged_data.json。首次 WeFlow 同步前文件尚不存在，加了存在性检查会导致 `merged_path=None`，整个写磁盘步骤被跳过，合并后的数据全丢。Code Review 时对路径函数的返回值语义要结合所有调用方判断，不能假设它是"查找已有文件"。
- **PipelineContext task_id 传递链路**：管线内调用 AI 必须通过 `PipelineContext`，否则 `ai_call_logs` 表的 `task_id` 字段为空，前端 AI 日志无法按任务筛选。直接调用 `call_online_chat()` / `call_ollama_chat()` 绕过上下文是遗留写法，新代码不应使用。
