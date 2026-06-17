"""
周报/月报生成服务

v0.7.2 架构升级：
- 新增 _extract_period_raw_data() 直接从原始消息提取 Python 统计 + 匿名化采样
- 绕过本地模型的不可靠归纳，给 DeepSeek 提供确定性数据 + 真实对话风味
- 旧 _aggregate_daily_reports() 保留作为降级路径

时间定义：
- 自然周：ISO 8601，周一~周日，标识如 2026-W23
- 自然月：1日~月末，标识如 2026-06
"""
from models.database import get_default_prompt
import json
import re
import logging
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional

from config import config
from models.database import (
    get_daily_reports_batch, get_analyzed_dates, save_periodic_report,
    get_periodic_report, list_periodic_reports,
)
from services.online_model import call_deepseek_chat
from services.stats_engine import (
    compute_activity_stats, compute_language_stats, compute_social_relations,
    compute_message_style, compute_topic_role, _build_dynamic_stop_words,
    WECHAT_EMOJI_PATTERN, strip_mentions,
)

logger = logging.getLogger(__name__)

# ---- 私聊适配 ----
_PRIVATE_REPLACEMENTS = [
    ("这群人", "两人"),
    ("这个群", "这段聊天"),
    ("群聊", "聊天"),
    ("群友", "对方"),
    ("群格", "聊天模式"),
    ("社群", "聊天"),
    ("群内", "聊天"),
    ("群里的", "聊天中的"),
]


def _adapt_prompt(text: str) -> str:
    """将 prompt 中的群聊话术替换为私聊话术"""
    result = text
    for old, new in _PRIVATE_REPLACEMENTS:
        result = result.replace(old, new)
    return result


