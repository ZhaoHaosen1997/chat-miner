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
    mark_date_analyzing, unmark_date_analyzing, is_date_analyzing,
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


async def _run_analyze_and_save(group_id: int, group_name: str, date: str, task, model_id: int = None):
    """后台执行：分析 + 保存

    v0.12.0: 支持 model_id 选择模型（本地或在线均可）。None=使用本地默认模型。
    """
    try:
        await _do_run_analyze_and_save(group_id, group_name, date, task, model_id)
    except Exception as e:
        logger.error(f"日报分析异常 [{group_name} {date}]: {e}", exc_info=True)
        try:
            task.finish(success=False, error={"type": "internal_error", "detail": str(e)})
        except Exception:
            pass  # finish 本身失败则忽略


async def _do_run_analyze_and_save(group_id: int, group_name: str, date: str, task, model_id: int = None):
    """_run_analyze_and_save 的实际实现（由 try/except 包裹调用）"""
    from services.model_config import get_effective_model, _row_to_config
    from models.database import get_model_config

    chat = get_chat_cache(group_id)
    if not chat:
        task.finish(success=False, error={"type": "data_missing", "detail": "群数据未加载"})
        return

    text_msgs = chat.get_text_messages_for_date(date)
    if len(text_msgs) < 5:
        task.finish(success=False, error={"type": "too_few", "detail": f"仅 {len(text_msgs)} 条文本消息"})
        return

    # v0.12.0: 解析模型配置 — 日报允许本地或在线
    if model_id is not None:
        db_config = get_model_config(model_id)
        if not db_config or not db_config.get("is_enabled", 1):
            task.finish(success=False, error={"type": "invalid_model", "detail": f"模型 ID={model_id} 不存在或已禁用"})
            return
        model_config = _row_to_config(db_config)
    else:
        model_config = get_effective_model("local")

    # 根据模型类型决定格式化方式
    model_name = model_config.get("model_name", config.OLLAMA_MODEL)
    chat_text = format_messages_for_prompt(text_msgs, chat.get_sender_name, model=model_name, senders=chat.senders)
    if len(chat_text) > 100000:
        logger.warning(f"{date} 聊天文本过长 {len(chat_text)} 字符")

    # 用 Python 统计精确的小时分布，供活跃时段分析
    day_stats = chat.stats_for_date(date)
    hourly_lines = [f"{h}:00 - {cnt}条" for h, cnt in
                    sorted(day_stats.get("hourly_distribution", {}).items()) if cnt > 0]
    hourly_stats_str = "\n".join(hourly_lines) if hourly_lines else ""

    is_private = len(chat.senders) <= 2
    result = await analyze_daily_chat(
        group_name=group_name,
        date=date,
        chat_text=chat_text,
        msg_count=len(text_msgs),
        model=model_name,
        model_config=model_config,
        task=task,
        hourly_stats=hourly_stats_str,
        is_private=is_private,
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
async def api_analyze_date(group_id: int, date: str, force: bool = False, model_id: int = None):
    """触发分析某天（带回退缓存检查 + 异步执行）

    v0.12.0: 新增 model_id 参数，支持选择模型。None=使用默认本地模型。
    """
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

    # v0.12.5: 提前校验 model_id，避免创建无效任务
    if model_id is not None:
        from models.database import get_model_config
        db_config = get_model_config(model_id)
        if not db_config or not db_config.get("is_enabled", 1):
            raise HTTPException(400, detail=f"模型 ID={model_id} 不存在或已禁用")

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
    asyncio.create_task(_run_analyze_and_save(group_id, group["name"], date, task, model_id=model_id))

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


async def _run_analyze_all(group_id: int, group_name: str, task, model_id: int = None):
    """后台执行：批量分析所有未分析日期（从新到旧）

    v0.12.0: 支持 model_id 选择模型（本地或在线均可）。
    """
    try:
        await _do_run_analyze_all(group_id, group_name, task, model_id)
    except Exception as e:
        logger.error(f"批量分析异常 [{group_name}]: {e}", exc_info=True)
        try:
            task.finish(success=False, error={"type": "internal_error", "detail": str(e)})
        except Exception:
            pass


async def _do_run_analyze_all(group_id: int, group_name: str, task, model_id: int = None):
    """_run_analyze_all 的实际实现（由 try/except 包裹调用）"""
    from services.model_config import get_effective_model, _row_to_config
    from models.database import get_model_config

    chat = get_chat_cache(group_id)
    if not chat:
        task.finish(success=False, error={"type": "data_missing", "detail": "群数据未加载"})
        return

    # v0.12.0: 批量分析统一使用同一个模型
    if model_id is not None:
        db_config = get_model_config(model_id)
        if not db_config or not db_config.get("is_enabled", 1):
            task.finish(success=False, error={"type": "invalid_model", "detail": f"模型 ID={model_id} 不存在或已禁用"})
            return
        model_config = _row_to_config(db_config)
    else:
        model_config = get_effective_model("local")
    model_name = model_config.get("model_name", config.OLLAMA_MODEL)

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

        # v0.13.2: 跳过正在被其他任务分析的日期（防并发重复）
        if is_date_analyzing(group_id, date):
            task.update("inference", f"跳过 {date} (正在被其他任务分析)",
                       progress={"current": i + 1, "total": total})
            continue

        text_msgs = chat.get_text_messages_for_date(date)
        if len(text_msgs) < 5:
            failed += 1
            task.update("inference", f"跳过 {date} (消息过少)",
                       progress={"current": i + 1, "total": total})
            await asyncio.sleep(1)
            continue

        mark_date_analyzing(group_id, date)
        try:
            chat_text = format_messages_for_prompt(text_msgs, chat.get_sender_name, model=model_name, senders=chat.senders)
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
                model=model_name,
                model_config=model_config,
                hourly_stats=hourly_stats_str,
                is_private=len(chat.senders) <= 2,
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
        finally:
            unmark_date_analyzing(group_id, date)

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
async def api_analyze_all(group_id: int, model_id: int = None):
    """一键分析全部未分析日期（从新到旧）

    v0.12.0: 新增 model_id 参数。
    """
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

    asyncio.create_task(_run_analyze_all(group_id, group["name"], task, model_id=model_id))

    return {
        "code": 200,
        "message": f"批量分析任务已创建：{total} 天待分析",
        "data": {"task_id": task.task_id, "total_unanalyzed": total},
    }


@router.get("/trending")
async def api_trending_topics(group_id: int, days: int = 7):
    """群聊热搜榜：聚合最近 N 天日报中的话题和关键词，排行"""
    import json
    from collections import Counter
    from datetime import datetime, timedelta

    reports = get_recent_reports(group_id, limit=days)
    if not reports:
        return {"code": 200, "message": "暂无数据", "data": {"topics": [], "keywords": []}}

    now = datetime.now()
    topic_counter = Counter()
    topic_dates = {}  # topic → 最近出现日期
    kw_counter = Counter()
    kw_dates = {}

    for r in reports:
        try:
            rj = json.loads(r["report_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        date = r["date"]
        # 话题
        for t in rj.get("topic_summary", []):
            t = str(t).strip()
            if t and len(t) >= 2:
                topic_counter[t] += 1
                if t not in topic_dates or date > topic_dates[t]:
                    topic_dates[t] = date
        # 关键词
        for kw in rj.get("keywords", []):
            kw = str(kw).strip()
            if kw and len(kw) >= 2:
                kw_counter[kw] += 1
                if kw not in kw_dates or date > kw_dates[kw]:
                    kw_dates[kw] = date

    # 按热度排序 (频次权重 + 时间衰减)
    def heat_score(item, counter, dates):
        count = counter.get(item, 1)
        last_date = dates.get(item, "")
        # 最近出现的加权
        try:
            dt = datetime.strptime(last_date, "%Y-%m-%d")
            days_ago = max(0, (now - dt).days)
        except Exception:
            days_ago = days
        recency_bonus = max(0, days - days_ago) / days  # 0~1
        return round(count * (1 + recency_bonus), 1)

    # 判断趋势：↑上期也在 ↓新上榜
    def trend_label(item, counter, dates):
        count = counter.get(item, 0)
        last = dates.get(item, "")
        if count >= 3:
            return "hot"  # 连续出现 → 沸
        if count >= 2:
            return "up"   # 多次出现 → ↑
        return "new"      # 首次 → 新

    topics_ranked = []
    for t, c in topic_counter.most_common(15):
        topics_ranked.append({
            "text": t,
            "count": c,
            "heat": heat_score(t, topic_counter, topic_dates),
            "trend": trend_label(t, topic_counter, topic_dates),
        })
    topics_ranked.sort(key=lambda x: x["heat"], reverse=True)

    kws_ranked = []
    for kw, c in kw_counter.most_common(15):
        kws_ranked.append({
            "text": kw,
            "count": c,
            "heat": heat_score(kw, kw_counter, kw_dates),
            "trend": trend_label(kw, kw_counter, kw_dates),
        })
    kws_ranked.sort(key=lambda x: x["heat"], reverse=True)

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "topics": topics_ranked[:10],
            "keywords": kws_ranked[:10],
            "period": f"最近{days}天",
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


# ==================== 周报/月报 API ====================

@router.get("/periods")
async def api_periods(group_id: int, type: str = "weekly"):
    """获取可用的自然周/自然月列表（O(n) 单次遍历，13ms 内完成）"""
    from services.weekly_report import compute_available_periods
    from models.database import list_periodic_reports

    chat = get_chat_cache(group_id)
    all_dates = chat.all_dates() if chat else []
    periods = compute_available_periods(all_dates, type)

    # 合并已生成状态
    existing = list_periodic_reports(group_id, type)
    generated_keys = {e["period_key"] for e in existing}

    result = []
    for p in periods:
        pk = p["period_key"]
        is_generated = pk in generated_keys
        result.append({
            "period_key": pk,
            "date_start": p["date_start"],
            "date_end": p["date_end"],
            "day_count": p["day_count"],
            "status": "generated" if is_generated else p["status"],
        })

    return {"code": 200, "message": "获取成功", "data": result}


@router.get("/weekly/{period_key}")
async def api_get_weekly(group_id: int, period_key: str):
    """获取指定周报"""
    from services.weekly_report import iso_week_dates
    from models.database import get_periodic_report as _get_pr

    report = _get_pr(group_id, "weekly", period_key)
    if not report:
        # 检查该周是否有效
        parts = period_key.split("-W")
        if len(parts) != 2:
            raise HTTPException(400, detail=f"无效的周标识: {period_key}")
        year, week = int(parts[0]), int(parts[1])
        try:
            start, end = iso_week_dates(year, week)
        except Exception:
            raise HTTPException(400, detail=f"无效的周标识: {period_key}")
        raise HTTPException(404, detail=f"周报 {period_key} 尚未生成，请先生成")

    try:
        data = json.loads(report["report_json"])
    except json.JSONDecodeError:
        raise HTTPException(500, detail="报告数据损坏")

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            **data,
            "model_used": report.get("model_used"),
            "created_at": report.get("created_at"),
        },
    }


@router.post("/weekly/generate")
async def api_generate_weekly(group_id: int, period_key: str = "", force: bool = False,
                               model_id: int = None):
    """生成周报（异步任务，默认生成最新可用的自然周）

    Args:
        period_key: 可选，指定要生成的周（如 '2026-W23'），不传则生成最新可用的周
        force: 强制重新生成，跳过缓存
        model_id: v0.12.0 可选，指定使用的模型。None=使用在线默认（无则在本地）。
    """
    from services.weekly_report import compute_available_periods, generate_weekly_report

    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    # 找最新可用的周
    if not period_key:
        all_dates = chat.all_dates()
        periods = compute_available_periods(all_dates, "weekly")
        ready = [p for p in periods if p["status"] == "ready"]
        if not ready:
            return {
                "code": 200,
                "message": "暂无足够数据的自然周（至少需要3天聊天数据）",
                "data": None,
            }
        period_key = ready[-1]["period_key"]  # 最新的

    # 创建异步任务
    task = task_manager.create("generate_weekly", group_id,
                               {"period_key": period_key})
    task.update("pending", f"开始{'重新' if force else ''}生成周报 {period_key}...")

    async def _run():
        try:
            result = await generate_weekly_report(group_id, period_key, task, force=force,
                                                  is_private=len(chat.senders) <= 2,
                                                  model_id=model_id)
            if result["success"]:
                task.update("done", f"周报 {period_key} 生成完成")
                task.finish(success=True)
            else:
                task.finish(success=False,
                            error={"type": "weekly_failed", "detail": result.get("error", "")})
        except Exception as e:
            logger.error(f"周报生成异常: {e}")
            task.finish(success=False, error={"type": "unknown", "detail": str(e)})

    asyncio.create_task(_run())

    return {
        "code": 200,
        "message": f"周报生成任务已创建: {period_key}",
        "data": {"task_id": task.task_id, "period_key": period_key},
    }


@router.get("/monthly/{period_key}")
async def api_get_monthly(group_id: int, period_key: str):
    """获取指定月报"""
    from services.weekly_report import month_dates
    from models.database import get_periodic_report as _get_pr

    report = _get_pr(group_id, "monthly", period_key)
    if not report:
        parts = period_key.split("-")
        if len(parts) != 2:
            raise HTTPException(400, detail=f"无效的月标识: {period_key}")
        year, month = int(parts[0]), int(parts[1])
        try:
            start, end = month_dates(year, month)
        except Exception:
            raise HTTPException(400, detail=f"无效的月标识: {period_key}")
        raise HTTPException(404, detail=f"月报 {period_key} 尚未生成，请先生成")

    try:
        data = json.loads(report["report_json"])
    except json.JSONDecodeError:
        raise HTTPException(500, detail="报告数据损坏")

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            **data,
            "model_used": report.get("model_used"),
            "created_at": report.get("created_at"),
        },
    }


