# Chat-Miner — 群聊内容挖掘机

基于本地 Ollama AI 的群聊分析工具。支持微信/QQ 聊天记录导入，自动生成每日报告、群友画像、情绪追踪和趣味内容。

> **当前版本**: v0.9.3  
> **技术栈**: FastAPI + SQLite + Vue3 + TailwindCSS + Ollama + DeepSeek API

---

## 功能一览

### 📊 每日报告
- 话题提取、关键词、情绪识别
- 搞笑发言精选 + AI 吐槽
- 综艺体标题 + 名场面花字点评
- 24小时活跃度分析

### 👤 群友画像
- 8 个维度深度分析：性格、说话风格、群内角色、兴趣、活跃时段、口头禅
- AI 生成的个人一句话介绍 + 专属 emoji
- 深度画像：月度情绪变化、语言风格洞察、趋势总结
- Python 统计补强：24h热力图、消息长度分布、常用表情、高频词
- 社交关系网络：互动排行、关系类型判断
- 群友考古：第一条发言、最长发言、历史上的今天

### 🔥 趣味内容
- 趣味称号（如"深夜哲学家""红包闪电侠"）
- 关系解读（星座配对风格）
- 最近30天状态快照
- 话题角色标签

### 📈 周报/月报（v0.7 新增）
- 自然周/自然月报告，支持历史回溯
- DeepSeek API 深度推理：趋势提炼、氛围诊断、群友聚光灯
- 本地 14B 脱敏消化，云端模型只看到结构化摘要
- 降级策略：DeepSeek 不可用时自动降级到本地模型

### 🐟 群鱼塘（v0.9 新增）
- **养鱼游戏化**：群成员活跃度映射为鱼的成长状态
- **22种水生生物**：金鱼🐟 锦鲤🎏 鲨鱼🦈 章鱼🐙 海豚🐬 等，各有独特属性加成
- **六维属性**：力量/敏捷/体质/智力/感知/魅力，影响指令成功率
- **掷骰检定**：所有互动基于属性掷骰判定，满点大成功，1点大失败
- **11个 / 指令**：`/领养` `/喂食` `/摸鱼` `/探索` `/晒鱼` `/训练` `/斗鱼` `/鱼塘` `/购买` `/赠予` `/改名`
- **每日结算**：天气系统☀️🌧️⛈️🌈 + 自动喂食 + 进化 + 鲨鱼来袭 + 连续活跃奖励
- **鳞币经济**：探索/晒鱼/斗鱼赚取，训练属性消耗，黑市购买道具
- **黑市系统**：每日随机限时商品，先到先得抢购
- **道具系统**：40+件道具（饲料/训练/装备/幸运/特殊/收藏），装备永久加成
- **鱼塘日报**：DeepSeek 生成自然语言日报（天气+黑市+群友动态+排行榜）
- **指令模拟器**：右下角聊天面板，选成员身份模拟 / 指令，实时回显检定结果


---

## 架构概览

```
微信/QQ聊天记录 JSON
       │
       ▼
  parser.py        ←── 格式检测 + 归一化 + wxid注入 + 按天分块
       │
       ├──→ pipelines.py   ←── 多步子任务 Pipeline（拆解复杂分析）
       │       │                    每次只让 AI 做一件事
       │       ▼
       │   analyzer.py    ←── Ollama API (qwen2.5:14b)
       │       │                    GPU 分布式锁防止争抢显存
       │       ▼
       │   SQLite 缓存    ←── 日报/画像持久化
       │       │
       │       ▼ (脱敏摘要)
       │   DeepSeek API   ←── 周报/月报深度推理 (v0.7)
       │
       ├──→ stats_engine.py ←── Python 纯计算（活跃/语言/关系/情绪）
       │
       └──→ FastAPI ──→ Vue3 SPA   ←── 前后端同端口 8856
```

**设计原则**：Python 做统计，AI 做总结。14B 模型只接收 ≤300 字的结构化摘要，不直接处理原始聊天。周报/月报由 DeepSeek 基于日报摘要深度推理，原始聊天永不出本地。

---

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/) + qwen2.5:14b 模型

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
```

### 开发模式
```bash
# 终端1: 后端
python -m uvicorn main:app --host 0.0.0.0 --port 8857

# 终端2: 前端 (热更新)
cd frontend && npx vite --port 5173

