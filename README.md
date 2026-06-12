# Chat-Miner — 群聊内容挖掘机

基于本地 Ollama / 在线大模型的群聊分析工具。导入微信/QQ 聊天记录，自动生成日报、周报、月报、年报、群友画像、关系网络和趣味内容。

> **当前版本**: v0.12.5  
> **技术栈**: FastAPI + SQLite + Vue3 + TailwindCSS + Ollama + DeepSeek / OpenAI 兼容 API

---

## 功能一览

### 📊 每日报告
- 8 步智能分析管线（本地模型）或单次调用（在线模型）
- 话题提取、关键词、情绪识别、emoji
- 搞笑发言精选 + AI 犀利吐槽
- 综艺体标题 + 名场面花字点评
- 24 小时活跃度分析

### 📅 周报 / 月报
- 自然周 / 自然月报告，支持历史回溯
- 在线模型深度推理：话题演化、群聊人格鉴定、梗文化考古、社群健康评分
- Python 预统计 + 匿名化采样，原始聊天不出本地
- 情绪自适应配色，杂志风格排版

### 🎉 年度报告
- AI 生成年度主题 + 年度叙事
- 12 奖项绑定群友（金句王、深夜守夜人、潜水冠军…）
- 时光轴、词云、颁奖典礼
- 仅支持在线模型（需深度推理能力）

### 👤 群友画像
- 基础画像：性格标签、说话风格、群内角色、兴趣、活跃时段、口头禅、人设描述
- 深度画像：情绪特征、语言风格洞察、变化趋势
- **在线模型一次生成完整画像**（含深度分析），本地模型分步管线
- Python 统计补强：24h 热力图、消息长度分布、常用表情、高频词
- 社交关系网络：互动排行 + AI 关系类型判断
- 群友考古：第一条发言、最长发言、历史今日
- 趣味称号 + 关系解读

### ⚙️ 模型配置（v0.12 新增）
- **设置页面**：CRUD 管理多个本地 Ollama 和在线 API 模型
- 支持 OpenAI 兼容 API（DeepSeek、OpenAI、自定义代理等）
- 每日分析、画像分析可**独立指定默认模型**（本地或在线）
- 在线模型失败自动降级到本地，进度面板醒目提示
- `.env` 自动播种到数据库，向后兼容

### 🐟 群鱼塘
- 养鱼游戏化：22 种水生生物 + 六维属性 + 掷骰检定
- 11 个斜杠指令、每日结算、天气系统、进化
- 鳞币经济、黑市系统、40+ 件道具
- 鱼塘日报（在线模型生成）

---

## 架构概览

```
微信/QQ聊天记录 JSON
       │
       ▼
  parser.py        ←── 格式检测 + 归一化 + wxid 注入 + 按天分块
       │
       ├──→ pipelines.py     ←── 本地：多步子任务 Pipeline / 在线：单次 JSON 调用
       │       │
       │       ├──→ analyzer.py        ←── Ollama API（本地模型）
       │       └──→ online_model.py    ←── OpenAI 兼容 API（在线模型）
       │                    │
       │                    ▼
       │               SQLite 缓存      ←── 日报/画像/周报/月报/年报持久化
       │
       ├──→ stats_engine.py  ←── Python 纯计算（活跃/语言/关系/情绪）
       ├──→ social.py        ←── AI 关系判断
       │
       └──→ FastAPI ──→ Vue3 SPA       ←── 前后端同端口 8856
```

**设计原则**：Python 做统计，AI 做总结。在线模型一次出结果，本地模型分步保稳定。

---

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/)（本地模型）或在线 API Key（DeepSeek/OpenAI）

### 安装
```bash
git clone <repo-url>
cd chat-miner
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 配置
```bash
cp .env.example .env
# 编辑 .env 设置 Ollama 地址、端口等
# 可选：设置 DEEPSEEK_API_KEY 启用在线模型
```

### 开发模式
```bash
# 终端1: 后端
python -m uvicorn main:app --host 0.0.0.0 --port 8857

# 终端2: 前端 (热更新)
cd frontend && npx vite --port 5173
```

访问 `http://localhost:5173`

### 生产模式
```bash
cd frontend && npm run build
python -m uvicorn main:app --host 0.0.0.0 --port 8856
```

---

## 模型配置

项目支持两种模型类型，可在设置页面（`/settings`）灵活管理：

| 类型 | 用途 | 默认模型 |
|------|------|---------|
| 本地 (Ollama) | 日报、画像（分步管线，稳定可靠） | `qwen2.5:14b` |
| 在线 (API) | 日报、画像、周报、月报、年报（单次调用，更快更深） | `deepseek-v4-flash` |

- 每日分析、画像分析可独立选择默认模型
- 年报强制使用在线模型
- 在线模型失败自动降级到本地

---

## 输入格式

### 微信聊天记录

