# CLAUDE.md

## ⚠️ 数据保护红线

- **严禁操作生产数据**：`data/` 下文件是用户数据，不得删除、修改、清空，除非用户明确说可以。
- **发行版更新**：不得使旧版用户数据丢失或程序崩溃。部署只替换代码，不动 `data/` 和 `config.json`。
- **测试**：用 `test-group` 或创建新群，不动已有群的数据。
- **本地开发端口**：8857。启动：`python -m uvicorn main:app --host 0.0.0.0 --port 8857`

## 项目概况

Chat-Miner — 微信/QQ 群聊分析工具。用户上传导出 JSON，AI 生成每日报告和群友画像。Vue3 SPA 前端，FastAPI 后端，SQLite 存储。v1.17.x 起在线模型为主力，本地 Ollama 默认关闭。

## WSL 生产部署

```bash
# 部署前确认无分析任务运行中
wsl -d DebianDev -- sh -c "rsync -av --delete \
  --exclude='.git' --exclude='node_modules' --exclude='frontend/node_modules' \
  --exclude='__pycache__' --exclude='data' --exclude='logs' --exclude='venv' \
  --exclude='config.json' --exclude='docs' --exclude='*.tar.gz' \
  /mnt/c/mycode/chat-miner/ /home/zhaohaosen/applications/chat-miner/ && \
  cd /home/zhaohaosen/applications/chat-miner/frontend && npm run build && \
  sudo systemctl restart chat-miner && echo 'Deploy OK'"

# 服务管理
sudo systemctl status chat-miner
sudo systemctl restart chat-miner
sudo journalctl -u chat-miner -f
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
- **前端状态**：`provide/inject` — `currentGroup`, `triggerRefresh`, `activeTaskId`
- **前端路由**（Hash）：`/` 仪表盘, `/report/:date`, `/portraits`, `/portrait/:memberId`, `/weekly/:weekId`, `/monthly/:monthId`, `/annual/:yearId`, `/fishpond`, `/fish-report/:date`, `/settings`, `/tasks`
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
