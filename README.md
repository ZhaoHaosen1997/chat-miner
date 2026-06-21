# Chat-Miner — 群聊内容挖掘机

基于在线大模型（主力）/ 本地 Ollama（兜底）的群聊分析工具。导入微信/QQ 聊天记录，自动生成日报、周报、月报、年报、群友画像和趣味内容。

> **当前版本**: v1.18.8
> **技术栈**: FastAPI + SQLite + Vue3 + TailwindCSS + DeepSeek / OpenAI 兼容 API + Ollama

---

## 功能一览

### 📰 事件探测
- 自适应尖峰检测 + 时间间隔窗口切分，自动识别群聊中的关键事件
- 6 种事件类型：决策、讨论、社交、公告、梗诞生、开车
- 事件时间轴仪表盘直展，一键分析 / 重新扫描
- AI 故事化叙述：起因、经过、高潮、余波

### 📊 每日报告
- 在线模型单次 JSON 调用（主力），本地模型 8 步分步管线（降级）
- 话题提取、关键词、情绪识别、emoji 情绪标签
- 搞笑发言精选 + AI 犀利吐槽
- 综艺体标题 + 名场面花字点评
- 24 小时活跃度分析

### 📖 群梗百科
- AI 扫描群聊发现群内自创梗 / 黑话
- 人工审核机制：AI 发现候选，人工确认收录
- 已收录的梗自动注入日报 / 周报 / 月报 / 事件 Prompt，帮助 AI 理解群聊上下文
- 独立 `/memes` 页面，仪表盘卡片入口 + 待审核提示

### 📅 周报 / 月报
- 自然周 / 自然月报告，支持历史回溯
- 在线模型深度推理：群聊头条、AI 锐评、奖项颁发、群聊故事、话题演变、群聊人格鉴定、梗文化考古、社群健康评分
- 情绪自适应配色，杂志风格排版
- 生成完成后自动跳转报告页

### 🎉 年度报告
- AI 生成年度主题 + 年度叙事
- 12 奖项绑定群友（金句王、深夜守夜人、潜水冠军…）
- 时光轴、词云、颁奖典礼

### 👤 群友画像
- 基础画像：性格标签、说话风格、群内角色、兴趣、活跃时段、口头禅、人设描述
- 深度画像（在线模型）：情绪特征、语言风格洞察、变化趋势
- Python 统计补强：24h 热力图、消息长度分布、常用表情、高频词
- 社交关系网络：互动排行 + AI 关系类型判断

### 🔄 WeFlow 同步
- 微信聊天记录持续同步，增量合并
- 定时任务自动拉取 + 手动触发
- 消息去重 + 发送人合并

### 🐟 群鱼塘
- 养鱼游戏化：22 种水生生物 + 六维属性 + 掷骰检定
- 斜杠指令、每日结算、天气系统、进化、黑市

### ⚙️ 灵活配置
- 多模型管理：在线 API + 本地 Ollama，可独立指定日报 / 画像默认模型
- 可配置 Prompt：日报 / 画像 / 事件探测系统提示词可自定义
- 过滤词管理：高频词统计 + AI 分析双层面过滤
- 在线模型失败自动降级到本地

---

## 架构概览

```
微信/QQ聊天记录 JSON / WeFlow 同步
       │
       ▼
  parser.py        ←── 格式检测 + 归一化 + 发送人映射 + pickle 缓存 + 按天分块
       │
       ├──→ pipelines.py       ←── 日报管线（在线单次 JSON / 本地 8 子任务分步）
       ├──→ weekly_report.py   ←── 周报/月报管线（Python 统计 + AI 深度推理）
       ├──→ annual_report.py   ←── 年报管线（月报摘要聚合 + AI 生成）
       ├──→ event_detector.py  ←── 事件探测（Python 尖峰检测 + AI 叙述）
       ├──→ portrait.py        ←── 画像生成（在线单次 / 本地分步）
       ├──→ memes.py           ←── 梗百科（AI 扫描 + 人工审核 + 上下文注入）
       │
       ├──→ desensitize.py     ←── 脱敏层：PII 过滤 + senderID 匿名化 + 昵称恢复
       ├──→ stats_engine.py    ←── Python 纯计算（活跃/语言/关系/情绪）
       ├──→ online_model.py    ←── OpenAI 兼容 API 调用层
       ├──→ analyzer.py        ←── Ollama 本地模型调用层
       │
       └──→ FastAPI ──→ Vue3 SPA       ←── 前后端同端口 8856
```

**设计原则**：Python 做统计，AI 做总结。发送人全链路匿名化（stable_id），AI 返回后恢复昵称。在线模型主力，本地模型兜底。

---

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/)（本地降级用）或在线 API Key（DeepSeek / OpenAI 兼容）