# ---- 敏感信息正则（隐私过滤） ----
# 注意：顺序很重要！更具体的模式必须放在前面，避免被宽泛模式误匹配
_PII_PATTERNS = [
    (re.compile(r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]'), '[身份证]'),  # 身份证（必须第一个，避免被手机号误匹配）
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[邮箱]'),  # 邮箱
    (re.compile(r'1[3-9]\d{9}'), '[手机号]'),                    # 手机号（11位，比通用号码更具体）
    (re.compile(r'\d{3,4}-\d{7,8}'), '[电话号码]'),              # 座机号码（带连字符）
]

# ---- 消息趣味性评分维度 ----
_INTERESTING_SIGNALS = [
    (r'\[捂脸\]|\[破防\]|\[裂开\]|\[笑哭\]|\[狗头\]|\[机智\]|\[坏笑\]', 3),   # 高情绪表情
    (r'笑死|哈哈|笑死我了|xswl|233|绷不住|救命|离谱|真香', 3),                # 强情绪词
    (r'\?{2,}|！{2,}|\.{3,}', 2),                                            # 多个标点（情绪激动）
    (r'@\S+|回复|引用', 2),                                                   # 互动标记
    (r'[一-鿿]{15,}', 2),                                                     # 长中文消息
]

# ---- 代号词库（用于生成匿名化别名） ----
_ALIAS_POOL = [
    "技术哥", "潜水员", "段子手", "红包侠", "深夜哲学家", "摸鱼冠军",
    "表情包大户", "吃瓜群众", "卷王", "科普达人", "奶茶品鉴师", "开车司机",
    "话题制造机", "和事佬", "毒舌评论员", "彩虹屁专家", "凡尔赛大师",
    "养生达人", "宠物博主", "追剧狂魔", "外卖品鉴师", "音乐推荐官",
    "职场吐槽王", "社交达人", "冷场王", "气氛组担当", "画饼专家",
    "摆烂王者", "真香选手", "社死担当", "破防boy",
]


# ========== 自然周/月计算 ==========

def iso_week_dates(year: int, week: int) -> tuple[str, str]:
    """返回 ISO 周的第一天（周一）和最后一天（周日）的日期字符串"""
    # ISO week 1 = the week with the first Thursday
    jan4 = datetime(year, 1, 4)
    # Monday of week 1
    first_monday = jan4 - timedelta(days=jan4.weekday())
    monday = first_monday + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_week_key(date: datetime) -> str:
    """返回日期所属的 ISO 周标识，如 '2026-W23'"""
    iso = date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def get_month_key(date: datetime) -> str:
    """返回日期所属的月标识，如 '2026-06'"""
    return date.strftime("%Y-%m")


def month_dates(year: int, month: int) -> tuple[str, str]:
    """返回自然月的第一天和最后一天的日期字符串"""
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    return first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")


def compute_available_periods(
    dates: list[str],
    period_type: str = "weekly",
    chat=None,  # 可选：用于统计文本消息条数
) -> list[dict]:
    """根据有聊天数据的日期，计算所有可用的自然周/自然月

    O(n) 单次遍历：按周期分组计数，不枚举空周期。
    新管道直接从原始消息提取数据，不依赖日报。
    若传入 chat，同时统计文本消息条数，用于判断消息量是否达标。

    Returns:
        [{period_key, date_start, date_end, day_count, msg_count, status}, ...]
        status: 'ready' | 'insufficient'
    """
    if not dates:
        return []

    if period_type == "annual":
        min_days = int(config.ANNUAL_MIN_DAYS)
        min_msgs = int(config.ANNUAL_MIN_MSGS)
    elif period_type == "monthly":
        min_days = int(config.MONTHLY_MIN_DAYS)
        min_msgs = int(config.MONTHLY_MIN_MSGS)
    else:
        min_days = int(config.WEEKLY_MIN_DAYS)
        min_msgs = int(config.WEEKLY_MIN_MSGS)

    groups = {}  # period_key -> {day_count, msg_count, date_start, date_end}

    # 按日期预取消息（一次 chunk_by_date，避免 N 次调用）
    by_date = chat.chunk_by_date() if chat else {}

    for date_str in dates:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        if period_type == "weekly":
            key = get_week_key(d)
            start, end = iso_week_dates(d.year, int(key.split("-W")[1]))
        elif period_type == "annual":
            key = str(d.year)
            start, end = f"{d.year}-01-01", f"{d.year}-12-31"
        else:
            key = get_month_key(d)
            start, end = month_dates(d.year, d.month)

        if key not in groups:
            groups[key] = {"day_count": 0, "msg_count": 0,
                           "date_start": start, "date_end": end}
        groups[key]["day_count"] += 1

        # 统计当天文本消息条数
        if chat and min_msgs > 0 and date_str in by_date:
            groups[key]["msg_count"] += sum(
                1 for m in by_date[date_str]
                if m.get("type") in ("文本消息", "引用消息")
                and (m.get("content") or "").strip()
            )

    # 按 period_key 降序排列（从新到旧）
    result = sorted(
        [
            {
                "period_key": key,
                "date_start": g["date_start"],
                "date_end": g["date_end"],
                "day_count": g["day_count"],
                "msg_count": g["msg_count"],
                "status": "ready" if (g["day_count"] >= min_days and g["msg_count"] >= min_msgs) else "insufficient",
            }
            for key, g in groups.items()
        ],
        key=lambda x: x["period_key"],
        reverse=True,
    )
    return result


# ========== v0.7.2 新数据管道 ==========

def _score_message_interestingness(msg: dict) -> int:
    """对单条消息打分，用于采样时挑选最有料的

    综合维度：情绪强度、互动性、长度、表情丰富度
    """
    content = (msg.get("content") or "").strip()
    if not content:
        return 0
    score = 0
    # 基础分：消息长度
    if len(content) >= 10:
        score += 1
    if len(content) >= 30:
        score += 2
    if len(content) >= 60:
        score += 1  # 太长不一定有趣，加分递减
    # 情绪/趣味信号
    for pattern, points in _INTERESTING_SIGNALS:
        if re.search(pattern, content):
            score += points
            break  # 每个维度只计一次
    # 微信表情数量
    emojis = WECHAT_EMOJI_PATTERN.findall(content)
    if emojis:
        score += min(len(emojis), 5)  # 最多 +5
    return score


def _build_alias_map(member_names: dict[str, str]) -> dict[str, str]:
    """根据成员数据构建 {真名 → 代号} 映射表

    代号从特征数据中推导：观察成员的活跃时段、发言风格等特征来分配
    有意义的代号（如"深夜哲学家"），而不是枯燥的"群友A"。
    无法推导特征时从 _ALIAS_POOL 随机分配。
    """
    import random
    rng = random.Random(42)  # 固定种子保证同一群每次生成一致
    used = set()
    alias_map = {}
    available = list(_ALIAS_POOL)
    rng.shuffle(available)

    for wxid, name in member_names.items():
        if name in used:
            # 同名不同wxid，加后缀
            alias = name
            suffix = 2
            while alias in used:
                alias = f"{name}{suffix}"
                suffix += 1
            alias_map[name] = alias
            used.add(alias)
        elif available:
            alias = available.pop()
            alias_map[name] = alias
            used.add(alias)
        else:
            # 代号池耗尽，回退编号
            alias = f"群友{len(used)+1}"
            alias_map[name] = alias
            used.add(alias)

    return alias_map


def _anonymize_messages(messages: list[dict], alias_map: dict[str, str]) -> list[dict]:
    """匿名化消息：替换真实名称为代号 + 过滤敏感信息

    Args:
        messages: 原始消息列表
        alias_map: {真名: 代号} 映射表

    Returns:
        匿名化后的消息列表（新对象，不修改原始数据）
    """
    # 按名字长度降序排列，避免短名先匹配导致长名失效
    sorted_names = sorted(alias_map.keys(), key=len, reverse=True)

    sanitized = []
    for msg in messages:
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        # 1. 替换真实名字为代号
        for real_name in sorted_names:
            alias = alias_map[real_name]
            content = content.replace(real_name, alias)

        # 2. 敏感信息正则过滤
        for pattern, replacement in _PII_PATTERNS:
            content = pattern.sub(replacement, content)

        sanitized.append({
            **{k: v for k, v in msg.items() if k != "content"},
            "content": content,
        })

    return sanitized


def _extract_period_raw_data(
    chat,  # ParsedChat 对象
    dates: list[str],
    group_id: int,
    samples_per_day: int = 8,
) -> dict:
    """从原始消息中提取周期数据：Python 统计 + 匿名化采样

    v0.7.2 核心函数。完全不依赖本地模型的日报归纳结果。

    Args:
        chat: ParsedChat 实例
        dates: 周期内的日期列表
        group_id: 群 ID
        samples_per_day: 每天采样消息数（默认 8 条）

    Returns:
        {
            "stats": {...},            # Python 统计数据
            "sampled_msgs": [...],     # 匿名化消息样本
            "member_summary": {...},   # 成员级别汇总
            "alias_map": {...},        # {真名: 代号}（仅本地使用）
        }
    """
    # 1. 收集该周期所有消息
    all_msgs = []
    by_date_msgs = {}
    for date in dates:
        day_msgs = chat.chunk_by_date().get(date, [])
        # 只用文本消息（排除系统消息、图片等无语义内容）
        text_msgs = [m for m in day_msgs
                     if m.get("type") in ("文本消息", "引用消息")
                     and (m.get("content") or "").strip()]
        all_msgs.extend(text_msgs)
        by_date_msgs[date] = text_msgs

    if not all_msgs:
        logger.warning(f"周期内无文本消息: dates={dates}")
        return {"stats": {}, "sampled_msgs": [], "member_summary": {}, "alias_map": {}}

    # 2. 预建成员映射
    member_names = {}  # {wxid: name}
    for s in chat.senders:
        wxid = s.get("wxid", "")
        name = s.get("displayName", "") or s.get("nickname", "") or wxid
        if wxid and name:
            member_names[wxid] = name
    member_name_set = set(member_names.values())

    # 3. 构建匿名化映射
    alias_map = _build_alias_map(member_names)

    # 4. Python 统计（每个成员独立计算）
    all_wxids = set(member_names.keys())
    member_stats = {}
    for wxid, name in member_names.items():
        sender_msgs = [m for m in all_msgs if m.get("wxid") == wxid]
        if not sender_msgs:
            continue
        activity = compute_activity_stats(all_msgs, wxid, sender_msgs=sender_msgs)
        language = compute_language_stats(all_msgs, wxid, member_names=member_name_set, sender_msgs=sender_msgs)
        style = compute_message_style(language, activity)
        role = compute_topic_role(all_msgs, wxid, all_wxids)
        member_stats[wxid] = {
            "name": name,
            "alias": alias_map.get(name, name),
            "msg_count": activity.get("total_messages", 0),
            "days_active": activity.get("total_days_active", 0),
            "peak_hour": activity.get("peak_hour", 12),
            "avg_msg_len": language.get("avg_msg_len", 0),
            "top_emojis": [e["emoji"] for e in (language.get("top_emojis") or [])[:3]],
            "style_label": style.get("style_label", ""),
            "emoji_style": style.get("emoji_style_label", ""),
            "role_label": role.get("role_label", ""),
        }

    # 5. 整体统计
    total_msgs = len(all_msgs)
    total_members = len(member_stats)

    # 按发言量排序
    ranked_members = sorted(member_stats.values(),
                           key=lambda x: x["msg_count"], reverse=True)

    # 找出深夜活跃者（peak_hour >= 23 或 <= 5）
    night_owls = [m for m in ranked_members if m["peak_hour"] >= 23 or m["peak_hour"] <= 5]
    # 找出潜水员（发言少但天数多）
    lurkers = [m for m in ranked_members
               if m["days_active"] >= 3 and m["msg_count"] <= m["days_active"] * 3]
    # 表情大户
    emoji_kings = sorted(member_stats.values(),
                        key=lambda x: len(x.get("top_emojis", [])), reverse=True)[:3]

    stats = {
        "total_messages": total_msgs,
        "active_days": len(dates),
        "active_members": total_members,
        "top_speakers": [{"alias": m["alias"], "count": m["msg_count"]}
                        for m in ranked_members[:5]],
        "night_owls": [{"alias": m["alias"], "peak": f"{m['peak_hour']}:00"}
                      for m in night_owls[:3]],
        "lurkers": [{"alias": m["alias"], "days": m["days_active"], "msgs": m["msg_count"]}
                   for m in lurkers[:3]],
        "emoji_kings": [{"alias": m["alias"], "emojis": m["top_emojis"]}
                       for m in emoji_kings],
        "member_details": member_stats,
    }

    # 6. 匿名化采样：每天挑最有料的消息
    # 先对所有消息匿名化
    anonymized_all = _anonymize_messages(all_msgs, alias_map)
    # 重建按天的匿名化消息
    anon_by_date = defaultdict(list)
    for am in anonymized_all:
        ft = am.get("formattedTime", "")
        if len(ft) >= 10:
            anon_by_date[ft[:10]].append(am)

    sampled_msgs = []
    for date in sorted(anon_by_date.keys()):
        day_anon_msgs = anon_by_date[date]
        if not day_anon_msgs:
            continue
        # 打分排序，取 top N
        scored = [(m, _score_message_interestingness(m)) for m in day_anon_msgs]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [m for m, s in scored[:samples_per_day] if s > 0]
        sampled_msgs.append({
            "date": date,
            "count": len(day_anon_msgs),
            "highlights": [{"speaker": alias_map.get(
                member_names.get(m.get("wxid", ""), m.get("wxid", "")),
                m.get("wxid", "")),
                           "content": m.get("content", "")[:120],
                           "time": (m.get("formattedTime") or "")[11:16]}
                          for m in top],
        })

    return {
        "stats": stats,
        "sampled_msgs": sampled_msgs,
        "member_summary": {
            "total": total_members,
            "top5": [m["alias"] for m in ranked_members[:5]],
            "night_owl_count": len(night_owls),
            "night_owl_names": [m["alias"] for m in night_owls[:3]],
        },
        "alias_map": alias_map,
    }


# ========== 旧数据聚合（保留为降级路径） ==========

def _aggregate_daily_reports(group_id: int, dates: list[str]) -> dict:
    """聚合多个日期的日报数据，纯 Python 计算（批量查询，单次 DB 连接）"""
    topic_counter = Counter()
    kw_counter = Counter()
    mood_counter = Counter()
    mood_emoji_days = []  # [(date, mood, mood_emoji)]
    total_msgs = 0
    total_active = 0
    member_msg_map = {}  # display_name -> total messages
    funniest_quotes = []  # 精选搞笑发言
    daily_summaries = []  # 每天的日报摘要行

    # 批量查询（一次连接，避免逐条阻塞事件循环）
    reports = get_daily_reports_batch(group_id, dates)
    for report in reports:
        report_date = report["date"]
        try:
            rj = json.loads(report["report_json"])
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"日报聚合: JSON 损坏，已跳过 date={report_date}")
            continue

        total_msgs += report.get("message_count", 0)
        total_active += report.get("active_members", 0)

        # 话题
        for t in rj.get("topic_summary", []):
            t = str(t).strip()
            if t and len(t) >= 2:
                topic_counter[t] += 1

        # 关键词
        for kw in rj.get("keywords", []):
            kw = str(kw).strip()
            if kw and len(kw) >= 2:
                kw_counter[kw] += 1

        # 情绪
        mood = rj.get("mood", "")
        mood_emoji = rj.get("mood_emoji", "")
        if mood:
            mood_counter[mood] += 1
        mood_emoji_days.append({
            "date": report_date,
            "mood": mood,
            "mood_emoji": mood_emoji or "💬",
        })

        # 每日摘要行
        one_line = rj.get("one_line", "")
        daily_summaries.append({
            "date": report_date,
            "mood_emoji": mood_emoji or "💬",
            "one_line": one_line,
            "keywords": rj.get("keywords", []),
            "msg_count": report.get("message_count", 0),
        })

        # 搞笑发言
        for q in rj.get("funny_quotes", []):
            if isinstance(q, dict) and q.get("quote"):
                funniest_quotes.append({
                    "date": report_date,
                    "speaker": q.get("speaker", ""),
                    "quote": q.get("quote", ""),
                    "comment": q.get("comment", ""),
                })

    # 热度排行
    def topic_heat(item, counter):
        count = counter[item]
        return round(count * 1.0, 1)

    topics_ranked = []
    for t, c in topic_counter.most_common(10):
        topics_ranked.append({"text": t, "count": c, "heat": topic_heat(t, topic_counter)})
    topics_ranked.sort(key=lambda x: x["heat"], reverse=True)

    kws_ranked = []
    for kw, c in kw_counter.most_common(10):
        kws_ranked.append({"text": kw, "count": c, "heat": topic_heat(kw, kw_counter)})
    kws_ranked.sort(key=lambda x: x["heat"], reverse=True)

    # 情绪排行
    mood_ranked = mood_counter.most_common(5)

    # 最热闹/最冷清日
    if daily_summaries:
        hottest = max(daily_summaries, key=lambda d: d["msg_count"])
        coldest = min(daily_summaries, key=lambda d: d["msg_count"])
    else:
        hottest = coldest = None

    # 精选名场面（最多5条）
    best_quotes = sorted(funniest_quotes,
                         key=lambda q: len(q.get("comment", "")) + len(q.get("quote", "")),
                         reverse=True)[:5]

    return {
        "total_messages": total_msgs,
        "active_days": len(dates),
        "active_members_avg": round(total_active / len(dates)) if dates else 0,
        "top_topics": topics_ranked[:5],
        "top_keywords": kws_ranked[:8],
        "mood_ranking": [{"mood": m, "count": c} for m, c in mood_ranked],
        "mood_timeline": mood_emoji_days,
        "hottest_day": hottest,
        "coldest_day": coldest,
        "highlight_quotes": best_quotes,
        "daily_summaries": daily_summaries,
    }