# 或者双击 start.bat 一键启动
```

### 生产模式
```bash
cd frontend && npm run build
python -m uvicorn main:app --host 0.0.0.0 --port 8856
```

访问 `http://localhost:8856`

---

## 本地模型选型指南 🧠

Chat-Miner 依赖两个 AI 角色：**本地 Ollama 模型**（日报/画像）和可选的**云端模型**（周报/月报）。选对模型直接影响体验。

### 日报/画像：本地模型要求

本地模型负责从原始聊天中提取结构化信息。经过大量测试，推荐如下：

| 模型 | 参数量 | 最低显存 | 推荐场景 | 备注 |
|------|--------|----------|----------|------|
| `qwen2.5:14b` ⭐ | 14B | 8GB | **主力推荐** | 本项目开发测试用，输出稳定 |
| `qwen2.5:7b` | 7B | 4GB | 显存紧张 | 偶尔输出格式不稳定，需要 retry |
| `qwen2.5:32b` | 32B | 20GB | 追求质量 | 推理速度慢（5-10s/次），但更准 |
| `qwen3:14b` | 14B | 8GB | 可尝试 | 注意：qwen3 默认开启 thinking，会大幅增加推理时间 |

> ⚠️ **关键坑**：`qwen3` 系列默认开启思考模式（thinking/CoT），模型会先生成大量思考 token 再输出答案。这会导致：
> 1. 推理时间翻倍甚至更久
> 2. 思考内容撑爆上下文窗口（默认 2048 tokens），输出截断
>
> 如果一定要用 qwen3，建议在 Ollama 创建自定义 Modelfile 关闭 thinking：
> ```
> FROM qwen3:14b
> PARAMETER num_predict 1024
> ```
> 本项目已内置 `num_predict: 1024` 限制输出 token 数，对 qwen3 等 thinking 模型有保护作用。

### 周报/月报：云端模型（可选）

周报/月报需要跨天推理和叙事生成，本地 14B 力不从心。推荐配置 DeepSeek API：

| 模型 | 用途 | 特点 |
|------|------|------|
| `deepseek-chat` / `deepseek-v4-flash` | 周报 | 速度快、便宜、中文理解好 |
| `deepseek-reasoner` | 月报 | 深度推理，但更慢更贵 |

如果不想配置云端 API，周报/月报会自动降级到本地模型，效果会打折扣但不影响使用。

### Ollama 安装与模型拉取

```bash
# 安装 Ollama（Linux / WSL）
curl -fsSL https://ollama.com/install.sh | sh

# 拉取推荐模型
ollama pull qwen2.5:14b

# 验证
ollama list
```

### 常见踩坑

| 问题 | 原因 | 解决 |
|------|------|------|
| 推理巨慢（>30s/次） | 模型跑在 CPU 上 | 确认 Ollama 检测到 GPU：`ollama ps` 或用 `nvidia-smi` 看显存占用 |
| 输出格式错乱/JSON 解析失败 | 模型太小（7B 以下） | 换 14B+ 模型，模型太小跟不住指令 |
| WSL 中 Ollama 连不上 | WSL 默认 localhost 不通 | 用 Windows 宿主 IP 或 `host.docker.internal` 替代 `localhost` |
| 显存被其他应用占满 | ComfyUI/Stable Diffusion 等 | 已内置 GPU 分布式锁（依赖 Dashboard 8850 端口），无锁服务时自动降级 |
| 分析到一半卡住 | 模型被 Ollama 自动卸载 | 已设置 `keep_alive: 300`（5 分钟常驻），模型 14B+ 加上消息多时可能超时 |
| Windows 安装 Ollama 后 GPU 不可用 | NVIDIA 驱动 / CUDA 版本不匹配 | 更新显卡驱动到最新，Ollama 需要 CUDA 12+ 的驱动 |
| 第一次加载模型很慢 | 模型需要从磁盘加载到显存 | 正常现象，后续调用速度快。已设置 keep_alive 减少反复加载 |

### 纯 CPU 运行

没有 GPU 也可以用，但需要耐心：

```bash
# 选一个 7B 以下的模型
ollama pull qwen2.5:3b

# .env 中修改
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT=300
```

> 3B 模型输出质量明显下降，仅适合体验流程，不建议生产使用。

---

## 输入格式

### 微信聊天记录

