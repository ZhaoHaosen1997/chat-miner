# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ 数据保护红线

- **严禁操作生产数据**：`data/` 目录下的 `chat_miner.db` 和 `merged_data.json` 是用户数据。
- 不得删除、修改、清空 `data/` 下的任何文件，除非用户**明确说**"可以清数据""导入流程会重建""开发阶段数据可以舍弃"。
- 部署更新时只替换代码文件，不动 `data/` 和 `.env`。
- 测试新功能时用 `test-group` 或创建新群，不要动已有群的数据。

## Project overview

Chat-Miner is a WeChat group chat analysis tool. Users upload exported chat JSON files, and a local Ollama AI model (qwen2.5:14b) generates daily reports and member portraits. Vue3 SPA frontend served on port 8856.

**Version**: 0.5.1 (deployed to WSL DebianDev)

## WSL 生产部署

```bash
# 目标环境
WSL 发行版: DebianDev
部署路径: /home/zhaohaosen/applications/chat-miner/
Python: venv 在项目目录下 venv/
服务名: chat-miner.service

# 部署更新（只更新代码，不动数据）
cd /mnt/c/mycode/chat-miner
tar --exclude='.git' --exclude='node_modules' --exclude='frontend/node_modules' \
    --exclude='__pycache__' --exclude='data' --exclude='logs' --exclude='venv' \
    --exclude='.env' -czf /mnt/c/mycode/chat-miner-deploy.tar.gz .
wsl -d DebianDev -- tar -xzf /mnt/c/mycode/chat-miner-deploy.tar.gz \
    -C /home/zhaohaosen/applications/chat-miner/
wsl -d DebianDev -- sh -c "cd /home/zhaohaosen/applications/chat-miner/frontend && npm run build"
wsl -d DebianDev -- sudo systemctl restart chat-miner

# 服务管理
sudo systemctl status chat-miner   # 查看状态
sudo systemctl restart chat-miner  # 重启
sudo systemctl stop chat-miner     # 停止
sudo journalctl -u chat-miner -f   # 查看日志
```

**访问**：`http://localhost:8856`（前后端同端口，静态文件由 FastAPI 托管）

## How to run (dev)

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Dev mode (two terminals)
python -m uvicorn main:app --host 0.0.0.0 --port 8856
cd frontend && npx vite --port 5173
# Or one-click: start.bat

# Production: frontend → npm run build → served by FastAPI
```

## Core architecture

**Data flow**: JSON file → `services/parser.py` (inject wxid, chunk by day) → `services/pipelines.py` (multi-step AI sub-tasks) → `services/analyzer.py:call_ollama_chat()` → SQLite cache → FastAPI JSON → Vue3 dashboard.

**Member identity**: Every message gets a `wxid` field injected at load time (`ParsedChat.load()`). All downstream code filters by `m["wxid"]` — never by `senderID` (which is an export-tool transient ID). `group_members` table has `UNIQUE(group_id, wxid)`.

**Pipeline system** (`services/pipelines.py`):
- Daily report: 8 sub-tasks (topics → quotes → mood → keywords → oneline → active_hours → headline → scene_commentary)
- Portrait (basic): 4 sub-tasks (persona → interests → phrase → oneline_portrait)
- Portrait (deep): 5 sub-tasks (monthly slices → emotion → language → monthly synthesis) + Python stats
- Each sub-task called via `_run_sub()` with 3 retries, circuit breaker, cancellation check

**Context safety for 14B model**: Python pre-computes statistics → AI only receives structured summaries (≤300 chars per sub-task). Monthly slicing splits member history into ≤3000 char chunks. "Python 做统计，AI 做总结" is the design principle.

**AI calls**: `services/analyzer.py:call_ollama_chat()` is the single Ollama integration. Uses `keep_alive: 300` (model stays loaded 5 min during pipeline), `temperature: 0.1`, GPU lock via Dashboard port 8850.

**Async tasks**: `services/task_manager.py` in-memory singleton. SSE progress streaming at `GET /api/tasks/{id}/stream`. `ProgressPanel.vue` subscribes via `EventSource`. Cancel support: `_run_sub()` checks `task._cancelled` before each retry.

**Database**: SQLite at `data/chat_miner.db`. Tables: `chat_groups`, `group_members` (UNIQUE: group_id+wxid), `daily_reports`, `member_portraits`, `portrait_versions`, `member_interactions`, `analysis_log`, `task_records`. Migration in `_migrate_db()`.

**Portrait system**: Unified analysis (`_run_full_portrait_analysis`) does basic pipeline + Python stats + deep pipeline + fun titles. Incremental mode (`max_days=10`) preserves AI personality traits, only refreshes data stats.

**Custom stopwords**: `stopwords.txt` at project root. Loaded by `_load_user_stopwords()` each analysis run. Words here excluded from all word/emoji/personality analysis.

## Key patterns

- **API response format**: `{"code": 200, "message": "...", "data": {...}}`
- **Config**: `.env` → `config.py:Config` class. Never hardcode secrets or URLs.
- **Frontend state**: `provide/inject` for `currentGroup`, `triggerRefresh`, `activeTaskId`.
- **Frontend router**: Hash-based, routes: `/`, `/report/:date`, `/portraits`, `/portrait/:memberId`.
- **JSON parsing safety**: All message content access uses `(m.get("content") or "").strip()` because `content` can be `None`.
- **Git**: Commit in Chinese with version tag. Do NOT commit `.env` or `docs/`.

## Input JSON format

```json
{
  "session": { "nickname": "群名", "wxid": "...", "messageCount": 31192 },
  "senders": [{ "senderID": 1, "displayName": "昵称", "avatar": "url", "wxid": "wxid_xxx" }],
  "messages": [{
    "localId": 1, "createTime": 1740271101,
    "formattedTime": "2025-02-23 08:38:21",
    "type": "文本消息", "content": "消息内容",
    "senderID": 1, "platformMessageId": "32751..."
  }]
}
```

Message types: 文本消息, 图片消息, 表情消息, 语音消息, 系统消息, 引用消息, 视频消息.
Daily reports include 引用消息 (for context), portrait analysis excludes them (to avoid contamination).
Portrait analysis also excludes ultra-short messages (<2 Chinese chars) and pure confirmation messages ("1", "ok").