# ========== AI 生成（DeepSeek V4 Flash + 降级） ==========

# -- v0.7.2 新版周报 prompt（基于原始数据+匿名化采样） --
WEEKLY_SYSTEM_PROMPT_V2 = """你是一个脱口秀编剧+人类学家+小说家的混合体。你的读者想通过你看到群聊里他们自己都没发现的趣事。

你的任务不是"写报告"，而是：
1. 像《吐槽大会》编剧一样发现笑点和槽点
2. 像人类学家发现部落仪式一样发现群聊文化
3. 像小说家一样把碎片串成有起承转合的故事

风格要求：
- 犀利、幽默、有洞察，像朋友聊天不是公文写作
- 群友名字已被替换为代号，不要质疑代号的含义
- 可以吐槽但不要人身攻击，保持善意
- 用中文，控制各段落长度"""

WEEKLY_USER_PROMPT_V2 = """来看看这群人这周都干了什么——

【周期】{date_start} 周一 ~ {date_end} 周日，{day_count} 天有聊天

【群聊数据快照】
- 总消息 {total_messages} 条，{active_members} 人参与
- 发言 TOP 5：{top_speakers}
- 深夜活跃分子：{night_owls}
- 潜水观察名单：{lurkers}
- 表情包爱好者：{emoji_kings}

【本周聊天精华】（真实对话片段，名字已用代号替代）
{sampled_chat}

请用 JSON 格式输出以下内容（勿输出其他内容）：
{{
  "week_headline": "群聊头条：用新闻标题风格写1-2句话概括本周最重大的群聊事件。要抓马、有梗。示例：'震惊！技术群连续3天深夜讨论Rust，群主表示我也不懂他们在说什么'",
  "ai_roast": "AI锐评（100-150字）：以犀利毒舌但不冒犯的风格吐槽本周群聊表现。要从具体对话片段中找槽点，不要泛泛而谈。示例：'本周群聊活跃度堪比春运火车站，但有效信息密度约等于一瓶矿泉水……'",
  "weekly_awards": [
    {{
      "award_name": "奖项名（4-6字）",
      "winner": "获奖者代号",
      "reason": "一句话颁奖理由（10-20字）",
      "emoji": "奖项emoji"
    }}
  ],
  "week_narrative": "群聊故事（200-300字）：把本周聊天写成小说的一章。要有起承转合——周一的平静、周三的冲突/高潮、周末的余韵。能看出'剧情线'。",
  "mood_rollercoaster": "情绪过山车（80-120字）：本周情绪起伏的一句话描述，要有画面感",
  "next_week_preview": "下周预告（30-50字）：轻松有趣的预测"
}}

注意：
- weekly_awards 颁发 3-5 个奖项，获奖者用消息中的代号
- week_narrative 要引用具体的聊天片段让故事有说服力
- ai_roast 必须基于给出的聊天片段，不要凭空吐槽"""

# -- 旧版周报 prompt（降级用，基于日报聚合数据） --
WEEKLY_SYSTEM_PROMPT = """你是一个群聊观察员，负责写群聊周报。风格要求：
- 有趣、有洞察，像朋友在跟你聊天
- 不要套话、不要模板化
- 从数据中发现隐藏的 pattern
- 用中文，长度控制在要求范围内"""

WEEKLY_USER_PROMPT = """请根据以下群聊日报摘要，生成本周（{date_start} ~ {date_end}）的周报。

【基本信息】
本周有 {day_count} 天有聊天记录，共 {total_messages} 条消息，日均活跃约 {avg_members} 人。

【每日概要】
{daily_lines}

【热门话题 TOP 5】
{topics_text}

【关键词云】
{keywords_text}

【情绪分布】
{mood_text}

【本周名场面】
{quotes_text}

请用 JSON 格式输出以下内容（勿输出其他内容）：
{{
  "overview": "本周综述（150-200字），一周话题全景和氛围总结",
  "dominant_mood": "本周主导情绪，只输出一个词，从以下选：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕 吃瓜 摸鱼 摆烂 内卷 破防 离谱 上头",
  "mood_rollercoaster": "情绪过山车（100-150字），本周的情绪起伏变化",
  "highlight_comments": ["名场面1的10字短评", "名场面2的10字短评", ...],
  "next_week_preview": "下周预告（30-50字），轻松有趣的预测"
}}

注意：highlight_comments 的数量必须和【本周名场面】的数量一致。dominant_mood 必须严格从选项中选择一个词。"""

MONTHLY_SYSTEM_PROMPT = """你是一个群聊分析师，负责写群聊月报。风格要求：
- 深刻有洞察，但也轻松有趣
- 能发现月度趋势和社群变迁
- 不要套话、不要模板化
- 用中文，长度控制在要求范围内"""

MONTHLY_USER_PROMPT = """请根据以下群聊日报摘要，生成本月（{date_start} ~ {date_end}）的月报。

【基本信息】
本月有 {day_count} 天有聊天记录，共 {total_messages} 条消息，日均活跃约 {avg_members} 人。
{weekly_context}

【每日情绪轨迹】
{mood_lines}

【热门话题 TOP 5】
{topics_text}

【关键词云】
{keywords_text}

【上月对比】
{prev_month_summary}

请用 JSON 格式输出以下内容（勿输出其他内容）：
{{
  "overview": "月度综述（250-300字），本月大事记，话题趋势演变",
  "dominant_mood": "本月主导情绪，只输出一个词，从以下选：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕 吃瓜 摸鱼 摆烂 内卷 破防 离谱 上头",
  "atmosphere_diagnosis": "社群氛围诊断（100-150字），本月群氛围特征及对比上月的变化",
  "member_spotlight": "群友聚光灯（100-150字），2-3位本月最值得关注的成员及原因",
  "next_month_preview": "下月展望（40-60字）"
}}"""

# -- v0.7.2 新版月报 prompt --
MONTHLY_SYSTEM_PROMPT_V2 = """你是一个人类学家+社群分析师+电影预告片编剧的混合体。

你的任务：
1. 像人类学家研究部落一样，给这个群做一个"群格鉴定"
2. 像财经分析师一样，追踪本月话题的涨跌趋势
3. 像考古学家一样，发现新诞生的内部梗
4. 像影评人一样，用电影预告片的语气写下月展望

风格要求：
- 深刻、有趣、有洞察
- 群友名字已被替换为代号，不要质疑代号的含义
- 用中文，控制各段落长度"""