@router.post("/monthly/generate")
async def api_generate_monthly(group_id: int, period_key: str = "", force: bool = False,
                                model_id: int = None):
    """生成月报（异步任务，默认生成最新可用的自然月）

    Args:
        period_key: 可选，指定要生成的月（如 '2026-06'），不传则生成最新可用的月
        force: 强制重新生成，跳过缓存
        model_id: v0.12.0 可选，指定使用的模型。None=使用在线默认（无则在本地）。
    """
    from services.weekly_report import compute_available_periods, generate_monthly_report

    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    if not period_key:
        all_dates = chat.all_dates()
        periods = compute_available_periods(all_dates, "monthly")
        ready = [p for p in periods if p["status"] == "ready"]
        if not ready:
            return {
                "code": 200,
                "message": "暂无足够数据的自然月（至少需要5天聊天数据）",
                "data": None,
            }
        period_key = ready[-1]["period_key"]

    task = task_manager.create("generate_monthly", group_id,
                               {"period_key": period_key})
    task.update("pending", f"开始{'重新' if force else ''}生成月报 {period_key}...")

    async def _run():
        try:
            result = await generate_monthly_report(group_id, period_key, task, force=force,
                                                   is_private=len(chat.senders) <= 2,
                                                   model_id=model_id)
            if result["success"]:
                task.update("done", f"月报 {period_key} 生成完成")
                task.finish(success=True)
            else:
                task.finish(success=False,
                            error={"type": "monthly_failed", "detail": result.get("error", "")})
        except Exception as e:
            logger.error(f"月报生成异常: {e}")
            task.finish(success=False, error={"type": "unknown", "detail": str(e)})

    asyncio.create_task(_run())

    return {
        "code": 200,
        "message": f"月报生成任务已创建: {period_key}",
        "data": {"task_id": task.task_id, "period_key": period_key},
    }


