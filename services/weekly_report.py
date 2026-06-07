"""
周报/月报生成服务
- Python 从日报 JSON 中聚合统计
- DeepSeek API 做深度推理和叙事生成
- 降级：DeepSeek 不可用时用本地 Ollama

时间定义：
- 自然周：ISO 8601，周一~周日，标识如 2026-W23
- 自然月：1日~月末，标识如 2026-06
"""
import json
import logging
from datetime import datetime, timedelta
from collections import Counter
from typing import Optional

from config import config
from models.database import (
    get_daily_reports_batch, get_analyzed_dates, save_periodic_report,
    get_periodic_report, list_periodic_reports,
)
from services.online_model import call_deepseek_chat

logger = logging.getLogger(__name__)


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
    analyzed_dates: list[str],
    period_type: str = "weekly",
) -> list[dict]:
    """根据已分析日期，计算所有可用的自然周/自然月

    O(n) 单次遍历：按周期分组计数，不枚举空周期。

    Returns:
        [{period_key, date_start, date_end, day_count, status}, ...]
        status: 'ready' | 'insufficient'
    """
    if not analyzed_dates:
        return []

    min_days = 3 if period_type == "weekly" else 10
    groups = {}  # period_key -> {day_count, date_start, date_end}

    for date_str in analyzed_dates:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        if period_type == "weekly":
            key = get_week_key(d)
            start, end = iso_week_dates(d.year, int(key.split("-W")[1]))
        else:
            key = get_month_key(d)
            start, end = month_dates(d.year, d.month)

        if key not in groups:
            groups[key] = {"day_count": 0, "date_start": start, "date_end": end}
        groups[key]["day_count"] += 1

    # 按 period_key 降序排列（从新到旧）
    result = sorted(
        [
            {
                "period_key": key,
                "date_start": g["date_start"],
                "date_end": g["date_end"],
                "day_count": g["day_count"],
                "status": "ready" if g["day_count"] >= min_days else "insufficient",
            }
            for key, g in groups.items()
        ],
        key=lambda x: x["period_key"],
        reverse=True,
    )
    return result


# ========== Python 聚合统计 ==========

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


# ========== AI 生成（DeepSeek + 降级） ==========

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
  "mood_rollercoaster": "情绪过山车（100-150字），本周的情绪起伏变化",
  "highlight_comments": ["名场面1的10字短评", "名场面2的10字短评", ...],
  "next_week_preview": "下周预告（30-50字），轻松有趣的预测"
}}

注意：highlight_comments 的数量必须和【本周名场面】的数量一致。"""

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
  "atmosphere_diagnosis": "社群氛围诊断（100-150字），本月群氛围特征及对比上月的变化",
  "member_spotlight": "群友聚光灯（100-150字），2-3位本月最值得关注的成员及原因",
  "next_month_preview": "下月展望（40-60字）"
}}"""


def _build_weekly_prompt(aggregated: dict, date_start: str, date_end: str) -> str:
    """构建周报 prompt"""
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
                       model: str = "", json_mode: bool = True) -> dict:
    """调用 DeepSeek 生成，失败时降级到本地 Ollama"""
    # 优先用 DeepSeek
    result = await call_deepseek_chat(
        system_prompt, user_prompt,
        model=model or config.DEEPSEEK_MODEL,
        temperature=0.3,
        json_mode=json_mode,
    )
    if result["success"] and result["data"]:
        return result

    # 降级：本地 Ollama
    logger.warning(f"DeepSeek 不可用，降级到本地模型: {result.get('error')}")
    from services.analyzer import call_ollama_chat
    ollama_result = await call_ollama_chat(system_prompt, user_prompt)
    if ollama_result["success"] and ollama_result["data"]:
        return {
            "success": True,
            "data": ollama_result["data"],
            "model": ollama_result.get("model", config.OLLAMA_MODEL),
            "duration_ms": ollama_result.get("duration_ms", 0),
            "fallback": True,
        }
    return result  # 返回原始错误


