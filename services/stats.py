"""
统计服务：纯 Python 统计计算（不调用 AI）
消息量、活跃度、时段分布、成员排行等
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from models.database import (
    get_daily_report, get_analyzed_dates, get_members, get_group,
    list_groups,
)

logger = logging.getLogger(__name__)


def compute_global_stats() -> dict:
    """全局统计：跨所有群的汇总"""
    groups = list_groups()
    total_messages = sum(g.get("message_count", 0) for g in groups)
    total_analyzed = sum(g.get("analyzed_days", 0) for g in groups)

    return {
        "total_groups": len(groups),
        "active_groups": sum(1 for g in groups if g.get("status") == "active"),
        "total_messages": total_messages,
        "total_analyzed_days": total_analyzed,
        "groups": groups,
    }


def compute_group_stats(group_id: int) -> dict:
    """某个群的汇总统计"""
    group = get_group(group_id)
    if not group:
        return {}

    members = get_members(group_id)
    analyzed_dates = get_analyzed_dates(group_id)

    # 已分析日期的情绪分布
    mood_counts = defaultdict(int)
    recent_reports = []
    for date in sorted(analyzed_dates, reverse=True):
        report = get_daily_report(group_id, date)
        if report and report.get("report_json"):
            import json
            try:
                rj = json.loads(report["report_json"])
                mood = rj.get("mood", "未知")
                mood_counts[mood] += 1
                recent_reports.append({
                    "date": date,
                    "mood": mood,
                    "mood_emoji": rj.get("mood_emoji", ""),
                    "one_line": rj.get("one_line", ""),
                    "keywords": rj.get("keywords", []),
                    "message_count": report.get("message_count", 0),
                })
            except json.JSONDecodeError:
                pass

    # 成员排行（按消息数）
    member_ranking = [
        {
            "id": m["id"],
            "display_name": m["display_name"],
            "nickname": m["nickname"],
            "remark": m["remark"],
            "avatar": m["avatar"],
            "message_count": m["message_count"],
        }
        for m in sorted(members, key=lambda x: x.get("message_count", 0), reverse=True)
    ]

    # 分析进度
    if group.get("date_range_start") and group.get("date_range_end"):
        try:
            start = datetime.strptime(group["date_range_start"], "%Y-%m-%d")
            end = datetime.strptime(group["date_range_end"], "%Y-%m-%d")
            total_days = (end - start).days + 1
        except (ValueError, TypeError):
            total_days = 0
    else:
        total_days = 0

    return {
        "group": group,
        "members": members,
        "member_count": len(members),
        "member_ranking": member_ranking[:10],
        "analyzed_dates": analyzed_dates,
        "analyzed_count": len(analyzed_dates),
        "total_days_with_data": total_days,
        "progress_pct": round(len(analyzed_dates) / max(total_days, 1) * 100, 1),
        "mood_distribution": dict(mood_counts),
        "recent_reports": recent_reports[:7],
        "top_speaker": member_ranking[0] if member_ranking else None,
    }


def compute_member_stats(group_id: int, member_id: int,
                         sender_messages: list[dict]) -> dict:
    """单个成员的统计"""
    total = len(sender_messages)
    if total == 0:
        return {"total_messages": 0}

    text_msgs = [m for m in sender_messages
                 if m.get("type") in ("文本消息", "引用消息")
                 and (m.get("content") or "").strip()]

    # 活跃时段
    hour_counts = defaultdict(int)
    for m in sender_messages:
        ft = m.get("formattedTime", "")
        if len(ft) >= 13:
            hour = int(ft[11:13])
            hour_counts[hour] += 1

    peak_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # 消息类型偏好
    type_counts = defaultdict(int)
    for m in sender_messages:
        type_counts[m.get("type", "未知")] += 1

    # 平均消息长度
    lengths = [len((m.get("content") or "").strip()) for m in text_msgs]
    avg_len = sum(lengths) / len(lengths) if lengths else 0

    # 活跃日期分布
    date_counts = defaultdict(int)
    for m in sender_messages:
        d = (m.get("formattedTime", "")[:10])
        if d:
            date_counts[d] += 1

    active_dates = len(date_counts)

    return {
        "total_messages": total,
        "text_messages": len(text_msgs),
        "avg_message_length": round(avg_len, 1),
        "peak_hours": [
            {"hour": f"{h:02d}:00", "count": c}
            for h, c in peak_hours
        ],
        "active_dates": active_dates,
        "type_distribution": dict(type_counts),
        "peak_hour_label": _peak_hour_label(peak_hours),
    }


def _peak_hour_label(peak_hours: list) -> str:
    """活跃时段人话标签"""
    if not peak_hours:
        return "暂无数据"
    top_hour = peak_hours[0][0]
    if 6 <= top_hour < 9:
        return "早起鸟儿 🐦"
    elif 9 <= top_hour < 12:
        return "上午干活 💼"
    elif 12 <= top_hour < 14:
        return "午间摸鱼 🍜"
    elif 14 <= top_hour < 18:
        return "下午摸鱼 ☕"
    elif 18 <= top_hour < 22:
        return "晚间活跃 🌆"
    elif 22 <= top_hour < 24 or top_hour < 2:
        return "夜猫子 🦉"
    elif 2 <= top_hour < 6:
        return "通宵战神 🌙"
    return "全天在线 📱"