### 安装
```bash
git clone <repo-url>
cd chat-miner
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 开发模式
```bash
# 终端1: 后端
python -m uvicorn main:app --host 0.0.0.0 --port 28856

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

## 输入格式

### 微信聊天记录
使用 [WeFlow](https://github.com/Shuax/WeFlow) 工具导出聊天记录，选择 **ArkMe JSON** 格式。或通过 WeFlow 同步功能持续拉取。

### QQ 聊天记录
使用 [qq-chat-exporter](https://github.com/shuakami/qq-chat-exporter)（V5+）导出 JSON / ZIP 格式。私聊和群聊均可导入，追加导入自动去重。

---

## 项目结构

```
chat-miner/
├── main.py                     # FastAPI 入口
├── config.py                   # 配置 + 版本号
├── models/
│   └── database.py             # SQLite CRUD + 表定义 + 迁移
├── services/
│   ├── parser.py               # JSON 解析 + pickle 缓存
│   ├── pipelines.py            # 日报管线（在线 + 本地）
│   ├── weekly_report.py        # 周报/月报管线
│   ├── annual_report.py        # 年报管线
│   ├── event_detector.py       # 事件探测管线
│   ├── portrait.py             # 画像生成
│   ├── desensitize.py          # 脱敏层（PII + senderID + 梗百科前缀）
│   ├── stats_engine.py         # Python 统计（活跃/语言/关系/情绪）
│   ├── online_model.py         # OpenAI 兼容 API 调用
│   ├── analyzer.py             # Ollama 本地模型调用
│   ├── model_config.py         # 模型配置解析
│   ├── task_manager.py         # 异步任务 + SSE 进度
│   └── gpu_lock.py             # GPU 分布式锁
├── routers/
│   ├── groups.py               # 群管理
│   ├── report.py               # 日报
│   ├── portrait.py             # 画像
│   ├── events.py               # 事件
│   ├── event_windows.py        # 事件窗口
│   ├── memes.py                # 梗百科
│   ├── stats.py                # 统计 + 健康检查
│   ├── settings.py             # 设置页
│   ├── tasks.py                # 任务进度
│   ├── weflow.py               # WeFlow 同步
│   └── fish_pond.py            # 鱼塘
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue         # 仪表盘
│       │   ├── DailyReport.vue       # 日报详情
│       │   ├── WeeklyReport.vue      # 周报详情
│       │   ├── MonthlyReport.vue     # 月报详情
│       │   ├── AnnualReport.vue      # 年报详情
│       │   ├── EventDetail.vue       # 事件详情
│       │   ├── MemeEncyclopedia.vue  # 梗百科
│       │   ├── Portraits.vue         # 画像卡片列表
│       │   ├── PortraitDetail.vue    # 画像详情
│       │   ├── ComprehensivePortrait.vue
│       │   ├── Settings.vue          # 设置页
│       │   ├── FishPond.vue          # 群鱼塘
│       │   └── TaskHistory.vue       # 任务记录
│       ├── components/
│       │   ├── Layout.vue            # 主布局
│       │   ├── FloatingNav.vue       # 浮动导航（←→ 翻页 + ESC 返回）
│       │   ├── GroupSelector.vue     # 群选择器
│       │   ├── UploadModal.vue       # 导入弹窗
│       │   ├── WeFlowImportModal.vue # WeFlow 同步弹窗
│       │   ├── WordCloud.vue         # Canvas 词云
│       │   └── RelatedEvents.vue     # 关联事件
│       └── api/
│           └── index.js              # 前端 API 封装
└── data/                       # 数据目录（不纳入版本控制）
```

---

## 版本历史

| 版本 | 亮点 |
|------|------|
| v1.18.8 | 群梗百科审核机制 + 独立页面 + 仪表盘互斥锁统一 + 报告生成跳转 + ESC 快捷键 |
| v1.18.7 | WeFlow 同步优化 — 数据覆盖修复 + 定时同步完善 + 平台校验 |
| v1.18.5 | QQ 群解析兼容 + 事件门槛优化 + senderID 稳定化 + NSIS 升级检测 |
| v1.18.3 | 事件降级 + 热搜 + 群梗百科 + 梗百科注入 + 词云 |
| v1.18.2 | 事件丰富化 + 仪表盘集成 |
| v1.18.1 | 事件两步拆分（窗口扫描 → AI 分析分离） |
| v1.18.0 | 事件探测系统 |
| v1.17 | 本地大模型高级化 + 设置全局重构 |
| v1.16 | 静默鱼塘（精力系统 + 性格 + Emoji 多态）+ 塘主经营 + 关系网 + 季节 |
| v1.5 | 跨群身份 + QQ 平台 + 可配置提示词 + 全面画像 |

详见 [ROADMAP.md](ROADMAP.md)

---

## 部署

生产环境部署在 WSL Debian，详见 [CLAUDE.md](CLAUDE.md)。

---

## License

MIT