def _parse_ai_json(raw_data) -> dict:
    """解析 AI 返回的 JSON（可能是 dict 或 str）"""
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, str):
        # 尝试提取 JSON
        import re
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
    group_id: int, period_key: str, task=None,
) -> dict:
    """生成指定自然周的周报

    Args:
        group_id: 群 ID
        period_key: 周标识，如 '2026-W23'
        task: 可选的 TaskInfo，用于 SSE 进度推送

    Returns:
        {"success": bool, "data": dict, "error": str, "cached": bool}
    """
    # 检查缓存
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

    # 收集该周所有已分析的日期
    analyzed_dates = get_analyzed_dates(group_id)
    week_dates = []
    sd = datetime.strptime(date_start, "%Y-%m-%d")
    ed = datetime.strptime(date_end, "%Y-%m-%d")
    d = sd
    while d <= ed:
        ds = d.strftime("%Y-%m-%d")
        if ds in analyzed_dates:
            week_dates.append(ds)
        d += timedelta(days=1)

    if len(week_dates) < 3:
        return {
            "success": False, "data": None,
            "error": f"该周仅有 {len(week_dates)} 天日报数据（最少需要 3 天）",
        }

    if task:
        task.update("inference", f"聚合 {len(week_dates)} 天日报数据...")

    # Python 聚合
    aggregated = _aggregate_daily_reports(group_id, week_dates)

    if task:
        task.update("inference", f"DeepSeek 生成周报中...")

    # AI 生成
    user_prompt = _build_weekly_prompt(aggregated, date_start, date_end)
    ai_result = await _ai_generate(WEEKLY_SYSTEM_PROMPT, user_prompt, json_mode=True)

    if not ai_result["success"]:
        return {
            "success": False, "data": None,
            "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}",
        }

    # 解析 AI 输出
    ai_data = _parse_ai_json(ai_result["data"])

    # 组装最终报告
    report = {
        "period_key": period_key,
        "date_start": date_start,
        "date_end": date_end,
        "day_count": len(week_dates),
        "total_messages": aggregated["total_messages"],
        "active_members_avg": aggregated["active_members_avg"],
        "overview": ai_data.get("overview", ""),
        "mood_rollercoaster": ai_data.get("mood_rollercoaster", ""),
        "highlight_comments": ai_data.get("highlight_comments", []),
        "next_week_preview": ai_data.get("next_week_preview", ""),
        # 附加 Python 统计数据（前端可按需展示）
        "top_topics": aggregated["top_topics"],
        "top_keywords": aggregated["top_keywords"],
        "mood_timeline": aggregated["mood_timeline"],
        "highlight_quotes": aggregated["highlight_quotes"],
        "hottest_day": aggregated["hottest_day"],
        "coldest_day": aggregated["coldest_day"],
    }

    # 保存到数据库
    model_used = ai_result.get("model", config.DEEPSEEK_MODEL)
    save_periodic_report(
        group_id=group_id, report_type="weekly", period_key=period_key,
        date_start=date_start, date_end=date_end,
        day_count=len(week_dates),
        total_messages=aggregated["total_messages"],
        active_members=aggregated["active_members_avg"],
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
    group_id: int, period_key: str, task=None,
) -> dict:
    """生成指定自然月的月报

    Args:
        group_id: 群 ID
        period_key: 月标识，如 '2026-06'
        task: 可选的 TaskInfo

    Returns:
        {"success": bool, "data": dict, "error": str, "cached": bool}
    """
    # 检查缓存
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

    # 收集该月所有已分析的日期
    analyzed_dates = get_analyzed_dates(group_id)
    month_dates_list = []
    sd = datetime.strptime(date_start, "%Y-%m-%d")
    ed = datetime.strptime(date_end, "%Y-%m-%d")
    d = sd
    while d <= ed:
        ds = d.strftime("%Y-%m-%d")
        if ds in analyzed_dates:
            month_dates_list.append(ds)
        d += timedelta(days=1)

    if len(month_dates_list) < 10:
        return {
            "success": False, "data": None,
            "error": f"该月仅有 {len(month_dates_list)} 天日报数据（最少需要 10 天）",
        }

    if task:
        task.update("inference", f"聚合 {len(month_dates_list)} 天日报数据...")

    # Python 聚合
    aggregated = _aggregate_daily_reports(group_id, month_dates_list)

    # 收集该月内的周报
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
                weekly_parts.append(f"第{wk.split('-W')[1]}周: {wrj.get('overview', '')[:80]}")
            except (json.JSONDecodeError, TypeError):
                pass
    if weekly_parts:
        weekly_context = "【已有周报摘要】\n" + "\n".join(weekly_parts)

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
            pass

    if task:
        task.update("inference", "DeepSeek 生成月报中...")

    # AI 生成（月报用 deepseek-reasoner 获得更深推理）
    user_prompt = _build_monthly_prompt(
        aggregated, date_start, date_end, prev_month_summary, weekly_context
    )
    ai_result = await _ai_generate(
        MONTHLY_SYSTEM_PROMPT, user_prompt,
        model=config.DEEPSEEK_REASONER_MODEL,
        json_mode=True,
    )

    if not ai_result["success"]:
        return {
            "success": False, "data": None,
            "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}",
        }

    ai_data = _parse_ai_json(ai_result["data"])

    # 组装最终报告
    report = {
        "period_key": period_key,
        "date_start": date_start,
        "date_end": date_end,
        "day_count": len(month_dates_list),
        "total_messages": aggregated["total_messages"],
        "active_members_avg": aggregated["active_members_avg"],
        "overview": ai_data.get("overview", ""),
        "atmosphere_diagnosis": ai_data.get("atmosphere_diagnosis", ""),
        "member_spotlight": ai_data.get("member_spotlight", ""),
        "next_month_preview": ai_data.get("next_month_preview", ""),
        "top_topics": aggregated["top_topics"],
        "top_keywords": aggregated["top_keywords"],
        "mood_timeline": aggregated["mood_timeline"],
        "highlight_quotes": aggregated["highlight_quotes"],
        "hottest_day": aggregated["hottest_day"],
        "coldest_day": aggregated["coldest_day"],
    }

    model_used = ai_result.get("model", config.DEEPSEEK_REASONER_MODEL)
    save_periodic_report(
        group_id=group_id, report_type="monthly", period_key=period_key,
        date_start=date_start, date_end=date_end,
        day_count=len(month_dates_list),
        total_messages=aggregated["total_messages"],
        active_members=aggregated["active_members_avg"],
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
