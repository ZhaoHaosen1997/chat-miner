# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Chat-Miner is a WeChat group chat analysis tool. Users upload exported chat JSON files, and a local Ollama AI model generates daily reports (topics, funny quotes, mood, keywords) and member portraits (personality, speaking style, role, interests). Output is a Vue3 web dashboard on port 8856.

## How to run

```bash
# Install deps
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Dev mode (two terminals)
python -m uvicorn main:app --host 0.0.0.0 --port 8856
cd frontend && npx vite --port 5173

# Or one-click: start.bat

# Production: frontend → npm run build → static/ served by FastAPI
```

Open `http://localhost:5173` for frontend dev (Vite proxy → backend 8856). API docs at `http://localhost:8856/docs`.

## Core architecture

**Data flow**: JSON file → `services/parser.py` (chunk messages by day) → `services/analyzer.py` (call Ollama API) → SQLite cache → FastAPI JSON → Vue3 dashboard.

**Chunking**: Messages grouped by `formattedTime[:10]`. Worst case day is ~13K tokens — safe for any modern model. Dedup by `platformMessageId` on re-import.

**AI calls**: Every Ollama call goes through `services/analyzer.py:call_ollama_chat()`. This is the single integration point. It wraps GPU lock acquisition (`services/gpu_lock.py`), sets `keep_alive: 0` for session isolation, and optionally reports progress via `TaskInfo` updates.

**Async tasks**: `services/task_manager.py` is an in-memory singleton. Analysis requests create a `TaskInfo`, run in background via `asyncio.create_task()`, and stream progress through SSE (`GET /api/tasks/{id}/stream`). The frontend `ProgressPanel.vue` subscribes via `EventSource`.

**Database**: Single SQLite file at `data/chat_miner.db`. Tables: `chat_groups`, `group_members`, `daily_reports`, `member_portraits`, `analysis_log`. All tables keyed by `group_id` with `ON DELETE CASCADE`. `member_portraits` has migration logic in `init_db()` for backward-compatible schema changes.

**Multi-group**: Each group is an independent entity. Portrait analysis does NOT cross groups. The global `_chat_cache` dict in `routers/groups.py` caches `ParsedChat` objects by `group_id`.

**GPU lock**: `services/gpu_lock.py` talks to Dashboard (port 8850) via HTTP. Before any Ollama call: check → wait → acquire → run → release. Graceful degradation if lock service is unreachable. Configurable via `.env`.

## Key patterns

- **API response format**: `{"code": 200, "message": "...", "data": {...}}`
- **Config**: `.env` → `config.py:Config` class. Never hardcode secrets or URLs.
- **Frontend state sharing**: `provide/inject` for `currentGroup`, `triggerRefresh`, `activeTaskId`.
- **Frontend router**: Hash-based (`createWebHashHistory`), 3 routes: `/`, `/report/:date`, `/portraits`.
- **Vue template imports**: Lucide icons used in `<template>` trigger false-positive "unused import" hints from the TS analyzer. Ignore them.
- **JSON parsing safety**: All message content access uses `(m.get("content") or "").strip()` because `content` can be `None`.
- **Git**: Commit in Chinese with version tag. Do NOT commit `.env` or `docs/` (contains personal chat data).

## Input JSON format

```json
{
  "session": { "nickname": "群名", "wxid": "...", "messageCount": 31192 },
  "senders": [{ "senderID": 1, "displayName": "昵称", "avatar": "url" }],
  "messages": [{
    "localId": 1, "createTime": 1740271101,
    "formattedTime": "2025-02-23 08:38:21",
    "type": "文本消息", "content": "消息内容",
    "senderID": 1, "platformMessageId": "32751..."
  }]
}
```

Message types include: 文本消息, 图片消息, 表情消息, 语音消息, 系统消息, 引用消息, 视频消息. Only 文本消息 and 引用消息 are fed to AI.
