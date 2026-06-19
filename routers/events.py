"""
事件探测 API 路由 v1.18.0
"""
import json
import logging

from fastapi import APIRouter, HTTPException

from models.database import get_group, get_events, get_event, delete_events_in_range, get_events_by_member
from routers.groups import get_chat_cache
from services.task_manager import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}/events", tags=["事件探测"])


@router.post("/detect")
async def api_detect_events(group_id: int, body: dict):
    """触发事件探测（异步任务）。

    Body: {"date_start": "2025-03-01", "date_end": "2025-06-19"}
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    date_start = (body.get("date_start") or "").strip()
    date_end = (body.get("date_end") or "").strip()

    # 默认时间范围：全量
    if not date_start or not date_end:
        dates = chat.all_dates()
        if dates:
            date_end = dates[0]  # 最新日期（降序）
            date_start = dates[-1]  # 最早日期
        else:
            raise HTTPException(400, detail="群内无聊天数据")

    if task_manager.has_active("event_detection", group_id):
        raise HTTPException(409, detail="该群已有正在执行的事件分析任务")

    task = task_manager.create("event_detection", group_id,
                                {"date_start": date_start, "date_end": date_end})
    task.update("inference", f"Phase 1/2: 正在扫描消息量尖峰...")

    async def _run():
        from services.event_detector import (
            find_candidate_windows, is_window_analyzed,
            analyze_single_window, insert_events_incremental,
        )
        total_events = 0
        try:
            # Phase 1: 找候选窗口
            windows = find_candidate_windows(chat, date_start, date_end)
            if not windows:
                task.update("done", "未发现候选事件窗口")
                task.finish(success=True)
                return

            # 清除旧事件（重新分析时替换而非跳过）
            from models.database import delete_events_in_range
            deleted = delete_events_in_range(group_id, date_start, date_end)
            if deleted:
                logger.info("事件探测: 清除旧事件 %d 条", deleted)

            total = len(windows)
            task.update("inference", f"发现 {total} 个候选窗口，开始逐个分析...")
            logger.info("事件探测: Phase 1 完成，%d 个候选窗口", total)

            # Phase 2: 逐个窗口分析
            for i, window in enumerate(windows):
                # 支持取消
                if task_manager.is_cancelled(task.task_id):
                    task.update("cancelled",
                                f"已取消（完成 {i}/{total}，发现 {total_events} 个事件）")
                    task.finish(success=False,
                                error={"type": "cancelled", "detail": "用户取消"})
                    return

                # 跳过已有事件的窗口
                if is_window_analyzed(group_id, window):
                    task.update("inference",
                                f"窗口 {i+1}/{total}: 跳过（已分析），"
                                f"已发现 {total_events} 个事件")
                    continue

                # 分析单个窗口
                events = await analyze_single_window(chat, group_id, window)
                if events:
                    # AI 返回的 time_span 只有 HH:MM，从窗口消息中匹配日期
                    for e in events:
                        ts = e.get("time_span_start", "")
                        te = e.get("time_span_end", "")
                        date_for_ts = _find_date_for_time(window, ts) if len(ts) == 5 else ""
                        date_for_te = _find_date_for_time(window, te) if len(te) == 5 else ""
                        if date_for_ts:
                            e["time_span_start"] = f"{date_for_ts} {ts}:00"
                        if date_for_te:
                            e["time_span_end"] = f"{date_for_te} {ts if not date_for_te else te}:00"
                        # 计算事件的消息数
                        e["message_count"] = _count_msgs_in_span(
                            window, e.get("time_span_start", ""), e.get("time_span_end", "")
                        )
                    inserted = insert_events_incremental(events, group_id)
                    total_events += inserted

                task.update("inference",
                            f"窗口 {i+1}/{total}: {'发现' if events else '未发现'}事件，"
                            f"已累计 {total_events} 个事件")

            task.update("done", f"事件探测完成: 发现 {total_events} 个事件 ({total} 个窗口)")
            task.finish(success=True)
            logger.info("事件探测完成: %d 个窗口 → %d 个事件", total, total_events)

        except Exception as e:
            logger.error("事件探测失败: %s", e, exc_info=True)
            task.finish(success=False,
                        error={"type": "event_detection_error", "detail": str(e)})

    import asyncio
    asyncio.create_task(_run())

    return {
        "code": 200,
        "message": "任务已创建",
        "data": {"task_id": task.task_id, "status": "pending",
                 "date_start": date_start, "date_end": date_end},
    }


@router.get("")
async def api_get_events(group_id: int, type: str = "",
                         date_from: str = "", date_to: str = "",
                         member_id: int = 0):
    """查询事件列表，支持类型/时间范围/成员筛选。"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    if member_id:
        events = get_events_by_member(group_id, member_id)
        # 后过滤：类型和时间范围
        if type:
            events = [e for e in events if e["event_type"] == type]
        if date_from:
            events = [e for e in events if e["start_time"] >= date_from]
        if date_to:
            events = [e for e in events if e["end_time"] <= date_to + "T23:59:59"]
    else:
        events = get_events(group_id, event_type=type,
                            date_from=date_from, date_to=date_to)

    # JSON 字段反序列化
    for e in events:
        for field in ("participant_ids", "key_quotes"):
            try:
                e[field] = json.loads(e[field])
            except (json.JSONDecodeError, TypeError):
                pass
        # 关联成员展示名称
        e["participant_names"] = _get_member_names(group_id, e.get("participant_ids", []))

    return {
        "code": 200,
        "message": "ok",
        "data": events,
    }


