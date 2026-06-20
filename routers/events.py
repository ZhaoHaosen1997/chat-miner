"""
事件探测 API 路由 v1.18.1
Phase 1: Python 检测（尖峰 + 自适应切分）— 纯 Python，不调 AI，不删数据
Phase 2: AI 分析 — 已移至 event_windows.py
"""
import json
import logging

from fastapi import APIRouter, HTTPException

from models.database import (
    get_group, get_events, get_event, get_events_by_member,
    insert_windows, delete_windows_by_group, update_window_status,
)
from routers.groups import get_chat_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}/events", tags=["事件探测"])


@router.post("/detect")
async def api_detect_events(group_id: int, body: dict):
    """Phase 1: Python 事件检测（纯 Python，不调 AI）。

    Body: {"date_start": "2025-03-01", "date_end": "2025-06-19", "force": false}
    force=true 时删除全部窗口后全量重检测（含已分析），默认仅替换待处理窗口。

    Returns: {"windows": [...], "count": N}
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

    # Phase 1: Python 尖峰检测 + 自适应切分 + 摘要提取
    from services.event_detector import find_candidate_windows

    windows = find_candidate_windows(chat, date_start, date_end)
    if not windows:
        return {
            "code": 200,
            "message": "未发现候选事件时段",
            "data": {"windows": [], "count": 0},
        }

    # force=true → 全量重检测（含已分析窗口）；默认增量（仅替换 pending/empty）
    force = body.get("force", False)
    delete_windows_by_group(group_id, only_pending=not force)

    # 持久化窗口
    window_records = []
    for w in windows:
        window_records.append({
            "start_time": w["start_time"],
            "end_time": w["end_time"],
            "message_count": w["message_count"],
            "summary_json": json.dumps(w.get("summary", {}), ensure_ascii=False),
        })

    ids = insert_windows(window_records, group_id)

    # 构建响应 — 含 window id 和 summary
    result_windows = []
    for i, w in enumerate(windows):
        result_windows.append({
            "id": ids[i],
            "start_time": w["start_time"],
            "end_time": w["end_time"],
            "message_count": w["message_count"],
            "status": "pending",
            "summary": w.get("summary", {}),
        })

    logger.info("事件检测完成: group=%d, %d 个事件组", group_id, len(ids))

    return {
        "code": 200,
        "message": f"检测完成，发现 {len(ids)} 个候选事件组",
        "data": {
            "windows": result_windows,
            "count": len(ids),
        },
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


@router.post("/{event_id}/reanalyze")
async def api_reanalyze_event(group_id: int, event_id: int):
    """重新分析指定事件 — 兼容无 window_id 的旧事件。

    流程：
    1. 查找事件 → 获取时间范围和消息索引
    2. 若事件有 window_id → 直接走窗口分析
    3. 若无 window_id → 根据事件数据创建临时窗口，关联旧 event_id
    4. 删除旧事件 → 调 AI → 写入新事件
    """
    from models.database import db, get_window
    from routers.event_windows import (
        _load_window_messages, _analyze_window_with_ai, _save_event_result,
    )

    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    old_event = get_event(event_id)
    if not old_event or old_event.get("group_id") != group_id:
        raise HTTPException(404, detail="事件不存在")

    # 阶段1：确定或创建窗口
    window_id = old_event.get("window_id")
    window = None

    if window_id:
        # 有 window_id，直接用
        window = get_window(window_id)
        if not window:
            raise HTTPException(404, detail=f"事件关联的窗口 {window_id} 不存在")

    if not window:
        # 无窗口：根据事件时间范围创建临时窗口
        start_time = old_event.get("start_time", "")
        end_time = old_event.get("end_time", "")
        msg_count = old_event.get("message_count", 0)

        # 加载该时间范围的消息（复用 _load_window_messages 用临时 dict）
        all_msgs = _load_window_messages(chat, {"start_time": start_time, "end_time": end_time})
        actual_count = max(msg_count, len(all_msgs))

        # 创建窗口并关联旧事件
        new_windows = insert_windows([{
            "start_time": start_time,
            "end_time": end_time,
            "message_count": actual_count,
            "summary_json": json.dumps({
                "preview": [{"senderID": m.get("senderID", ""), "content": (m.get("content") or "")[:80]}
                           for m in all_msgs[:5]]
            }, ensure_ascii=False),
        }], group_id)
        window_id = new_windows[0]
        window = get_window(window_id)
        # 关联旧事件以便后续删除
        with db() as conn:
            conn.execute(
                "UPDATE event_windows SET event_id=? WHERE id=?",
                (event_id, window_id),
            )
        logger.info("为旧事件 %d 创建临时窗口 %d (start=%s, msgs=%d)",
                    event_id, window_id, start_time[:16], actual_count)

    # 阶段2：删除旧事件
    with db() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    logger.info("重新分析事件 %d，已删除旧事件（窗口=%d）", event_id, window_id)

    # 阶段3：锁定窗口为 analyzing
    if window.get("status") == "analyzing":
        raise HTTPException(409, detail="该事件组正在分析中")
    update_window_status(window_id, "analyzing")

    # 阶段4：加载消息 + AI 分析
    try:
        window_msgs = _load_window_messages(chat, window)
        if not window_msgs:
            update_window_status(window_id, "empty", event_count=0)
            return {
                "code": 200,
                "message": "窗口无有效消息",
                "data": {"window_id": window_id, "status": "empty", "event": None},
            }

        event_data = await _analyze_window_with_ai(chat, group_id, window_msgs, window)

        if event_data:
            new_event_id = _save_event_result(event_data, group_id, window_id, window)
            update_window_status(window_id, "analyzed",
                                event_count=1, event_id=new_event_id)
            logger.info("事件 %d 重新分析完成: '%s' → 新事件 id=%s",
                        event_id, event_data.get("title", ""), new_event_id)
            return {
                "code": 200,
                "message": "重新分析完成，发现事件",
                "data": {
                    "window_id": window_id,
                    "status": "analyzed",
                    "event_id": new_event_id,
                    "event": {"id": new_event_id, "title": event_data.get("title", "")},
                },
            }
        else:
            update_window_status(window_id, "empty", event_count=0)
            logger.info("事件 %d 重新分析完成: 无事件", event_id)
            return {
                "code": 200,
                "message": "重新分析完成，未发现事件",
                "data": {"window_id": window_id, "status": "empty", "event": None},
            }

    except Exception as e:
        update_window_status(window_id, "pending", event_count=0)
        logger.error("事件 %d 重新分析失败: %s", event_id, e, exc_info=True)
        raise HTTPException(500, detail=f"AI 分析失败: {str(e)}")
