"""
v1.19.0 共享采样模块 — 所有管线统一采样入口

提供三种采样策略：
- sample_recent: 取最近 N 条（梗百科）
- sample_uniform: 均匀采样，每天固定 N 条（月报/年报）
- sample_full: 取全量，设上限（周报）

双轨制设计：
- 摘要轨道：日报 one_lines / 周报 headlines / 月报 headlines（线索）
- 统计轨道：Python 统计数据（数据）
- 直接采样：原始消息均匀采样（证据）
"""
import json
import logging
from datetime import datetime
from typing import Optional

from services.desensitize import filter_pii
from services.parser import strip_mention_from_content

logger = logging.getLogger(__name__)


# ========== 直接采样函数 ==========

def sample_recent(messages: list[dict], limit: int = 500) -> list[dict]:
    """取最近 N 条有效消息（不去重）

    用于：梗百科

    Args:
        messages: 消息列表（已过滤有效内容）
        limit: 上限数量

    Returns:
        最近的 N 条消息（不去重）
    """
    valid = [m for m in messages if (m.get("content") or "").strip()]
    if len(valid) <= limit:
        return valid
    return valid[-limit:]


def sample_uniform(
    by_date_msgs: dict[str, list[dict]],
    per_day: int = 5,
    total_limit: int = 1500,
    prioritize_longer: bool = False,
) -> list[dict]:
    """均匀采样：每天固定 N 条，总计上限

    用于：月报、年报

    Args:
        by_date_msgs: {date: [messages]}
        per_day: 每天采样数
        total_limit: 总计上限
        prioritize_longer: 是否优先取长消息（年报可选）

    Returns:
        均匀采样的消息列表
    """
    sampled = []
    dates_sorted = sorted(by_date_msgs.keys())

    for date in dates_sorted:
        msgs = by_date_msgs.get(date, [])
        if not msgs:
            continue

        # 可选：按长度排序
        if prioritize_longer:
            msgs = sorted(
                msgs,
                key=lambda m: len((m.get("content") or "").strip()),
                reverse=True
            )

        # 每天取 per_day 条
        day_sample = msgs[:per_day]
        sampled.extend(day_sample)

        # 总上限检查
        if len(sampled) >= total_limit:
            return sampled[:total_limit]

    return sampled


def sample_full(
    by_date_msgs: dict[str, list[dict]],
    total_limit: int = 1000,
) -> list[dict]:
    """取全量消息，设上限

    用于：周报

    Args:
        by_date_msgs: {date: [messages]}
        total_limit: 总计上限

    Returns:
        全量消息（截断至上限）
    """
    sampled = []
    dates_sorted = sorted(by_date_msgs.keys())

    for date in dates_sorted:
        msgs = by_date_msgs.get(date, [])
        sampled.extend(msgs)
        if len(sampled) >= total_limit:
            return sampled[:total_limit]

    return sampled


# ========== 格式化函数 ==========

def format_sampled_messages(
    sampled: list[dict],
    wxid_to_stable: dict[str, int],
    content_limit: int = 120,
    member_names: set[str] = None,
) -> list[dict]:
    """格式化采样消息：PII 过滤 + @mention 剥离 + stable_id + 截断

    Args:
        sampled: 采样后的消息列表
        wxid_to_stable: {wxid: stable_id} 映射
        content_limit: 内容截断长度
        member_names: 群成员名字集合（用于剥离 @mention）

    Returns:
        [{"date", "sender_id", "content", "time"}, ...]
    """
    formatted = []
    for m in sampled:
        content = (m.get("content") or "").strip()
        if not content:
            continue

        # PII 过滤
        content = filter_pii(content)

        # @mention 剥离
        if member_names:
            content = strip_mention_from_content(content, member_names)

        # 截断
        if len(content) > content_limit:
            content = content[:content_limit]

        # stable_id
        wxid = m.get("wxid", "")
        sender_id = str(wxid_to_stable.get(wxid, m.get("senderID", 0)))

        # 时间
        ft = m.get("formattedTime", "")
        date = ft[:10] if len(ft) >= 10 else ""
        time = ft[11:16] if len(ft) >= 16 else ""

        formatted.append({
            "date": date,
            "sender_id": sender_id,
            "content": content,
            "time": time,
        })

    return formatted


def format_sampled_for_prompt(
    sampled: list[dict],
    style: str = "weekly",
) -> str:
    """将采样消息格式化为 Prompt 文本

    Args:
        sampled: 格式化后的消息列表（含 date, sender_id, content, time）
        style: "weekly" | "monthly" | "annual"

    Returns:
        格式化的文本
    """
    if not sampled:
        return "暂无聊天样本"

    # 按日期分组
    by_date = {}
    for m in sampled:
        date = m.get("date", "")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(m)

    lines = []
    dates_sorted = sorted(by_date.keys())

    for date in dates_sorted:
        msgs = by_date[date]
        count = len(msgs)

        if style == "weekly":
            # 周报格式：[2026-06-23 (200条消息)]
            lines.append(f"\n[{date} ({count}条消息)]")
            for m in msgs:
                lines.append(f"[{m['time']}] [{m['sender_id']}]: {m['content']}")

        elif style == "monthly":
            # 月报格式：[2026-06-23 (200条消息)] + 每条带时间
            lines.append(f"\n[{date} ({count}条消息)]")
            for m in msgs[:5]:  # 月报每天最多显示 5 条
                lines.append(f"[{m['time']}] [{m['sender_id']}]: {m['content']}")

        elif style == "annual":
            # 年报格式：[2026-06-23，200条]
            lines.append(f"\n[{date}，{count}条]")
            for m in msgs[:3]:  # 年报每天最多显示 3 条
                lines.append(f"[{m['time']}] [{m['sender_id']}]: {m['content']}")

    return "\n".join(lines)