```json
{
  "session": { "nickname": "群名", "wxid": "...", "messageCount": 31192 },
  "senders": [
    { "senderID": 1, "displayName": "昵称", "avatar": "url", "wxid": "wxid_xxx" }
  ],
  "messages": [
    {
      "localId": 1, "createTime": 1740271101,
      "formattedTime": "2025-02-23 08:38:21",
      "type": "文本消息", "content": "消息内容",
      "senderID": 1, "platformMessageId": "32751..."
    }
  ]
}
```

### QQ 聊天记录（v0.8 新增）

支持 [QQChatExporter V5](https://github.com/shuakami/qq-chat-exporter) 导出的 JSON 格式。私聊和群聊均可导入，自动归一化为微信格式，下游分析管线零改动复用。

- 支持追加导入：已有群可追加新 JSON，按 `platformMessageId` 自动去重
- 支持多群管理

---

## 项目结构

```
chat-miner/
├── main.py                   # FastAPI 入口
├── config.py                 # 配置（读取 .env）
├── requirements.txt
├── stopwords.txt             # 自定义过滤词
├── models/
│   └── database.py           # SQLite CRUD + 表定义
├── services/
│   ├── parser.py             # JSON 解析 + pickle 缓存
│   ├── pipelines.py          # AI 子任务管道 + Prompt 定义
│   ├── analyzer.py           # Ollama API 调用
│   ├── stats_engine.py       # Python 统计（活跃/语言/关系/情绪）
│   ├── stats.py              # 全局统计
│   ├── portrait.py           # 画像生成服务
│   ├── social.py             # AI 关系判断
│   ├── gpu_lock.py           # GPU 分布式锁
│   ├── online_model.py       # DeepSeek API 在线模型 (v0.7)
│   ├── weekly_report.py      # 周报/月报生成引擎 (v0.7)
│   └── task_manager.py       # 异步任务管理 + SSE 进度
├── routers/
│   ├── groups.py             # 群管理 API
│   ├── portrait.py           # 画像 API
│   ├── report.py             # 日报 API + 周报/月报 API
│   ├── stats.py              # 统计 API
│   └── tasks.py              # 任务进度 API
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue       # 仪表盘
│       │   ├── DailyReport.vue     # 日报详情
│       │   ├── WeeklyReport.vue    # 周报详情 (v0.7)
│       │   ├── MonthlyReport.vue   # 月报详情 (v0.7)
│       │   ├── Portraits.vue       # 画像卡片列表 + 关系图
│       │   └── PortraitDetail.vue  # 画像详情
│       └── components/
└── data/                     # 数据目录（不纳入版本控制）
    ├── chat_miner.db
    └── import_*/             # 上传的 JSON + 合并文件
```

---

## 部署

生产环境部署在 WSL Debian，详见 [CLAUDE.md](CLAUDE.md) 部署章节。

```bash
# rsync 增量部署（推荐，秒级完成）
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
| v0.8 | QQ 聊天记录导入（QQChatExporter V5 格式适配）|
| v0.7.3 | 周报/月报页面重设计 + 动态配色 + 异常处理修复 |
| v0.7.2 | 月报 5 新模块 + 词频突变检测 + 匿名化消息直传 DeepSeek |
| v0.7.0 | 周报/月报 + DeepSeek API 深度推理 + 脱敏架构 |
| v0.6.4 | emoji 智能匹配、个人情绪轨迹、性能优化 (O(n²)→O(log n))、pickle 缓存 |
| v0.5.1 | 趣味称号 + 关系解读 |
| v0.5.0 | 深度画像 Pipeline + Python 统计引擎 |
| v0.4.0 | 多任务 Pipeline + SSE 进度推送 |
| v0.1-0.3 | 基础框架 + 日报/画像 + 多群管理 |

详见 [ROADMAP.md](ROADMAP.md)

---

## 技术亮点

- **子任务管道**：复杂 AI 分析拆解为极简子任务，每个只回答一个词或一行，14B 模型也能稳定输出
- **上下文安全**：AI 只看到结构化摘要（≤300 字符），原始聊天内容不出本地
- **GPU 分布式锁**：通过 Dashboard 协调多应用（ComfyUI 等）对 GPU 的使用
- **SSE 实时进度**：分析任务通过 Server-Sent Events 推送进度到前端
- **pickle 缓存**：首次解析 75MB JSON 后缓存为 15MB pickle，重启秒级加载
- **增量去重**：追加导入时按 `platformMessageId` 自动去重

---

## License

MIT