# ==================== 年度报告 v0.11.0 ====================

@router.get("/annual/{year}")
async def api_get_annual(group_id: int, year: int):
    """获取年度报告"""
    from models.database import get_periodic_report
    report = get_periodic_report(group_id, "annual", str(year))
    if not report:
        raise HTTPException(404, detail=f"{year}年度报告尚未生成")
    try:
        report["report_json"] = json.loads(report["report_json"])
    except (json.JSONDecodeError, TypeError):
        pass
    return {"code": 200, "message": "获取成功", "data": report}


@router.post("/annual/generate")
async def api_generate_annual(group_id: int, year: int = 0, force: bool = False,
                               model_id: int = None):
    """生成年度报告（异步任务）

    v0.12.0: 年报仅支持在线模型。若传入 local 模型 ID 返回 400。

    Args:
        year: 年份，0表示生成最新可用年份
        force: 强制重新生成，跳过缓存
        model_id: v0.12.0 可选，仅支持在线模型。None=使用在线默认。
    """
    from services.weekly_report import compute_available_periods
    from services.annual_report import generate_annual_report
    from services.model_config import resolve_model_for_report

    # v0.12.0: 年报强制使用在线模型
    if model_id is not None:
        try:
            model_config = resolve_model_for_report("online", requested_model_id=model_id)
        except ValueError as e:
            raise HTTPException(400, detail=str(e))
    else:
        # 检查在线模型是否可用
        model_config = resolve_model_for_report("online", requested_model_id=None)
        if not model_config.get("api_key"):
            raise HTTPException(400, detail="年报需要在线模型，但当前无可用在线模型。请在设置中配置并启用在线模型。")

    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    if not year:
        all_dates = chat.all_dates()
        periods = compute_available_periods(all_dates, "annual")
        ready = [p for p in periods if p["status"] == "ready"]
        if not ready:
            return {
                "code": 200,
                "message": "暂无足够数据的年份（至少需要30天聊天数据）",
                "data": None,
            }
        year = int(ready[-1]["period_key"])

    # 数据量预检
    all_dates = chat.all_dates()
    year_dates = [d for d in all_dates if d.startswith(str(year))]
    if len(year_dates) < 30:
        return {
            "code": 200,
            "message": f"{year}年数据不足（仅{len(year_dates)}天有消息，需要≥30天）",
            "data": None,
        }

    task = task_manager.create("generate_annual", group_id,
                               {"period_key": str(year)})
    task.update("pending", f"开始{'重新' if force else ''}生成{year}年度报告...")

    async def _run():
        try:
            result = await generate_annual_report(
                group_id, year, chat, task=task, force=force,
                model_config=model_config)
            if result["success"]:
                task.update("done", f"{year}年度报告生成完成")
                task.finish(success=True)
            else:
                task.finish(success=False,
                            error={"type": "annual_failed", "detail": result.get("error", "")})
        except Exception as e:
            logger.error(f"年度报告生成异常: {e}")
            task.finish(success=False, error={"type": "unknown", "detail": str(e)})

    asyncio.create_task(_run())

    return {
        "code": 200,
        "message": f"年度报告生成任务已创建: {year}",
        "data": {"task_id": task.task_id, "period_key": str(year)},
    }


@router.get("/annual-awards/{year}")
async def api_get_annual_awards(group_id: int, year: int):
    """获取某年所有奖项列表"""
    from models.database import get_annual_awards
    awards = get_annual_awards(group_id, year)
    return {"code": 200, "message": "获取成功", "data": awards}


@router.get("/member/{member_id}/awards")
async def api_get_member_awards(group_id: int, member_id: int):
    """获取某成员的历年奖项"""
    from models.database import get_member_awards as db_get_member_awards
    awards = db_get_member_awards(group_id, member_id)
    return {"code": 200, "message": "获取成功", "data": awards}