使用 [WeFlow](https://github.com/Shuax/WeFlow) 工具导出聊天记录，选择 **ArkMe JSON** 格式。导出后在前端上传 JSON 文件即可导入。

### QQ 聊天记录

使用 [qq-chat-exporter](https://github.com/shuakami/qq-chat-exporter)（V5+）导出 JSON 格式。私聊和群聊均可导入，追加导入自动去重。

### JSON 结构示例

```json
{
  "session": { "nickname": "群名", "messageCount": 31192 },
  "senders": [
    { "senderID": 1, "displayName": "昵称", "wxid": "wxid_xxx" }
  ],
  "messages": [
    {
      "localId": 1, "createTime": 1740271101,
      "formattedTime": "2025-02-23 08:38:21",
      "type": "文本消息", "content": "消息内容",
      "senderID": 1
    }
  ]
}
```

---

## 项目结构

```
chat-miner/
├── main.py                   # FastAPI 入口
├── config.py                 # 配置（读取 .env）
├── stopwords.txt             # 自定义过滤词
├── models/
│   └── database.py           # SQLite CRUD + 表定义
├── services/
│   ├── parser.py             # JSON 解析 + pickle 缓存
│   ├── pipelines.py          # AI 管线（本地分步 + 在线单次）
│   ├── analyzer.py           # Ollama API 调用
│   ├── online_model.py       # OpenAI 兼容 API 调用
│   ├── model_config.py       # 模型配置解析层（DB + .env 合并）
│   ├── stats_engine.py       # Python 统计（活跃/语言/关系/情绪）
│   ├── portrait.py           # 画像生成服务
│   ├── social.py             # AI 关系判断
│   ├── weekly_report.py      # 周报/月报生成引擎
│   ├── annual_report.py      # 年报 + 颁奖典礼
│   ├── task_manager.py       # 异步任务管理 + SSE 进度
│   └── gpu_lock.py           # GPU 分布式锁
├── routers/
│   ├── groups.py             # 群管理 API
│   ├── report.py             # 日报/周报/月报/年报 API
│   ├── portrait.py           # 画像 API
│   ├── settings.py           # 设置页 API（v0.12）
│   ├── stats.py              # 统计 + 健康检查 API
│   ├── tasks.py              # 任务进度 API
│   └── fish_pond.py          # 鱼塘 API
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue       # 仪表盘（日历 + 批量分析 + 热搜）
│       │   ├── DailyReport.vue     # 日报详情
│       │   ├── WeeklyReport.vue    # 周报详情
│       │   ├── MonthlyReport.vue   # 月报详情
│       │   ├── AnnualReport.vue    # 年报详情
│       │   ├── Portraits.vue       # 画像卡片列表 + 关系网络图
│       │   ├── PortraitDetail.vue  # 画像详情（6 标签页）
│       │   ├── Settings.vue        # 设置页（模型配置 + 默认群）
│       │   ├── FishPond.vue        # 群鱼塘
│       │   └── FishDailyReport.vue # 鱼塘日报
│       ├── components/
│       │   ├── Layout.vue          # 主布局（导航 + 群选择器）
│       │   ├── ProgressPanel.vue   # 右下角 SSE 进度面板
│       │   ├── GroupSelector.vue   # 群选择下拉
│       │   ├── UploadModal.vue     # 文件导入弹窗
│       │   └── WordCloud.vue       # Canvas 词云
│       └── api/
│           └── index.js            # 前端 API 封装
└── data/                     # 数据目录（不纳入版本控制）
    ├── chat_miner.db
    └── import_*/
```

---

## 部署

生产环境部署在 WSL Debian，详见 [CLAUDE.md](CLAUDE.md)。

```bash
# rsync 增量部署（推荐）
wsl -d DebianDev -- sh -c "rsync -av --delete \
  --exclude='.git' --exclude='node_modules' --exclude='frontend/node_modules' \
  --exclude='__pycache__' --exclude='data' --exclude='logs' --exclude='venv' \
  --exclude='.env' --exclude='docs' \
  /mnt/c/mycode/chat-miner/ /home/zhaohaosen/applications/chat-miner/ && \
  cd /home/zhaohaosen/applications/chat-miner/frontend && npm run build && \
  sudo systemctl restart chat-miner"
```

---

## 版本历史

| 版本 | 亮点 |
|------|------|
| v0.12 | 模型配置系统：设置页面 + 多模型管理 + 在线模型日报/画像单次调用 |
| v0.11 | 年度报告：AI 生成 + 12 奖项绑定群友 + 时光轴 + 词云 |
| v0.10 | 前端全面重设计：群聊杂志风格 + 情绪自适应主题 + 关系网络图 |
| v0.9 | 群鱼塘 D&D 完整版：黑市 + 道具 + 日报 + 指令模拟器 |
| v0.8 | QQ 聊天记录导入（QQChatExporter V5 格式适配）|
| v0.7 | 周报/月报 + DeepSeek 深度推理 + 脱敏架构 |
| v0.6 | 热搜榜 + 关系图 + 群友考古 |
| v0.5 | 深度画像 + Python 统计引擎 + 趣味称号 |
| v0.4 | 多任务 Pipeline + SSE 进度推送 |
| v0.1-0.3 | 基础框架 + 日报/画像 + 多群管理 |

详见 [ROADMAP.md](ROADMAP.md)

---

## License

MIT
