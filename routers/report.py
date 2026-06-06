"""
每日报告 API：触发分析、获取报告、日期列表
"""
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from config import config
from models.database import (
    get_group, get_daily_report, save_daily_report, get_analyzed_dates,
    get_recent_reports, log_analysis,
)
from services.analyzer import analyze_daily_chat
from services.parser import format_messages_for_prompt
from routers.groups import get_chat_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}", tags=["每日报告"])


@router.get("/dates")
async def api_get_dates(group_id: int):
    """获取该群所有有消息的日期"""
    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载，请先导入")

    all_dates = chat.all_dates()
    analyzed = set(get_analyzed_dates(group_id))

    dates_info = []
    for date in all_dates:
        stats = chat.stats_for_date(date)
        dates_info.append({
            "date": date,
            "total_messages": stats["total_messages"],
            "text_messages": stats["text_messages"],
            "active_members": stats["active_members"],
            "analyzed": date in analyzed,
        })

    return {"code": 200, "message": "获取成功", "data": dates_info}


@router.get("/dates/analyzed")
async def api_get_analyzed_dates(group_id: int):
    """获取已分析的日期列表"""
    dates = get_analyzed_dates(group_id)
    return {"code": 200, "message": "获取成功", "data": dates}


@router.post("/analyze/{date}")
async def api_analyze_date(group_id: int, date: str):
    """触发分析某天的群聊"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    # 检查是否已分析
    existing = get_daily_report(group_id, date)
    if existing:
        try:
            report_data = json.loads(existing["report_json"])
            return {
                "code": 200,
                "message": f"{date} 已分析过，返回缓存",
                "data": {
                    "date": date,
                    "report": report_data,
                    "stats": chat.stats_for_date(date),
                    "model_used": existing.get("model_used"),
                    "cached": True,
                },
            }
        except json.JSONDecodeError:
            pass  # 缓存损坏，重新分析

    # 获取该天的文本消息
    text_msgs = chat.get_text_messages_for_date(date)
    if len(text_msgs) < 5:
        return {
            "code": 400,
            "message": f"{date} 文本消息过少（{len(text_msgs)}条），跳过 AI 分析",
            "data": {
                "date": date,
                "stats": chat.stats_for_date(date),
                "skipped": True,
                "reason": "too_few_messages",
            },
        }

    # 格式化聊天记录
    chat_text = format_messages_for_prompt(text_msgs, chat.get_sender_name)
    if len(chat_text) > 100000:
        logger.warning(f"{date} 聊天文本过长 {len(chat_text)} 字符，可能影响分析质量")

    # 调用 AI 分析
    result = await analyze_daily_chat(
        group_name=group["name"],
        date=date,
        chat_text=chat_text,
        msg_count=len(text_msgs),
        model=config.OLLAMA_MODEL,
    )

    if result["success"] and result["data"]:
        # 保存到数据库
        report_json = json.dumps(result["data"], ensure_ascii=False)
        stats = chat.stats_for_date(date)
        save_daily_report(
            group_id=group_id,
            date=date,
            message_count=stats["total_messages"],
            active_members=stats["active_members"],
            report_json=report_json,
            model_used=result["model"],
        )

        # 更新已分析天数
        from models.database import update_group_stats
        analyzed_count = len(get_analyzed_dates(group_id))
        update_group_stats(group_id, analyzed_count)

        # 日志
        log_analysis(group_id, date, "daily_report", "success",
                    model_used=result["model"], duration_ms=result["duration_ms"])

        return {
            "code": 200,
            "message": f"{date} 分析完成",
            "data": {
                "date": date,
                "report": result["data"],
                "stats": stats,
                "model_used": result["model"],
                "cached": False,
                "duration_ms": result["duration_ms"],
            },
        }
    else:
        log_analysis(group_id, date, "daily_report", "failed",
                    error_msg=result.get("error", ""))
        raise HTTPException(
            500,
            detail=f"AI 分析失败: {result.get('error', '未知错误')}",
        )


@router.get("/report/{date}")
async def api_get_report(group_id: int, date: str):
    """获取某天的报告"""
    report = get_daily_report(group_id, date)
    if not report:
        raise HTTPException(404, detail=f"{date} 尚未分析")

    try:
        report_data = json.loads(report["report_json"])
    except json.JSONDecodeError:
        raise HTTPException(500, detail="报告数据损坏")

    chat = get_chat_cache(group_id)
    stats = chat.stats_for_date(date) if chat else {}

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "date": date,
            "report": report_data,
            "stats": stats,
            "model_used": report.get("model_used"),
            "created_at": report.get("created_at"),
        },
    }


@router.get("/reports/recent")
async def api_get_recent_reports(group_id: int, limit: int = 7):
    """获取最近的报告摘要列表"""
    reports = get_recent_reports(group_id, limit)
    result = []
    for r in reports:
        try:
            rj = json.loads(r["report_json"])
            result.append({
                "date": r["date"],
                "mood": rj.get("mood", ""),
                "mood_emoji": rj.get("mood_emoji", ""),
                "one_line": rj.get("one_line", ""),
                "keywords": rj.get("keywords", []),
                "message_count": r["message_count"],
                "active_members": r["active_members"],
            })
        except json.JSONDecodeError:
            result.append({
                "date": r["date"],
                "message_count": r["message_count"],
                "active_members": r["active_members"],
            })

    return {"code": 200, "message": "获取成功", "data": result}
