# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ 数据保护红线

- **严禁操作生产数据**：`data/` 目录下的 `chat_miner.db` 和 `merged_data.json` 是用户数据。
- **发行版更新**：设计和开发时要考虑，发行版安装包、绿色版更新时，不得使旧版用户数据丢失、程序崩溃
- 不得删除、修改、清空 `data/` 下的任何文件，除非用户**明确说**"可以清数据""导入流程会重建""开发阶段数据可以舍弃"。
- 部署更新时只替换代码文件，不动 `data/` 和 `config.json`。
- 测试新功能时用 `test-group` 或创建新群，不要动已有群的数据。
- **本地开发端口**：8857（避免与 WSL 生产 8856 冲突）。启动命令：`python -m uvicorn main:app --host 0.0.0.0 --port 8857`

## Project overview

Chat-Miner is a WeChat/QQ group chat analysis tool. Users upload exported chat JSON files (WeChat or QQ format, auto-detected), and a local Ollama AI model (qwen2.5:14b) generates daily reports and member portraits. DeepSeek API can be configured for weekly/monthly deep reasoning reports. Vue3 SPA frontend served on port 8856.

**Version**: 1.5.0 (deployed to WSL DebianDev)

## WSL 生产部署

```bash
# 目标环境
WSL 发行版: DebianDev
部署路径: /home/zhaohaosen/applications/chat-miner/
Python: venv 在项目目录下 venv/
服务名: chat-miner.service

# ⚠️ 部署前先检查是否有运行中的分析任务！
# 如果任务正在运行，部署会中断分析造成数据不完整。
# 先在前端确认无活跃任务，或等待完成后再部署。

# 推荐：rsync 增量部署（快且安全，只传变更文件）
wsl -d DebianDev -- sh -c "rsync -av --delete \
  --exclude='.git' --exclude='node_modules' --exclude='frontend/node_modules' \
  --exclude='__pycache__' --exclude='data' --exclude='logs' --exclude='venv' \
  --exclude='config.json' --exclude='docs' --exclude='*.tar.gz' \
  /mnt/c/mycode/chat-miner/ /home/zhaohaosen/applications/chat-miner/ && \
  cd /home/zhaohaosen/applications/chat-miner/frontend && npm run build && \
  sudo systemctl restart chat-miner && echo 'Deploy OK'"

# 如果确认有任务在运行，用 reload 代替 restart（不中断正在处理的请求）
# sudo systemctl reload chat-miner  # 注意：需要服务支持 SIGHUP
# 或者等任务完成后再 restart

# 备用：tar 打包部署（兼容旧方式）
# cd /mnt/c/mycode/chat-miner
# tar --exclude='.git' --exclude='node_modules' --exclude='frontend/node_modules' \
#     --exclude='__pycache__' --exclude='data' --exclude='logs' --exclude='venv' \
#     --exclude='config.json' --exclude='docs' -czf /tmp/chat-miner-deploy.tar.gz .
# wsl -d DebianDev -- sh -c "tar -xzf /mnt/c/mycode/chat-miner-deploy.tar.gz \
#     -C /home/zhaohaosen/applications/chat-miner/ && cd /home/zhaohaosen/applications/chat-miner/frontend && npm run build && sudo systemctl restart chat-miner"
# rm -f /tmp/chat-miner-deploy.tar.gz

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

**Database**: SQLite at `data/chat_miner.db`. Tables: `chat_groups`, `group_members` (UNIQUE: group_id+wxid), `daily_reports`, `member_portraits`, `portrait_versions`, `member_interactions`, `analysis_log`, `task_records`, `periodic_reports` (周报/月报/年报), `annual_awards` (年度奖项), `app_settings` (可热更新设置), `model_configs` (AI 模型配置), `fish_pond` + `fish_events` + `scale_coin_wallet` + `scale_coin_transactions` + `fish_inventory` + `fish_black_market` (鱼塘系统). Migration in `_migrate_db()` and dedicated `_migrate_*` functions.

**Portrait system**: Unified analysis (`_run_full_portrait_analysis`) does basic pipeline + Python stats + deep pipeline + fun titles. Incremental mode (`max_days=10`) preserves AI personality traits, only refreshes data stats.

**Custom stopwords**: Managed via Settings page (stored in `app_settings` DB table). Default stopwords hardcoded in `config.DEFAULT_STOPWORDS`. Loaded by `_load_user_stopwords()` each analysis run.

## Key patterns

- **API response format**: `{"code": 200, "message": "...", "data": {...}}`
- **Config**: `config.json` (启动参数) → `config.py` (默认值) → DB `app_settings` (可热更新)。通过设置页面管理。
- **Frontend state**: `provide/inject` for `currentGroup`, `triggerRefresh`, `activeTaskId`.
- **Frontend router**: Hash-based, routes: `/` (Dashboard), `/report/:date` (日报), `/portraits` (画像列表), `/portrait/:memberId` (画像详情), `/weekly/:weekId` (周报), `/monthly/:monthId` (月报), `/annual/:yearId` (年报), `/fishpond` (鱼塘), `/fish-report/:date` (鱼日报), `/settings` (设置), `/tasks` (任务历史).
- **JSON parsing safety**: All message content access uses `(m.get("content") or "").strip()` because `content` can be `None`.
- **Git**: Commit in Chinese with version tag. Do NOT commit `docs/`.
- **提交纪律**：用户测试确认功能无误后再 commit + push。AI 不自行提交，等用户明确说"提交"。
- **版本号规则**：新功能大版本（v0.x.0）独立提交；每次提交 bug fix 时版本号最后一位 +1（如 v0.12.0 → v0.12.1），禁止两次提交使用同一个版本号。

## Input JSON format

**WeChat 格式**（微信导出工具）：
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

**QQ 格式**（QQChatExporter V5，parser.py `_normalize_qq()` 归一化）：
```json
{
  "session": { "nickname": "群名", "groupUid": "u_xxxx" },
  "senders": [{ "uid": "u_xxxx", "uin": "12345678", "nickname": "昵称" }],
  "messages": [{
    "type": "type_1", "subType": "text",
    "senderUid": "u_xxxx", "senderNickname": "昵称",
    "elements": [{ "elementType": 1, "textElement": { "content": "消息内容" } }],
    "timestamp": "2025-02-23 08:38:21"
  }]
}
```
QQ 格式归一化后：`uid` → `wxid`, `uin` → 额外保留在 `sender.uin`（v1.5.0 起存入 DB）。

Message types: 文本消息, 图片消息, 表情消息, 语音消息, 系统消息, 引用消息, 视频消息.
Daily reports include 引用消息 (for context), portrait analysis excludes them (to avoid contamination).
Portrait analysis also excludes ultra-short messages (<2 Chinese chars) and pure confirmation messages ("1", "ok").

## 踩坑记录

### bat / nsi 文件禁止中文

`build.bat`、`installer.nsi` 等 Windows 脚本文件只用 **ASCII/英文**。NSIS makensis 只认 ANSI 编码，中文注释和 Unicode 字符（如 `—` 长破折号）会直接报 `Bad text encoding` 导致构建失败。bat 脚本同理，中文在 cmd 控制台可能乱码。

### app_settings 类型陷阱

`app_settings` 表的 `value` 列是 `TEXT`，`value_type` 列标记类型（int/float/bool/string）。`load_app_settings_to_config()` 根据 `value_type` 选择转换器。

**坑**：`upsert_app_setting()` 用 `INSERT ... ON CONFLICT DO UPDATE` 时，若 key 不存在，`value_type` 走表默认值 `DEFAULT 'string'`。之后 `load_app_settings_to_config` 用 `str` 转换 → config 属性变成字符串 → `total_msgs >= "50"` → `TypeError`。

**教训**：
1. `upsert_app_setting` INSERT 时必须显式指定 `value_type`，从 `_SETTINGS_DEFS` 注册表查
2. `_seed_app_settings` 每次启动校验已有 key 的 `value_type`，错的自动修复
3. 所有数值比较处加 `int()` 防御（`compute_available_periods` 已做，`generate_*_report` 易遗漏）

### Git Bash 命令行参数 `/D` 陷阱

Git Bash 会把 `/DVERSION=1.2.8` 中的 `/D` 解释为 D: 盘路径。调用 makensis 等 Windows 原生工具时，用 `cmd //c "makensis /DVERSION=..."` 包装，避免路径转换。

### PyInstaller 构建后杀软锁文件

杀毒软件（Defender）会在 PyInstaller 刚生成 exe 时扫描，导致后续 `Compress-Archive` 读不到文件。`build.bat` 只 sleep 2 秒有时不够。用 Python `zipfile` 替代 PowerShell，加重试延迟更可靠。

### WSL 生产 DB 查询路径

```bash
# 正确：通过 bash -c 执行，WSL 内路径
wsl -d DebianDev -- bash -c "sqlite3 /home/zhaohaosen/applications/chat-miner/data/chat_miner.db 'SELECT ...'"
# 错误：直接在 wsl 命令中写 WSL 路径（Git Bash 会拼接 Windows 路径）
```
