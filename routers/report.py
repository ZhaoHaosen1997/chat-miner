"""
每日报告 API：触发分析、获取报告、日期列表
v0.3.3: 分析改为异步任务 + SSE 进度推送
"""
import json
import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from config import config
from models.database import (
    get_group, get_daily_report, save_daily_report, get_analyzed_dates,
    get_recent_reports, log_analysis, update_group_stats,
)
from services.analyzer import analyze_daily_chat
from services.parser import format_messages_for_prompt
from services.task_manager import task_manager
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


async def _run_analyze_and_save(group_id: int, group_name: str, date: str, task):
    """后台执行：分析 + 保存"""
    chat = get_chat_cache(group_id)
    if not chat:
        task.finish(success=False, error={"type": "data_missing", "detail": "群数据未加载"})
        return

    text_msgs = chat.get_text_messages_for_date(date)
    if len(text_msgs) < 5:
        task.finish(success=False, error={"type": "too_few", "detail": f"仅 {len(text_msgs)} 条文本消息"})
        return

    chat_text = format_messages_for_prompt(text_msgs, chat.get_sender_name)
    if len(chat_text) > 100000:
        logger.warning(f"{date} 聊天文本过长 {len(chat_text)} 字符")

    # 用 Python 统计精确的小时分布，供活跃时段分析
    day_stats = chat.stats_for_date(date)
    hourly_lines = [f"{h}:00 - {cnt}条" for h, cnt in
                    sorted(day_stats.get("hourly_distribution", {}).items()) if cnt > 0]
    hourly_stats_str = "\n".join(hourly_lines) if hourly_lines else ""

    result = await analyze_daily_chat(
        group_name=group_name,
        date=date,
        chat_text=chat_text,
        msg_count=len(text_msgs),
        model=config.OLLAMA_MODEL,
        task=task,
        hourly_stats=hourly_stats_str,
    )

    if result["success"] and result["data"]:
        report_json = json.dumps(result["data"], ensure_ascii=False)
        stats = chat.stats_for_date(date)
        save_daily_report(
            group_id=group_id, date=date,
            message_count=stats["total_messages"],
            active_members=stats["active_members"],
            report_json=report_json,
            model_used=result["model"],
        )
        analyzed_count = len(get_analyzed_dates(group_id))
        update_group_stats(group_id, analyzed_count)
        log_analysis(group_id, date, "daily_report", "success",
                    model_used=result["model"], duration_ms=result["duration_ms"])
    else:
        log_analysis(group_id, date, "daily_report", "failed",
                    error_msg=result.get("error", ""))


@router.delete("/report/{date}")
async def api_delete_report(group_id: int, date: str):
    """删除某天的分析报告"""
    from models.database import get_conn
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM daily_reports WHERE group_id=? AND date=?",
        (group_id, date)
    )
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if deleted:
        # 更新已分析天数
        analyzed_count = len(get_analyzed_dates(group_id))
        update_group_stats(group_id, analyzed_count)
        return {"code": 200, "message": f"已删除 {date} 的分析报告", "data": None}
    raise HTTPException(404, detail=f"{date} 没有分析记录")