MONTHLY_USER_PROMPT_V2 = """来看看这群人这个月都发生了些什么——

【周期】{date_start} ~ {date_end}，{day_count} 天有聊天，共 {total_messages} 条消息，{active_members} 人参与

【本月群聊数据画像】
- 发言 TOP 5：{top_speakers}
- 深夜活跃分子：{night_owls}
- 潜水观察名单：{lurkers}
- 表情包爱好者：{emoji_kings}

【每周话题快照】（用于分析话题演变）
{weekly_snapshots}

【词频突变检测】（可能是新梗！）
{bursting_words}

【本月聊天精华】（匿名化采样）
{sampled_chat}

【上月对比摘要】
{prev_month_summary}

请用 JSON 格式输出以下内容（勿输出其他内容）：
{{
  "dominant_mood": "本月主导情绪，只输出一个词，从以下选：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕 吃瓜 摸鱼 摆烂 内卷 破防 离谱 上头",
  "group_personality": {{
    "type_label": "群聊人格类型标签（8字内），模仿MBTI风格，如'INTJ-A 技术辩论型'",
    "type_explanation": "类型解读（100-150字），解释为什么是这个类型",
    "core_traits": ["特质1", "特质2", "特质3"]
  }},
  "topic_evolution": "月度话题演变（150-200字）：分析本月话题从月初到月末如何演变，发现话题谱系",
  "meme_archaeology": "梗文化考古（100-150字）：根据词频突变数据，推断本月新诞生的内部梗及其起源",
  "community_health": {{
    "active_score": 3,
    "density_score": 3,
    "harmony_score": 4,
    "nightowl_score": 2,
    "active_comment": "活跃指数评语（15字内）",
    "density_comment": "信息密度评语（15字内）",
    "harmony_comment": "和谐指数评语（15字内）",
    "nightowl_comment": "夜猫子指数评语（15字内）"
  }},
  "next_month_trailer": "下月预告（60-80字）：用电影预告片风格写，要有片名。示例：'即将上映：《六月·deadline的复仇》。主演：全体群友。预告：大量救命、绷不住了、终于上线了即将播出。敬请期待。'",
  "overview": "月度综述（250-300字），本月大事记",
  "atmosphere_diagnosis": "社群氛围诊断（100-150字）",
  "member_spotlight": "群友聚光灯（100-150字），2-3位本月最值得关注的成员"
}}

注意：community_health 四个分数是 1-5 的整数。topic_evolution 要结合每周快照分析变化。meme_archaeology 基于词频突变数据，不要凭空编造。"""


def _build_monthly_prompt_v2(raw_data: dict, date_start: str, date_end: str,
                              prev_month_summary: str, weekly_context: str,
                              bursting_words: str) -> str:
    """构建 v0.7.2 新版月报 prompt"""
    stats = raw_data.get("stats", {})
    sampled = raw_data.get("sampled_msgs", [])

    top_speakers = ", ".join(
        f"{m['alias']}({m['count']}条)" for m in stats.get("top_speakers", [])[:5]
    ) or "暂无数据"
    night_owls = ", ".join(
        f"{m['alias']}({m['peak']})" for m in stats.get("night_owls", [])[:3]
    ) or "暂无"
    lurkers = ", ".join(
        f"{m['alias']}({m['days']}天{m['msgs']}条)" for m in stats.get("lurkers", [])[:3]
    ) or "暂无"
    emoji_kings = ", ".join(
        f"{m['alias']}({' '.join(m['emojis'][:3])})" for m in stats.get("emoji_kings", [])[:3]
    ) or "暂无"

    # 按天聚合聊天精华（月报每天限5条控制上下文）
    chat_parts = []
    for day in sampled:
        highlights = day.get("highlights", [])
        if not highlights:
            continue
        lines = [f"\n[{day['date']} ({day['count']}条消息)]"]
        for h in highlights[:5]:
            lines.append(f"{h.get('speaker','?')} ({h.get('time','')}): {h.get('content','')}")
        chat_parts.append("\n".join(lines))
    sampled_chat = "\n".join(chat_parts) if chat_parts else "暂无聊天样本"

    return MONTHLY_USER_PROMPT_V2.format(
        date_start=date_start,
        date_end=date_end,
        day_count=stats.get("active_days", 0),
        total_messages=stats.get("total_messages", 0),
        active_members=stats.get("active_members", 0),
        top_speakers=top_speakers,
        night_owls=night_owls,
        lurkers=lurkers,
        emoji_kings=emoji_kings,
        weekly_snapshots=weekly_context,
        bursting_words=bursting_words,
        sampled_chat=sampled_chat,
        prev_month_summary=prev_month_summary,
    )


def _build_weekly_prompt_v2(raw_data: dict, date_start: str, date_end: str) -> str:
    """构建 v0.7.2 新版周报 prompt（基于原始数据+匿名化采样）"""
    stats = raw_data.get("stats", {})
    sampled = raw_data.get("sampled_msgs", [])

    # 格式化发言 TOP 5
    top_speakers = ", ".join(
        f"{m['alias']}({m['count']}条)" for m in stats.get("top_speakers", [])[:5]
    ) or "暂无数据"

    # 深夜活跃
    night_owls = ", ".join(
        f"{m['alias']}({m['peak']})" for m in stats.get("night_owls", [])[:3]
    ) or "暂无"

    # 潜水员
    lurkers = ", ".join(
        f"{m['alias']}({m['days']}天{m['msgs']}条)" for m in stats.get("lurkers", [])[:3]
    ) or "暂无"

    # 表情包大户
    emoji_kings = ", ".join(
        f"{m['alias']}({' '.join(m['emojis'][:3])})" for m in stats.get("emoji_kings", [])[:3]
    ) or "暂无"

    # 聊天精华格式化（按天组织）
    chat_parts = []
    for day in sampled:
        highlights = day.get("highlights", [])
        if not highlights:
            continue
        lines = [f"\n[{day['date']} ({day['count']}条消息)]"]
        for h in highlights:
            speaker = h.get("speaker", "?")
            content = h.get("content", "")
            time_str = h.get("time", "")
            lines.append(f"{speaker} ({time_str}): {content}")
        chat_parts.append("\n".join(lines))

    sampled_chat = "\n".join(chat_parts) if chat_parts else "暂无聊天样本"

    return WEEKLY_USER_PROMPT_V2.format(
        date_start=date_start,
        date_end=date_end,
        day_count=stats.get("active_days", 0),
        total_messages=stats.get("total_messages", 0),
        active_members=stats.get("active_members", 0),
        top_speakers=top_speakers,
        night_owls=night_owls,
        lurkers=lurkers,
        emoji_kings=emoji_kings,
        sampled_chat=sampled_chat,
    )


def _build_weekly_prompt(aggregated: dict, date_start: str, date_end: str) -> str:
    """构建周报 prompt（旧版，基于日报聚合数据，降级用）"""
    daily_lines = "\n".join(
        f"{d['date']} {d['mood_emoji']} {d['one_line']} (关键词: {', '.join(d['keywords'][:3])})"
        for d in aggregated["daily_summaries"]
    )
    topics_text = "\n".join(
        f"{i+1}. {t['text']} (热度 {t['heat']})"
        for i, t in enumerate(aggregated["top_topics"])
    ) or "暂无"

    keywords_text = ", ".join(kw["text"] for kw in aggregated["top_keywords"]) or "暂无"

    mood_text = ", ".join(
        f"{m['mood']}×{m['count']}" for m in aggregated["mood_ranking"]
    ) or "暂无"

    quotes_text = "\n".join(
        f"{i+1}. [{q['date']}] {q['speaker']}: 「{q['quote'][:80]}」"
        for i, q in enumerate(aggregated["highlight_quotes"])
    ) or "暂无"

    return WEEKLY_USER_PROMPT.format(
        date_start=date_start,
        date_end=date_end,
        day_count=aggregated["active_days"],
        total_messages=aggregated["total_messages"],
        avg_members=aggregated["active_members_avg"],
        daily_lines=daily_lines,
        topics_text=topics_text,
        keywords_text=keywords_text,
        mood_text=mood_text,
        quotes_text=quotes_text,
    )


