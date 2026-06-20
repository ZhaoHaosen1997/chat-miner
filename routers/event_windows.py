"""
事件窗口分析 API v1.18.1
Phase 2: 逐事件组 AI 分析 —— 独立于检测步骤
"""
import json
import logging

from fastapi import APIRouter, HTTPException

from models.database import (
    get_group, get_window, get_windows, update_window_status,
    get_pending_windows_count, insert_events,
)
from routers.groups import get_chat_cache
from services.task_manager import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}/events/windows", tags=["事件窗口分析"])


@router.get("")
async def api_get_windows(group_id: int, status: str = ""):
    """获取事件窗口列表，支持按状态筛选。

    Query params:
        status: pending | analyzing | analyzed | empty (空=全部)
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    windows = get_windows(group_id, status=status)
    # 反序列化 summary_json
    for w in windows:
        try:
            w["summary"] = json.loads(w.get("summary_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            w["summary"] = {}
        # 关联事件信息（已分析窗口）
        if w.get("event_id"):
            from models.database import get_event
            evt = get_event(w["event_id"])
            if evt:
                w["event"] = {
                    "id": evt["id"],
                    "title": evt["title"],
                    "event_type": evt["event_type"],
                }

    return {"code": 200, "message": "ok", "data": windows}


@router.get("/{window_id}")
async def api_get_window(group_id: int, window_id: int):
    """获取单个事件窗口详情，含消息内容（用于 AI 分析前预览）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    window = get_window(window_id)
    if not window or window.get("group_id") != group_id:
        raise HTTPException(404, detail="窗口不存在")

    # 反序列化 summary
    try:
        window["summary"] = json.loads(window.get("summary_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        window["summary"] = {}

    return {"code": 200, "message": "ok", "data": window}


@router.post("/{window_id}/analyze")
async def api_analyze_single_window(group_id: int, window_id: int):
    """分析单个事件窗口：调 AI 判断是否为事件 → 入库 → 更新窗口状态。

    如果窗口已有 event_id（重新分析），先删除旧事件。
    一次只允许一个窗口在分析中。
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    window = get_window(window_id)
    if not window or window.get("group_id") != group_id:
        raise HTTPException(404, detail="窗口不存在")

    if window.get("status") == "analyzing":
        raise HTTPException(409, detail="该事件组正在分析中")

    # 如果已有事件，先删除旧事件
    old_event_id = window.get("event_id")
    if old_event_id:
        from models.database import db
        with db() as conn:
            conn.execute("DELETE FROM events WHERE id=?", (old_event_id,))
        logger.info("重新分析窗口 %d，已删除旧事件 %d", window_id, old_event_id)

    # 标记为 analyzing
    update_window_status(window_id, "analyzing")

    try:
        # 加载窗口消息 — 需要从 chat 缓存中获取
        window_msgs = _load_window_messages(chat, window)
        if not window_msgs:
            update_window_status(window_id, "empty", event_count=0)
            return {
                "code": 200,
                "message": "窗口无有效消息",
                "data": {"window_id": window_id, "status": "empty", "event": None},
            }

        # 构建 Prompt + 调 AI
        event_data = await _analyze_window_with_ai(chat, group_id, window_msgs, window)

        if event_data:
            # v1.18.5: 将 AI 输出中的 [senderID] 还原为昵称
            from services.desensitize import build_stable_id_map, resolve_sender_ids_deep
            _, name_map = build_stable_id_map(chat.senders)
            event_data = resolve_sender_ids_deep(event_data, name_map)

            new_event_id = _save_event_result(event_data, group_id, window_id, window)

            update_window_status(window_id, "analyzed",
                                event_count=1, event_id=new_event_id)
            logger.info("窗口 %d 分析完成: 发现事件 '%s' (id=%s)",
                        window_id, event_data.get("title", ""), new_event_id)

            return {
                "code": 200,
                "message": "分析完成，发现事件",
                "data": {
                    "window_id": window_id,
                    "status": "analyzed",
                    "event_id": new_event_id,
                    "event": {"id": new_event_id, "title": event_data.get("title", "")},
                },
            }
        else:
            update_window_status(window_id, "empty", event_count=0)
            logger.info("窗口 %d 分析完成: 无事件", window_id)

            return {
                "code": 200,
                "message": "分析完成，未发现事件",
                "data": {"window_id": window_id, "status": "empty", "event": None},
            }

    except Exception as e:
        # 恢复到 pending 状态以便重试
        update_window_status(window_id, "pending", event_count=0)
        logger.error("窗口 %d 分析失败: %s", window_id, e, exc_info=True)
        raise HTTPException(500, detail=f"AI 分析失败: {str(e)}")


@router.post("/analyze-all")
async def api_analyze_all_windows(group_id: int):
    """一键分析所有待处理窗口（后台串行队列）。

    复用 task_manager 推送进度，前端可通过 SSE 订阅。
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    pending_count = get_pending_windows_count(group_id)
    if pending_count == 0:
        return {
            "code": 200,
            "message": "没有待分析的窗口",
            "data": {"total": 0, "done": 0},
        }

    if task_manager.has_active("event_window_batch", group_id):
        raise HTTPException(409, detail="该群已有正在执行的批量分析任务")

    task = task_manager.create("event_window_batch", group_id,
                                {"total": pending_count})
    task.update("inference", f"准备分析 {pending_count} 个事件组...")

    async def _batch_run():
        done = 0
        failed = 0
        try:
            # 获取所有 pending 窗口
            all_pending = get_windows(group_id, status="pending")
            task.update("inference", f"开始串行分析 ({done}/{len(all_pending)})...",
                       progress={"current": done, "total": len(all_pending)})

            for w in all_pending:
                if task_manager.is_cancelled(task.task_id):
                    # 清理：将当前正在分析的窗口恢复为 pending
                    for w in all_pending:
                        if get_window(w["id"]).get("status") == "analyzing":
                            update_window_status(w["id"], "pending")
                    task.update("cancelled",
                                f"已取消（完成 {done}/{len(all_pending)}，失败 {failed}）")
                    task.finish(success=False,
                                error={"type": "cancelled", "detail": "用户取消"})
                    return

                wid = w["id"]
                try:
                    # 重新检查状态，防止与单窗口分析并发冲突
                    current = get_window(wid)
                    if current and current.get("status") != "pending":
                        logger.info("批量分析跳过窗口 %d: 状态已变为 %s", wid, current.get("status"))
                        done += 1
                        continue

                    window_msgs = _load_window_messages(chat, w)
                    if not window_msgs:
                        update_window_status(wid, "empty", event_count=0)
                        done += 1
                        task.update("inference",
                                    f"窗口 {wid}: 无消息 ({done}/{len(all_pending)})",
                                    progress={"current": done, "total": len(all_pending)})
                        continue

                    update_window_status(wid, "analyzing")
                    event_data = await _analyze_window_with_ai(chat, group_id,
                                                                window_msgs, w)

                    if event_data:
                        from services.desensitize import build_stable_id_map, resolve_sender_ids_deep
                        _, name_map = build_stable_id_map(chat.senders)
                        event_data = resolve_sender_ids_deep(event_data, name_map)
                        new_event_id = _save_event_result(event_data, group_id, wid, w)
                        update_window_status(wid, "analyzed",
                                            event_count=1, event_id=new_event_id)
                    else:
                        update_window_status(wid, "empty", event_count=0)
                    done += 1

                except Exception as e:
                    logger.error("批量分析窗口 %d 失败: %s", wid, e, exc_info=True)
                    update_window_status(wid, "pending", event_count=0)
                    failed += 1
                    done += 1

                task.update("inference",
                            f"分析中 ({done}/{len(all_pending)})...",
                            progress={"current": done, "total": len(all_pending)})

            task.update("done", f"批量分析完成: {done} 个窗口 (失败 {failed})")
            task.finish(success=True)
            logger.info("批量分析完成 group=%d: %d done, %d failed", group_id, done, failed)

        except Exception as e:
            logger.error("批量分析失败 group=%d: %s", group_id, e, exc_info=True)
            task.finish(success=False,
                        error={"type": "batch_error", "detail": str(e)})

    import asyncio
    asyncio.create_task(_batch_run())

    return {
        "code": 200,
        "message": "批量分析任务已创建",
        "data": {
            "task_id": task.task_id,
            "total": pending_count,
        },
    }


# ── 内部辅助函数 ──────────────────────────────────────────────────


def _save_event_result(event_data: dict, group_id: int,
                       window_id: int, window: dict) -> int | None:
    """字段映射 + 入库：AI返回 → DB列 → insert_events。

    统一单窗口分析和批量分析的持久化逻辑，避免重复。
    Returns: new_event_id or None
    """
    event_data["group_id"] = group_id
    event_data["window_id"] = window_id
    ts_start = event_data.get("time_span_start", "")
    ts_end = event_data.get("time_span_end", "")
    event_data["start_time"] = _resolve_event_time(window, ts_start)
    event_data["end_time"] = _resolve_event_time(window, ts_end, ts_start)
    # v1.18.2: participants 可能是 [{name, role}] 或旧格式 ["name"]
    raw_participants = event_data.get("participants", [])
    if raw_participants and isinstance(raw_participants[0], dict):
        participant_names = [p.get("name", "") for p in raw_participants]
    else:
        participant_names = raw_participants
    event_data["participant_ids"] = json.dumps(
        _resolve_participant_names(group_id, participant_names),
        ensure_ascii=False)
    event_data["key_quotes"] = json.dumps(
        (event_data.get("key_quotes") or [])[:3], ensure_ascii=False)
    event_data.setdefault("message_start_idx", 0)
    event_data.setdefault("message_end_idx", 0)
    event_data.setdefault("message_count", window.get("message_count", 0))
    event_data.setdefault("ai_model_used", "")
    event_data["report_json"] = json.dumps(
        event_data.get("report_json", {}), ensure_ascii=False)
    eids = insert_events([event_data])
    return eids[0] if eids else None


def _load_window_messages(chat, window: dict) -> list[dict]:
    """从 chat 缓存加载窗口时间范围内的消息。"""
    start = window.get("start_time", "")
    end = window.get("end_time", "")
    if not start or not end:
        return []
    msgs = [m for m in chat.messages
            if start <= m.get("formattedTime", "") <= end]
    return msgs


async def _analyze_window_with_ai(chat, group_id: int,
                                   window_msgs: list[dict],
                                   window: dict) -> dict | None:
    """调用 AI 分析单个事件组，返回单个事件 dict 或 None。"""
    from services.event_detector import _build_event_prompt, _call_ai_for_events

    group_name = ""
    try:
        g = get_group(group_id)
        if g:
            group_name = g.get("display_name") or g.get("name", "")
    except Exception:
        pass

    system_prompt, user_prompt = _build_event_prompt(chat, window_msgs, group_name)

    try:
        result = await _call_ai_for_events(system_prompt, user_prompt)
    except Exception as e:
        logger.warning("窗口 AI 调用失败: %s", e, exc_info=True)
        raise

    return result


def _resolve_event_time(window: dict, hh_mm: str, start_hh_mm: str = "") -> str:
    """从 AI 返回的 HH:MM 和窗口日期组装完整时间字符串。

    AI 返回的 time_span 只有 HH:MM 格式。对于 end_time，
    如果 end HH:MM < start HH:MM 说明跨午夜，日期应 +1 天。
    """
    if not hh_mm or len(hh_mm) != 5:
        return hh_mm  # 已经是完整时间或为空

    window_start = window.get("start_time", "")
    if len(window_start) < 10:
        return hh_mm

    date_part = window_start[:10]

    # 跨午夜检测：end_time 的 HH:MM 比 start_time 早
    if start_hh_mm and len(start_hh_mm) == 5 and hh_mm < start_hh_mm:
        try:
            from datetime import datetime, timedelta
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            dt = dt + timedelta(days=1)
            date_part = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return f"{date_part} {hh_mm}:00"


# 参与者名称缓存：避免批量分析时每个窗口重复查询 DB
_participant_cache: dict = {}  # {(group_id,): {name: member_id}}


def _get_participant_map(group_id: int) -> dict:
    """获取群成员名称→ID 映射（带缓存）。"""
    cache_key = group_id
    if cache_key in _participant_cache:
        return _participant_cache[cache_key]
    from models.database import get_members
    name_to_id = {}
    try:
        members = get_members(group_id)
        for m in members:
            mid = m.get("id")
            if mid:
                for field in ("display_name", "nickname", "wxid"):
                    val = m.get(field, "")
                    if val:
                        name_to_id[val] = mid
    except Exception:
        pass
    _participant_cache[cache_key] = name_to_id
    return name_to_id


def _resolve_participant_names(group_id: int, names: list[str]) -> list[int]:
    """将 AI 返回的参与者名称解析为 member_id 列表（使用缓存）。"""
    if not names:
        return []
    name_to_id = _get_participant_map(group_id)
    ids = []
    seen = set()
    for name in names:
        name = name.strip()
        if not name:
            continue
        mid = name_to_id.get(name)
        if mid and mid not in seen:
            ids.append(mid)
            seen.add(mid)
    return ids