# ========== 摘要轨道函数 ==========

def get_daily_summary_track(group_id: int, dates: list[str]) -> list[dict]:
    """获取日报摘要轨道（one_lines）

    Args:
        group_id: 群 ID
        dates: 日期列表

    Returns:
        [{date, mood_emoji, one_line, keywords, msg_count}, ...]
    """
    from models.database import get_daily_reports_batch

    if not dates:
        return []

    reports = get_daily_reports_batch(group_id, dates)
    summaries = []

    for r in reports:
        try:
            rj = json.loads(r["report_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        summaries.append({
            "date": r["date"],
            "mood_emoji": rj.get("mood_emoji", "💬"),
            "one_line": rj.get("one_line", ""),
            "keywords": rj.get("keywords", [])[:3],
            "msg_count": r.get("message_count", 0),
        })

    return summaries


def get_weekly_summary_track(group_id: int, dates: list[str]) -> list[dict]:
    """获取周报摘要轨道（headlines）

    Args:
        group_id: 群 ID
        dates: 该周期内的日期列表（用于推算 week_keys）

    Returns:
        [{week, headline}, ...]
    """
    from models.database import get_periodic_report

    if not dates:
        return []

    # 推算 week_keys
    week_keys = set()
    for date in dates:
        d = datetime.strptime(date, "%Y-%m-%d")
        iso = d.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"
        week_keys.add(week_key)

    summaries = []
    for wk in sorted(week_keys):
        wr = get_periodic_report(group_id, "weekly", wk)
        if not wr:
            continue

        try:
            wrj = json.loads(wr["report_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        headline = wrj.get("week_headline", "") or wrj.get("overview", "")
        if headline:
            summaries.append({
                "week": wk,
                "headline": headline[:80],
            })

    return summaries


def get_monthly_summary_track(group_id: int, year: int) -> list[dict]:
    """获取月报摘要轨道（headlines）

    Args:
        group_id: 群 ID
        year: 年份

    Returns:
        [{month, period_key, headline}, ...]
    """
    from models.database import get_periodic_report

    summaries = []
    for month in range(1, 13):
        period_key = f"{year}-{month:02d}"
        mr = get_periodic_report(group_id, "monthly", period_key)
        if not mr:
            continue

        try:
            mrj = json.loads(mr["report_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        headline = mrj.get("overview", "")
        if headline:
            summaries.append({
                "month": month,
                "period_key": period_key,
                "headline": headline[:100],
                "dominant_mood": mrj.get("dominant_mood", ""),
            })

    return summaries


def format_daily_summary_track(summaries: list[dict]) -> str:
    """格式化日报摘要轨道为 Prompt 文本

    Args:
        summaries: [{date, mood_emoji, one_line, keywords}, ...]

    Returns:
        格式化的文本
    """
    if not summaries:
        return "暂无日报摘要"

    lines = []
    for s in summaries:
        emoji = s.get("mood_emoji", "💬")
        one_line = s.get("one_line", "")
        keywords = s.get("keywords", [])
        kw_text = ", ".join(keywords[:3]) if keywords else ""

        if one_line:
            line = f"{s['date']} {emoji} \"{one_line}\""
            if kw_text:
                line += f" (关键词: {kw_text})"
            lines.append(line)

    return "\n".join(lines) if lines else "暂无日报摘要"


def format_weekly_summary_track(summaries: list[dict]) -> str:
    """格式化周报摘要轨道为 Prompt 文本

    Args:
        summaries: [{week, headline}, ...]

    Returns:
        格式化的文本
    """
    if not summaries:
        return "暂无周报摘要"

    lines = []
    for s in summaries:
        week_num = s["week"].split("-W")[1] if "-W" in s["week"] else s["week"]
        headline = s.get("headline", "")
        if headline:
            lines.append(f"第{week_num}周: {headline}")

    return "\n".join(lines) if lines else "暂无周报摘要"


def format_monthly_summary_track(summaries: list[dict]) -> str:
    """格式化月报摘要轨道为 Prompt 文本

    Args:
        summaries: [{month, headline, dominant_mood}, ...]

    Returns:
        格式化的文本
    """
    if not summaries:
        return "暂无月报摘要"

    lines = []
    for s in summaries:
        month = s.get("month", "?")
        headline = s.get("headline", "")
        mood = s.get("dominant_mood", "")
        if headline:
            line = f"### {month}月"
            if mood:
                line += f" [{mood}]"
            lines.append(line)
            lines.append(f"主题：{headline}")

    return "\n\n".join(lines) if lines else "暂无月报摘要"


# ========== 辅助函数 ==========

def get_week_key(date: datetime) -> str:
    """返回日期所属的 ISO 周标识，如 '2026-W23'"""
    iso = date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"