def _build_monthly_prompt(aggregated: dict, date_start: str, date_end: str,
                          prev_month_summary: str, weekly_context: str) -> str:
    """构建月报 prompt"""
    mood_lines = " ".join(
        f"{d['date']}{d['mood_emoji']}" for d in aggregated["mood_timeline"]
    )
    topics_text = "\n".join(
        f"{i+1}. {t['text']} (热度 {t['heat']})"
        for i, t in enumerate(aggregated["top_topics"])
    ) or "暂无"
    keywords_text = ", ".join(kw["text"] for kw in aggregated["top_keywords"]) or "暂无"

    return MONTHLY_USER_PROMPT.format(
        date_start=date_start,
        date_end=date_end,
        day_count=aggregated["active_days"],
        total_messages=aggregated["total_messages"],
        avg_members=aggregated["active_members_avg"],
        weekly_context=weekly_context,
        mood_lines=mood_lines,
        topics_text=topics_text,
        keywords_text=keywords_text,
        prev_month_summary=prev_month_summary,
    )


async def _ai_generate(system_prompt: str, user_prompt: str,
                       model: str = "", json_mode: bool = True,
                       temperature: float = 0.8, max_tokens: int = 4096,
                       thinking: bool = False,
                       model_config: dict | None = None,
                       task=None) -> dict:
    """AI 生成入口，支持在线/本地模型 + 降级

    v0.12.0: 优先使用 model_config 选择模型和端点。
    若 model_config 为 None 或 model_config["model_type"]=="online" 且无 api_key，
    则回退到旧版 DeepSeek → Ollama 降级逻辑。

    Args:
        model_config: v0.12.0 模型配置 dict。若为 None 则使用旧版 DeepSeek 逻辑。
    """
    import asyncio as _asyncio
    try:
        return await _asyncio.wait_for(
            _do_ai_generate(system_prompt, user_prompt, model, json_mode,
                          temperature, max_tokens, thinking, model_config,
                          task),
            timeout=300  # v0.13.4: 硬兜底 5 分钟总超时
        )
    except _asyncio.TimeoutError:
        logger.error("_ai_generate 总超时 (300s)")
        return {"success": False, "data": None,
                "error": "AI 生成总超时 (300s)，请尝试使用更小的模型或缩短数据范围",
                "model": model_config.get("model_name", "") if model_config else model,
                "duration_ms": 300000}


async def _do_ai_generate(system_prompt: str, user_prompt: str,
                           model: str, json_mode: bool,
                           temperature: float, max_tokens: int,
                           thinking: bool,
                           model_config: dict | None,
                           task=None) -> dict:
    """_ai_generate 的实际实现（由 asyncio.wait_for 包裹调用）"""
    # v0.12.0: 使用 model_config 路由
    if model_config and model_config.get("model_type") == "online" and model_config.get("api_key"):
        from services.online_model import call_online_chat
        # v1.0.3: 在线模型重试，全部失败后再降级本地
        max_attempts = config.ONLINE_RETRY_COUNT + 1
        last_result = None
        for attempt in range(max_attempts):
            result = await call_online_chat(
                system_prompt, user_prompt,
                model_config=model_config,
                temperature=temperature,
                json_mode=json_mode,
                max_tokens=max_tokens,
                thinking=thinking,
            )
            if result["success"] and result["data"]:
                return result
            last_result = result
            if attempt < max_attempts - 1:
                delay = (attempt + 1) * 2  # 渐进等待：2s, 4s, 6s...
                logger.warning(
                    f"在线模型调用失败 (尝试 {attempt+1}/{max_attempts}): "
                    f"{result.get('error')}，{delay}s 后重试"
                )
                await asyncio.sleep(delay)

        # 全部重试失败 → 降级到本地
        last_error = last_result.get("error", "未知错误") if last_result else "未知错误"
        if not config.LOCAL_LLM_ENABLED:
            logger.warning(f"在线模型 {max_attempts} 次尝试均失败且本地模型已禁用: {last_error}")
            if task:
                task.update("inference", "在线模型失败且本地模型已禁用")
            return {"success": False, "data": None, "error": "在线模型不可用且本地模型已禁用"}
        logger.warning(f"在线模型 {max_attempts} 次尝试均失败，降级到本地: {last_error}")
        from services.model_config import get_effective_model
        try:
            local_cfg = get_effective_model("local")
            if not local_cfg:
                raise ValueError("未找到本地模型配置")
            from services.analyzer import call_ollama_chat
            # v0.13.4: 本地模型上下文有限，截断 prompt 防卡死
            truncated_user = user_prompt
            if len(user_prompt) > 3000:
                truncated_user = user_prompt[:3000] + "\n\n（内容过长已截断，请基于已有数据生成）"
                logger.warning(f"本地模型降级：prompt 从 {len(user_prompt)} 截断至 3000 字符")
            ollama_result = await call_ollama_chat(
                system_prompt, truncated_user,
                model=local_cfg.get("model_name", ""),
                timeout=180,  # 本地模型给 3 分钟
            )
            if ollama_result["success"] and ollama_result["data"]:
                return {
                    "success": True,
                    "data": ollama_result["data"],
                    "model": ollama_result.get("model", config.OLLAMA_MODEL),
                    "duration_ms": ollama_result.get("duration_ms", 0),
                    "fallback": True,
                }
            else:
                logger.warning(f"本地降级也失败: {ollama_result.get('error')}")
                return ollama_result  # 返回本地模型的错误
        except Exception as e:
            logger.warning(f"本地降级异常: {e}")
        return last_result if last_result else {"success": False, "data": None, "error": last_error}

    if model_config and model_config.get("model_type") == "local":
        # 直接使用本地模型
        from services.analyzer import call_ollama_chat
        # v0.13.4: 本地模型上下文有限，截断过长 prompt
        truncated_user = user_prompt
        if len(user_prompt) > 3000:
            truncated_user = user_prompt[:3000] + "\n\n（内容过长已截断，请基于已有数据生成）"
            logger.info(f"本地模型：prompt 从 {len(user_prompt)} 截断至 3000 字符")
        result = await call_ollama_chat(
            system_prompt, truncated_user,
            model=model_config.get("model_name", ""),
            timeout=180,
        )
        if result["success"] and result["data"]:
            return result
        # 本地失败 → 尝试在线降级
        logger.warning(f"本地模型失败，尝试在线降级: {result.get('error')}")
        from services.model_config import get_effective_model
        try:
            online_cfg = get_effective_model("online")
            if online_cfg.get("api_key"):
                from services.online_model import call_online_chat
                online_result = await call_online_chat(
                    system_prompt, user_prompt,
                    model_config=online_cfg,
                    temperature=temperature,
                    json_mode=json_mode,
                    max_tokens=max_tokens,
                    thinking=thinking,
                )
                if online_result["success"] and online_result["data"]:
                    return online_result
        except Exception as e:
            logger.warning("在线模型降级尝试异常: %s", e)
            pass
        return result

    # 旧版降级：DeepSeek → Ollama
    from services.online_model import call_deepseek_chat
    result = await call_deepseek_chat(
        system_prompt, user_prompt,
        model=model or config.DEEPSEEK_MODEL,
        temperature=temperature,
        json_mode=json_mode,
        max_tokens=max_tokens,
        thinking=thinking,
    )
    if result["success"] and result["data"]:
        return result

    # 降级：本地 Ollama
    if not config.LOCAL_LLM_ENABLED:
        logger.warning(f"DeepSeek 不可用且本地模型已禁用: {result.get('error')}")
        return {"success": False, "data": None, "error": "DeepSeek 不可用且本地模型已禁用"}
    logger.warning(f"DeepSeek 不可用，降级到本地模型: {result.get('error')}")
    from services.analyzer import call_ollama_chat
    # v1.0.6: 与新版路径一致的截断和超时保护
    truncated_user = user_prompt
    if len(user_prompt) > 3000:
        truncated_user = user_prompt[:3000] + "\n\n（内容过长已截断，请基于已有数据生成）"
    ollama_result = await call_ollama_chat(system_prompt, truncated_user, timeout=180)
    if ollama_result["success"] and ollama_result["data"]:
        return {
            "success": True,
            "data": ollama_result["data"],
            "model": ollama_result.get("model", config.OLLAMA_MODEL),
            "duration_ms": ollama_result.get("duration_ms", 0),
            "fallback": True,
        }
    return result  # 返回原始错误


def _de_anonymize_ai_output(ai_data: dict, reverse_map: dict[str, str]) -> dict:
    """将 AI 输出中的代号替换回真实名称

    递归处理 dict/list/str，用 reverse_map (代号→真名) 做字符串替换。
    按代号长度降序替换，避免短代号误匹配长代号的部分。
    """
    if not reverse_map:
        return ai_data

    sorted_aliases = sorted(reverse_map.keys(), key=len, reverse=True)

    def _replace(text: str) -> str:
        for alias in sorted_aliases:
            text = text.replace(alias, reverse_map[alias])
        return text

    def _walk(obj):
        if isinstance(obj, str):
            return _replace(obj)
        elif isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_walk(item) for item in obj]
        return obj

    return _walk(ai_data)