@router.post("/analyze/{date}")
async def api_analyze_date(group_id: int, date: str, force: bool = False):
    """触发分析某天（带回退缓存检查 + 异步执行）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    # 检查缓存（force=true 时跳过）
    existing = get_daily_report(group_id, date)
    if existing and not force:
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
            pass

    # 文本消息太少
    text_msgs = chat.get_text_messages_for_date(date)
    if len(text_msgs) < 5:
        # 返回 200，让前端正常处理（不报错），同时记录为跳过
        return {
            "code": 200,
            "message": f"{date} 文本消息过少（{len(text_msgs)}条），已跳过",
            "data": {"date": date, "stats": chat.stats_for_date(date), "skipped": True, "reason": "too_few_messages"},
        }

    # 创建异步任务
    task = task_manager.create("analyze_day", group_id, {"date": date})
    task.update("pending", "任务已创建，等待 GPU...")

    # 后台执行
    asyncio.create_task(_run_analyze_and_save(group_id, group["name"], date, task))

    return {
        "code": 200,
        "message": "任务已创建",
        "data": {"task_id": task.task_id, "status": "pending"},
    }


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


async def _run_analyze_all(group_id: int, group_name: str, task):
    """后台执行：批量分析所有未分析日期（从新到旧）"""
    chat = get_chat_cache(group_id)
    if not chat:
        task.finish(success=False, error={"type": "data_missing", "detail": "群数据未加载"})
        return

    all_dates = chat.all_dates()
    analyzed = set(get_analyzed_dates(group_id))
    unanalyzed = [d for d in all_dates if d not in analyzed]
    # 从新到旧排序
    unanalyzed.sort(reverse=True)

    if not unanalyzed:
        task.update("done", "全部日期已分析", progress={"current": 0, "total": 0})
        task.finish(success=True)
        return

    total = len(unanalyzed)
    failed = 0
    task.update("pending", f"准备分析 {total} 天...", progress={"current": 0, "total": total})

    for i, date in enumerate(unanalyzed):
        if task_manager.is_cancelled(task.task_id):
            task.update("cancelled", f"已取消 (完成 {i}/{total})")
            return

        task.update("inference", f"分析 {date}...", progress={"current": i, "total": total})

        text_msgs = chat.get_text_messages_for_date(date)
        if len(text_msgs) < 5:
            failed += 1
            task.update("inference", f"跳过 {date} (消息过少)",
                       progress={"current": i + 1, "total": total})
            await asyncio.sleep(1)
            continue

        chat_text = format_messages_for_prompt(text_msgs, chat.get_sender_name)
        # 传递 batch task，让 pipeline 的子步骤进度也推送到 SSE
        task.update("inference", f"({i+1}/{total}) 分析 {date}...",
                   progress={"current": i, "total": total})
        day_stats = chat.stats_for_date(date)
        hourly_lines = [f"{h}:00 - {cnt}条" for h, cnt in
                        sorted(day_stats.get("hourly_distribution", {}).items()) if cnt > 0]
        hourly_stats_str = "\n".join(hourly_lines) if hourly_lines else ""
        result = await analyze_daily_chat(
            group_name=group_name, date=date,
            chat_text=chat_text, msg_count=len(text_msgs),
            task=task,
            model=config.OLLAMA_MODEL,
            hourly_stats=hourly_stats_str,
        )

        if result["success"] and result["data"]:
            report_json = json.dumps(result["data"], ensure_ascii=False)
            stats = chat.stats_for_date(date)
            save_daily_report(
                group_id=group_id, date=date,
                message_count=stats["total_messages"],
                active_members=stats["active_members"],
                report_json=report_json, model_used=result["model"],
            )
            log_analysis(group_id, date, "daily_report", "success",
                        model_used=result["model"], duration_ms=result["duration_ms"])
        else:
            failed += 1
            log_analysis(group_id, date, "daily_report", "failed",
                        error_msg=result.get("error", ""))

        # 更新进度
        analyzed_count = len(get_analyzed_dates(group_id))
        update_group_stats(group_id, analyzed_count)
        task.update("inference",
                   f"已完成 {i + 1}/{total} (失败 {failed})",
                   progress={"current": i + 1, "total": total})

        # 天之间短暂冷却
        await asyncio.sleep(3)

    # 完成
    msg = f"全量分析完成：{total - failed}/{total} 成功"
    if failed > 0:
        msg += f"，{failed} 天失败"
    task.update("done", msg, progress={"current": total, "total": total})
    task.finish(success=True)

    # 更新群统计
    final_count = len(get_analyzed_dates(group_id))
    update_group_stats(group_id, final_count)


@router.post("/analyze-all")
async def api_analyze_all(group_id: int):
    """一键分析全部未分析日期（从新到旧）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    # 检查是否有待分析的日期
    analyzed = set(get_analyzed_dates(group_id))
    unanalyzed = [d for d in chat.all_dates() if d not in analyzed]
    if not unanalyzed:
        return {"code": 200, "message": "全部日期已分析", "data": {"total_unanalyzed": 0}}

    total = len(unanalyzed)
    task = task_manager.create("analyze_all", group_id, {"total": total})
    task.update("pending", f"开始批量分析 {total} 天...", progress={"current": 0, "total": total})

    asyncio.create_task(_run_analyze_all(group_id, group["name"], task))

    return {
        "code": 200,
        "message": f"批量分析任务已创建：{total} 天待分析",
        "data": {"task_id": task.task_id, "total_unanalyzed": total},
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