@router.get("/{event_id}")
async def api_get_event_detail(group_id: int, event_id: int):
    """获取单个事件详情 + 关联的原始消息上下文。"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    event = get_event(event_id)
    if not event:
        raise HTTPException(404, detail="事件不存在")

    # JSON 字段反序列化
    for field in ("participant_ids", "key_quotes"):
        try:
            event[field] = json.loads(event[field])
        except (json.JSONDecodeError, TypeError):
            pass
    event["participant_names"] = _get_member_names(group_id,
                                                    event.get("participant_ids", []))

    # 获取关联消息上下文
    chat = get_chat_cache(group_id)
    context_messages = []
    if chat:
        start_time = event.get("start_time", "")
        end_time = event.get("end_time", "")
        for m in chat.messages:
            ft = m.get("formattedTime", "")
            if start_time <= ft <= end_time:
                context_messages.append({
                    "time": ft[11:16] if len(ft) >= 16 else ft,
                    "sender": m.get("senderID", ""),
                    "content": (m.get("content") or "").strip(),
                })

    return {
        "code": 200,
        "message": "ok",
        "data": {**event, "context_messages": context_messages[:500]},  # 最多 500 条
    }


def _count_msgs_in_span(window: list[dict], start_time: str, end_time: str) -> int:
    """统计窗口内落在时间范围内的消息数。"""
    if not start_time or not end_time:
        return len(window)  # fallback
    count = 0
    for m in window:
        ft = m.get("formattedTime", "")
        if start_time <= ft <= end_time:
            count += 1
    return count or len(window)  # fallback if 0


def _find_date_for_time(window: list[dict], hh_mm: str) -> str:
    """从窗口消息中找最匹配给定 HH:MM 的日期。处理跨午夜场景。"""
    best_date = ""
    for m in window:
        ft = m.get("formattedTime", "")
        if len(ft) >= 16:
            msg_time = ft[11:16]  # "HH:MM"
            msg_date = ft[:10]
            if not best_date:
                best_date = msg_date
            if msg_time >= hh_mm:
                return msg_date  # 找到第一个 >= 目标时间的消息日期
    return best_date  # fallback：窗口第一条消息的日期


def _get_member_names(group_id: int, member_ids: list) -> dict:
    """将 member_id 列表转为 {id: name} 映射。"""
    from models.database import get_members
    try:
        members = get_members(group_id)
        name_map = {}
        for m in members:
            mid = m.get("id")
            if mid in member_ids:
                name_map[mid] = m.get("display_name") or m.get("nickname") or str(mid)
        return name_map
    except Exception:
        return {}