def _de_anonymize_stats(stats: dict, reverse_map: dict[str, str]) -> None:
    """原地替换 stats 中带 alias 字段的值为真实名称"""
    if not reverse_map:
        return
    for field in ("top_speakers", "night_owls", "lurkers", "emoji_kings"):
        items = stats.get(field, [])
        for item in items:
            if isinstance(item, dict) and "alias" in item:
                item["alias"] = reverse_map.get(item["alias"], item["alias"])


def _parse_ai_json(raw_data) -> dict:
    """解析 AI 返回的 JSON（可能是 dict 或 str）"""
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, str):
        # 尝试提取 JSON
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError:
            m = re.search(r'\{[\s\S]*\}', raw_data)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
    return {}


# ========== 主入口 ==========

async def generate_weekly_report(
    group_id: int, period_key: str, task=None, force: bool = False,
    is_private: bool = False, model_id: int = None,
) -> dict:
    """生成指定自然周的周报

    is_private: 私聊模式，将 prompt 中的"群聊"替换为"聊天"、"群友"替换为"对方"

    v0.7.2: 优先使用新管道（Python统计+匿名化采样→DeepSeek V4 Flash）
    降级路径：原始消息不足时回退到旧日报聚合模式
    v0.12.0: 新增 model_id 参数，支持模型选择。

    Args:
        group_id: 群 ID
        period_key: 周标识，如 '2026-W23'
        task: 可选的 TaskInfo，用于 SSE 进度推送
        force: 强制重新生成，跳过缓存
        model_id: v0.12.0 可选模型 ID。None=在线默认（无则在本地）。

    Returns:
        {"success": bool, "data": dict, "error": str, "cached": bool}
    """
    from services.model_config import resolve_model_for_report, get_effective_model

    # v0.12.0: 解析模型配置（优先在线，无则本地）
    try:
        model_config = resolve_model_for_report("online", requested_model_id=model_id)
    except ValueError as e:
        logger.warning(f"周报模型解析失败 (model_id={model_id}): {e}，回退到本地默认模型")
        model_config = get_effective_model("local")

    # 检查缓存（force 时跳过）
    if not force:
        existing = get_periodic_report(group_id, "weekly", period_key)
        if existing:
            return {
                "success": True,
                "data": json.loads(existing["report_json"]),
                "error": None,
                "cached": True,
            "model_used": existing.get("model_used"),
            "created_at": existing.get("created_at"),
        }

    # 解析 period_key
    parts = period_key.split("-W")
    if len(parts) != 2:
        return {"success": False, "data": None, "error": f"无效的周标识: {period_key}"}
    year, week = int(parts[0]), int(parts[1])
    date_start, date_end = iso_week_dates(year, week)

    # 收集该周所有日期（包括未分析但有数据的日期）
    from routers.groups import get_chat_cache
    chat = get_chat_cache(group_id)
    all_dates = set(chat.all_dates()) if chat else set()
    analyzed_dates = get_analyzed_dates(group_id)

    week_dates = []
    sd = datetime.strptime(date_start, "%Y-%m-%d")
    ed = datetime.strptime(date_end, "%Y-%m-%d")
    d = sd
    while d <= ed:
        ds = d.strftime("%Y-%m-%d")
        if ds in all_dates:
            week_dates.append(ds)
        d += timedelta(days=1)

    if len(week_dates) < int(config.WEEKLY_MIN_DAYS):
        if task:
            task.finish(success=False, error={"type": "too_few", "detail": f"该周仅有 {len(week_dates)} 天有聊天数据（最少需要 {int(config.WEEKLY_MIN_DAYS)} 天）"})
        return {
            "success": False, "data": None,
            "error": f"该周仅有 {len(week_dates)} 天有聊天数据（最少需要 {int(config.WEEKLY_MIN_DAYS)} 天）",
        }

    if task:
        task.update("inference", f"提取 {len(week_dates)} 天原始数据...")

    # ---- v0.7.2 新管道：Python统计 + 匿名化采样 ----
    use_new_pipeline = False
    raw_data = {}
    total_msgs = 0
    if not chat:
        logger.info(f"周报降级: {period_key} (chat未加载)")
    elif len(chat.messages) == 0:
        logger.info(f"周报降级: {period_key} (chat消息为空)")
    else:
        raw_data = _extract_period_raw_data(chat, week_dates, group_id)
        total_msgs = raw_data.get("stats", {}).get("total_messages", 0)
        if total_msgs >= int(config.WEEKLY_MIN_MSGS):
            use_new_pipeline = True
            logger.info(f"周报使用新管道: {period_key}, {total_msgs}条消息")
        else:
            logger.info(f"周报降级: {period_key} (消息不足: {total_msgs}条<{int(config.WEEKLY_MIN_MSGS)})")

    # v0.13.4: 本地模型上下文有限，降级到旧管道（基于日报聚合，prompt 更短）
    is_local_model = model_config.get("model_type") == "local"
    if is_local_model and use_new_pipeline:
        logger.warning(f"周报检测到本地模型，切换旧管道（prompt 较短）")
        use_new_pipeline = False  # 强制走旧管道

    if use_new_pipeline:
        # 新版 prompt（仅在线模型使用）
        if task:
            task.update("inference", f"📋 {model_config.get('model_name', 'AI')} 生成周报中...")

        user_prompt = _build_weekly_prompt_v2(raw_data, date_start, date_end)
        ai_result = await _ai_generate(
            _adapt_prompt(WEEKLY_SYSTEM_PROMPT_V2) if is_private else WEEKLY_SYSTEM_PROMPT_V2,
            _adapt_prompt(user_prompt) if is_private else user_prompt,
            temperature=config.WEEKLY_TEMPERATURE,
            json_mode=True, max_tokens=config.DEEPSEEK_MAX_TOKENS_WEEKLY,
            model_config=model_config,
        )

        if not ai_result["success"]:
            return {
                "success": False, "data": None,
                "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}",
            }

        ai_data = _parse_ai_json(ai_result["data"])
        stats = raw_data.get("stats", {})

        # 反向映射：将 AI 输出中的代号恢复为真实名称
        alias_map = raw_data.get("alias_map", {})
        if alias_map:
            reverse_map = {v: k for k, v in alias_map.items()}
            ai_data = _de_anonymize_ai_output(ai_data, reverse_map)
            # 同时修复 Python 统计字段中的代号
            _de_anonymize_stats(stats, reverse_map)

        # 组装新版报告
        report = {
            "period_key": period_key,
            "date_start": date_start,
            "date_end": date_end,
            "day_count": len(week_dates),
            "total_messages": stats.get("total_messages", 0),
            "active_members_avg": stats.get("active_members", 0),
            # v0.7.2 新增模块
            "week_headline": ai_data.get("week_headline", ""),
            "dominant_mood": ai_data.get("dominant_mood", ""),
            "ai_roast": ai_data.get("ai_roast", ""),
            "weekly_awards": ai_data.get("weekly_awards", []),
            "week_narrative": ai_data.get("week_narrative", ""),
            # 保留旧字段兼容
            "mood_rollercoaster": ai_data.get("mood_rollercoaster", ""),
            "next_week_preview": ai_data.get("next_week_preview", ""),
            "overview": ai_data.get("week_headline", ""),  # 兼容旧前端
            # Python 统计数据
            "mood_ranking": stats.get("mood_ranking", []),
            "mood_timeline": stats.get("mood_timeline", []),
            "top_topics": stats.get("top_topics", []),
            "top_keywords": stats.get("top_keywords", []),
            "hottest_day": stats.get("hottest_day"),
            "coldest_day": stats.get("coldest_day"),
            "highlight_quotes": stats.get("highlight_quotes", []),
            "top_speakers": stats.get("top_speakers", []),
            "night_owls": stats.get("night_owls", []),
            "lurkers": stats.get("lurkers", []),
            "emoji_kings": stats.get("emoji_kings", []),
            # v0.7.2 版本标记
            "_version": "0.7.2",
        }
    else:
        # ---- 降级：旧日报聚合管道 ----
        if not chat:
            logger.warning(f"周报降级到旧管道: {period_key} (chat未加载)")
        if task:
            task.update("inference", "⚠️ 原始消息数据不足，降级为日报聚合模式...")
        analyzed_week_dates = [d for d in week_dates if d in analyzed_dates]
        if len(analyzed_week_dates) < int(config.WEEKLY_MIN_DAYS):
            if task:
                task.finish(success=False, error={"type": "too_few", "detail": f"该周仅有 {len(analyzed_week_dates)} 天日报数据（最少需要 {int(config.WEEKLY_MIN_DAYS)} 天）"})
            return {
                "success": False, "data": None,
                "error": f"该周仅有 {len(analyzed_week_dates)} 天日报数据（最少需要 {int(config.WEEKLY_MIN_DAYS)} 天）",
            }

        if task:
            task.update("inference", f"聚合 {len(analyzed_week_dates)} 天日报数据（降级）...")

        aggregated = _aggregate_daily_reports(group_id, analyzed_week_dates)

        if task:
            task.update("inference", f"📋 {model_config.get('model_name', 'AI')} 生成周报中...")

        user_prompt = _build_weekly_prompt(aggregated, date_start, date_end)
        ai_result = await _ai_generate(
            _adapt_prompt(WEEKLY_SYSTEM_PROMPT) if is_private else WEEKLY_SYSTEM_PROMPT,
            _adapt_prompt(user_prompt) if is_private else user_prompt,
            json_mode=True, model_config=model_config)

        if not ai_result["success"]:
            return {
                "success": False, "data": None,
                "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}",
            }

        ai_data = _parse_ai_json(ai_result["data"])

        report = {
            "period_key": period_key,
            "date_start": date_start,
            "date_end": date_end,
            "day_count": len(analyzed_week_dates),
            "total_messages": aggregated["total_messages"],
            "active_members_avg": aggregated["active_members_avg"],
            "overview": ai_data.get("overview", ""),
            "dominant_mood": ai_data.get("dominant_mood", ""),
            "mood_rollercoaster": ai_data.get("mood_rollercoaster", ""),
            "highlight_comments": ai_data.get("highlight_comments", []),
            "next_week_preview": ai_data.get("next_week_preview", ""),
            "top_topics": aggregated["top_topics"],
            "top_keywords": aggregated["top_keywords"],
            "mood_timeline": aggregated["mood_timeline"],
            "highlight_quotes": aggregated["highlight_quotes"],
            "hottest_day": aggregated["hottest_day"],
            "coldest_day": aggregated["coldest_day"],
            "_version": "legacy",
        }

    # 保存到数据库
    model_used = ai_result.get("model") or model_config.get("model_name") or config.DEEPSEEK_MODEL
    day_count_val = report.get("day_count", len(week_dates))
    total_msgs_val = report.get("total_messages", 0)
    active_members_val = report.get("active_members_avg", 0)
    save_periodic_report(
        group_id=group_id, report_type="weekly", period_key=period_key,
        date_start=date_start, date_end=date_end,
        day_count=day_count_val,
        total_messages=total_msgs_val,
        active_members=active_members_val,
        report_json=json.dumps(report, ensure_ascii=False),
        model_used=model_used,
    )

    if task:
        task.finish(success=True)

    return {
        "success": True,
        "data": report,
        "error": None,
        "cached": False,
        "model_used": model_used,
    }


async def generate_monthly_report(
    group_id: int, period_key: str, task=None, force: bool = False,
    is_private: bool = False, model_id: int = None,
) -> dict:
    """生成指定自然月的月报

    is_private: 私聊模式，将 prompt 中的"群聊"替换为"聊天"、"群友"替换为"对方"
    v0.12.0: 新增 model_id 参数，支持模型选择。

    Args:
        group_id: 群 ID
        period_key: 月标识，如 '2026-06'
        task: 可选的 TaskInfo
        force: 强制重新生成，跳过缓存
        model_id: v0.12.0 可选模型 ID。None=在线默认（无则在本地）。

    Returns:
        {"success": bool, "data": dict, "error": str, "cached": bool}
    """
    from services.model_config import resolve_model_for_report, get_effective_model

    logger.info(f"月报生成开始: group={group_id} period={period_key} force={force}")

    # v0.12.0: 解析模型配置（优先在线，无则本地）
    try:
        model_config = resolve_model_for_report("online", requested_model_id=model_id)
    except ValueError as e:
        logger.warning(f"月报模型解析失败 (model_id={model_id}): {e}，回退到本地默认模型")
        model_config = get_effective_model("local")
    # 检查缓存（force 时跳过）
    if not force:
        existing = get_periodic_report(group_id, "monthly", period_key)
        if existing:
            return {
                "success": True,
                "data": json.loads(existing["report_json"]),
                "error": None,
            "cached": True,
            "model_used": existing.get("model_used"),
            "created_at": existing.get("created_at"),
        }

    # 解析 period_key
    parts = period_key.split("-")
    if len(parts) != 2:
        return {"success": False, "data": None, "error": f"无效的月标识: {period_key}"}
    year, month = int(parts[0]), int(parts[1])
    date_start, date_end = month_dates(year, month)

    # 收集该月所有日期
    from routers.groups import get_chat_cache
    chat = get_chat_cache(group_id)
    all_dates = set(chat.all_dates()) if chat else set()
    analyzed_dates = get_analyzed_dates(group_id)

    month_dates_list = []
    sd = datetime.strptime(date_start, "%Y-%m-%d")
    ed = datetime.strptime(date_end, "%Y-%m-%d")
    d = sd
    while d <= ed:
        ds = d.strftime("%Y-%m-%d")
        if ds in all_dates:
            month_dates_list.append(ds)
        d += timedelta(days=1)

    if len(month_dates_list) < int(config.MONTHLY_MIN_DAYS):
        logger.warning(f"月报数据不足: group={group_id} period={period_key} 仅有 {len(month_dates_list)} 天")
        if task:
            task.finish(success=False, error={"type": "too_few", "detail": f"该月仅有 {len(month_dates_list)} 天有聊天数据（最少需要 {int(config.MONTHLY_MIN_DAYS)} 天）"})
        return {
            "success": False, "data": None,
            "error": f"该月仅有 {len(month_dates_list)} 天有聊天数据（最少需要 {int(config.MONTHLY_MIN_DAYS)} 天）",
        }

    # 收集该月内的周报摘要
    weekly_context = ""
    week_keys = set()
    for ds in month_dates_list:
        wk = get_week_key(datetime.strptime(ds, "%Y-%m-%d"))
        week_keys.add(wk)
    weekly_parts = []
    for wk in sorted(week_keys):
        wr = get_periodic_report(group_id, "weekly", wk)
        if wr:
            try:
                wrj = json.loads(wr["report_json"])
                overview = wrj.get('week_headline', '') or wrj.get('overview', '')
                weekly_parts.append(f"第{wk.split('-W')[1]}周: {overview[:80]}")
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"月报周上下文: 周报 JSON 损坏 wk={wk}")
    if weekly_parts:
        weekly_context = "\n".join(weekly_parts)

    # 上月对比摘要
    prev_month_summary = "暂无上月数据"
    if month == 1:
        prev_key = f"{year - 1}-12"
    else:
        prev_key = f"{year}-{month - 1:02d}"
    prev_report = get_periodic_report(group_id, "monthly", prev_key)
    if prev_report:
        try:
            prev_json = json.loads(prev_report["report_json"])
            prev_month_summary = (
                f"上月共 {prev_json.get('day_count', '?')} 天有数据，"
                f"{prev_json.get('total_messages', '?')} 条消息。"
                f"综述: {prev_json.get('overview', '')[:150]}"
            )
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"月报上月对比: JSON 损坏 prev_key={prev_key}")

    # ---- v0.7.2 新管道：Python统计 + 匿名化采样 ----
    use_new_pipeline = False
    raw_data = {}
    total_msgs = 0
    bursting_words = "暂无词频突变数据"
    if not chat:
        logger.info(f"月报降级: {period_key} (chat未加载)")
    elif len(chat.messages) == 0:
        logger.info(f"月报降级: {period_key} (chat消息为空)")
    else:
        if task:
            task.update("inference", f"提取 {len(month_dates_list)} 天原始数据...")
        raw_data = _extract_period_raw_data(chat, month_dates_list, group_id, samples_per_day=5)
        total_msgs = raw_data.get("stats", {}).get("total_messages", 0)
        if total_msgs >= int(config.MONTHLY_MIN_MSGS):
            use_new_pipeline = True
            logger.info(f"月报使用新管道: {period_key}, {total_msgs}条消息")
            # 词频突变检测
            try:
                # 获取上月消息
                prev_month_dates = []
                pd_sd = sd - timedelta(days=28)  # 粗略上月
                pd_ed = sd - timedelta(days=1)
                pd = pd_sd
                while pd <= pd_ed:
                    pds = pd.strftime("%Y-%m-%d")
                    if pds in all_dates:
                        prev_month_dates.append(pds)
                    pd += timedelta(days=1)
                prev_msgs = []
                if prev_month_dates and chat:
                    for pds in prev_month_dates:
                        day_msgs = chat.chunk_by_date().get(pds, [])
                        prev_msgs.extend([m for m in day_msgs
                                         if m.get("type") in ("文本消息", "引用消息")
                                         and (m.get("content") or "").strip()])
                if prev_msgs:
                    # 收集本月所有文本消息
                    this_msgs = []
                    for ds in month_dates_list:
                        day_msgs = chat.chunk_by_date().get(ds, [])
                        this_msgs.extend([m for m in day_msgs
                                         if m.get("type") in ("文本消息", "引用消息")
                                         and (m.get("content") or "").strip()])
                    member_name_set = set()
                    for s in chat.senders:
                        name = s.get("displayName", "") or s.get("nickname", "")
                        if name:
                            member_name_set.add(name)
                    from services.stats_engine import detect_bursting_keywords
                    bursting = detect_bursting_keywords(this_msgs, prev_msgs, member_name_set)
                    if bursting:
                        bursting_parts = []
                        for b in bursting[:10]:
                            rate = f"↑{b['growth_rate']}x" if b['growth_rate'] != float('inf') else "🆕全新"
                            bursting_parts.append(
                                f"{b['word']}(本月{b['this_count']}次,上月{b['prev_count']}次,{rate})"
                            )
                        bursting_words = "、".join(bursting_parts)
                        logger.info(f"词频突变检测: {len(bursting)} 个候选词")
            except Exception as e:
                logger.warning(f"词频突变检测失败: {e}")
        else:
            logger.info(f"月报降级: {period_key} (消息不足: {total_msgs}条<{int(config.MONTHLY_MIN_MSGS)})")

    # v0.13.4: 本地模型上下文有限，降级到旧管道
    is_local_model_monthly = model_config.get("model_type") == "local"
    if is_local_model_monthly and use_new_pipeline:
        logger.warning(f"月报检测到本地模型，切换旧管道（prompt 较短）")
        use_new_pipeline = False

    if use_new_pipeline:
        if task:
            task.update("inference", f"📅 {model_config.get('model_name', 'AI')} 生成月报中...")

        user_prompt = _build_monthly_prompt_v2(
            raw_data, date_start, date_end, prev_month_summary, weekly_context, bursting_words
        )
        ai_result = await _ai_generate(
            _adapt_prompt(MONTHLY_SYSTEM_PROMPT_V2) if is_private else MONTHLY_SYSTEM_PROMPT_V2,
            _adapt_prompt(user_prompt) if is_private else user_prompt,
            temperature=config.MONTHLY_TEMPERATURE,
            json_mode=True, max_tokens=config.DEEPSEEK_MAX_TOKENS_MONTHLY,
            thinking=True, model_config=model_config,
        )

        if not ai_result["success"]:
            return {
                "success": False, "data": None,
                "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}",
            }

        ai_data = _parse_ai_json(ai_result["data"])
        stats = raw_data.get("stats", {})

        # 反向映射
        alias_map = raw_data.get("alias_map", {})
        if alias_map:
            reverse_map = {v: k for k, v in alias_map.items()}
            ai_data = _de_anonymize_ai_output(ai_data, reverse_map)
            _de_anonymize_stats(stats, reverse_map)

        # 组装新版报告
        personality = ai_data.get("group_personality", {}) or {}
        health = ai_data.get("community_health", {}) or {}
        report = {
            "period_key": period_key,
            "date_start": date_start,
            "date_end": date_end,
            "day_count": len(month_dates_list),
            "total_messages": stats.get("total_messages", 0),
            "active_members_avg": stats.get("active_members", 0),
            # v0.7.2 新增
            "dominant_mood": ai_data.get("dominant_mood", ""),
            "group_personality": {
                "type_label": personality.get("type_label", ""),
                "type_explanation": personality.get("type_explanation", ""),
                "core_traits": personality.get("core_traits", []),
            },
            "topic_evolution": ai_data.get("topic_evolution", ""),
            "meme_archaeology": ai_data.get("meme_archaeology", ""),
            "community_health": {
                "active_score": health.get("active_score", 3),
                "density_score": health.get("density_score", 3),
                "harmony_score": health.get("harmony_score", 4),
                "nightowl_score": health.get("nightowl_score", 2),
                "active_comment": health.get("active_comment", ""),
                "density_comment": health.get("density_comment", ""),
                "harmony_comment": health.get("harmony_comment", ""),
                "nightowl_comment": health.get("nightowl_comment", ""),
            },
            "next_month_trailer": ai_data.get("next_month_trailer", ""),
            # 保留兼容
            "overview": ai_data.get("overview", ""),
            "atmosphere_diagnosis": ai_data.get("atmosphere_diagnosis", ""),
            "member_spotlight": ai_data.get("member_spotlight", ""),
            "next_month_preview": ai_data.get("next_month_trailer", ""),
            # Python 统计
            "mood_ranking": stats.get("mood_ranking", []),
            "mood_timeline": stats.get("mood_timeline", []),
            "highlight_quotes": stats.get("highlight_quotes", []),
            "top_speakers": stats.get("top_speakers", []),
            "night_owls": stats.get("night_owls", []),
            "lurkers": stats.get("lurkers", []),
            "emoji_kings": stats.get("emoji_kings", []),
            "_version": "0.7.2",
        }
    else:
        # ---- 降级：旧日报聚合管道 ----
        if not chat:
            logger.warning(f"月报降级到旧管道: {period_key} (chat未加载)")
        if task:
            task.update("inference", "⚠️ 原始消息数据不足，降级为日报聚合模式...")
        analyzed_month_dates = [d for d in month_dates_list if d in analyzed_dates]
        if len(analyzed_month_dates) < 10:
            if task:
                task.finish(success=False, error={"type": "too_few", "detail": f"该月仅有 {len(analyzed_month_dates)} 天日报数据（最少需要 10 天）"})
            return {
                "success": False, "data": None,
                "error": f"该月仅有 {len(analyzed_month_dates)} 天日报数据（最少需要 10 天）",
            }

        if task:
            task.update("inference", f"聚合 {len(analyzed_month_dates)} 天日报数据（降级）...")

        aggregated = _aggregate_daily_reports(group_id, analyzed_month_dates)

        if task:
            task.update("inference", f"📅 {model_config.get('model_name', 'AI')} 生成月报中...")

        user_prompt = _build_monthly_prompt(
            aggregated, date_start, date_end, prev_month_summary, weekly_context
        )
        ai_result = await _ai_generate(
            _adapt_prompt(MONTHLY_SYSTEM_PROMPT) if is_private else MONTHLY_SYSTEM_PROMPT,
            _adapt_prompt(user_prompt) if is_private else user_prompt,
            model=config.DEEPSEEK_REASONER_MODEL,
            json_mode=True, model_config=model_config,
        )

        if not ai_result["success"]:
            return {
                "success": False, "data": None,
                "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}",
            }

        ai_data = _parse_ai_json(ai_result["data"])

        report = {
            "period_key": period_key,
            "date_start": date_start,
            "date_end": date_end,
            "day_count": len(analyzed_month_dates),
            "total_messages": aggregated["total_messages"],
            "active_members_avg": aggregated["active_members_avg"],
            "overview": ai_data.get("overview", ""),
            "dominant_mood": ai_data.get("dominant_mood", ""),
            "atmosphere_diagnosis": ai_data.get("atmosphere_diagnosis", ""),
            "member_spotlight": ai_data.get("member_spotlight", ""),
            "next_month_preview": ai_data.get("next_month_preview", ""),
            "top_topics": aggregated["top_topics"],
            "top_keywords": aggregated["top_keywords"],
            "mood_timeline": aggregated["mood_timeline"],
            "highlight_quotes": aggregated["highlight_quotes"],
            "hottest_day": aggregated["hottest_day"],
            "coldest_day": aggregated["coldest_day"],
            "_version": "legacy",
        }

    # ---- 保存 + 返回 ----
    model_used = ai_result.get("model") or model_config.get("model_name") or config.DEEPSEEK_REASONER_MODEL
    save_periodic_report(
        group_id=group_id, report_type="monthly", period_key=period_key,
        date_start=date_start, date_end=date_end,
        day_count=report.get("day_count", len(month_dates_list)),
        total_messages=report.get("total_messages", 0),
        active_members=report.get("active_members_avg", 0),
        report_json=json.dumps(report, ensure_ascii=False),
        model_used=model_used,
    )

    if task:
        task.finish(success=True)

    return {
        "success": True,
        "data": report,
        "error": None,
        "cached": False,
        "model_used": model_used,
    }
