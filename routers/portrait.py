"""
群友画像 API：获取、刷新画像
v0.3.3: 刷新改为异步任务 + SSE 进度推送
"""
import json
import asyncio
import logging

from fastapi import APIRouter, HTTPException
from config import config
from models.database import (
    get_group, get_portraits, get_portrait, log_analysis,
    get_member_by_sender_id, get_member,
)
from services.portrait import generate_single_portrait, refresh_portraits
from services.task_manager import task_manager
from routers.groups import get_chat_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}", tags=["群友画像"])


@router.get("/portraits")
async def api_get_portraits(group_id: int):
    """获取群所有成员的画像"""
    from models.database import get_portraits as db_get_portraits
    portraits = db_get_portraits(group_id)

    result = []
    for p in portraits:
        try:
            pj = json.loads(p["portrait_json"])
        except (json.JSONDecodeError, TypeError):
            pj = {}

        # 合并成员信息
        member = get_member(group_id, p["member_id"])
        result.append({
            "member_id": p["member_id"],
            "display_name": p["display_name"],
            "avatar": member["avatar"] if member else "",
            "total_messages": p["total_analyzed_messages"],
            "portrait": pj,
            "data_start_date": p.get("data_start_date") or "",
            "data_end_date": p.get("data_end_date") or "",
            "last_updated": p["last_updated"],
        })

    return {"code": 200, "message": "获取成功", "data": result}


@router.get("/portrait/{member_id}")
async def api_get_single_portrait(group_id: int, member_id: int):
    """获取单个成员的画像"""
    portrait = get_portrait(group_id, member_id)
    if not portrait:
        raise HTTPException(404, detail="该成员尚无画像，请先分析几天数据")

    try:
        pj = json.loads(portrait["portrait_json"])
    except (json.JSONDecodeError, TypeError):
        pj = {}

    member = get_member(group_id, member_id)
    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "member_id": member_id,
            "display_name": portrait["display_name"],
            "avatar": member["avatar"] if member else "",
            "total_messages": portrait["total_analyzed_messages"],
            "portrait": pj,
            "data_start_date": portrait.get("data_start_date") or "",
            "data_end_date": portrait.get("data_end_date") or "",
            "last_updated": portrait["last_updated"],
        },
    }


async def _run_portrait_and_save(group_id: int, member_id: int, task):
    """后台执行：画像生成 + 保存"""
    group = get_group(group_id)
    chat = get_chat_cache(group_id)
    member = get_member(group_id, member_id)
    if not all([group, chat, member]):
        task.finish(success=False, error={"type": "data_missing", "detail": "数据未找到"})
        return

    result = await generate_single_portrait(
        group_id=group_id,
        group_name=group["name"],
        sender_id=member["sender_id"],
        sender_name=member["display_name"] or member["nickname"],
        chat=chat,
        model=config.OLLAMA_MODEL,
        task=task,
    )

    if result["success"] and result["data"]:
        from models.database import save_member_portrait
        portrait_json = json.dumps(result["data"], ensure_ascii=False)
        save_member_portrait(
            group_id=group_id, member_id=member_id,
            display_name=member["display_name"] or member["nickname"],
            total_messages=result.get("_analyzed_msg_count", member["message_count"]),
            portrait_json=portrait_json,
            data_start=result.get("_data_start") or group.get("date_range_start") or "",
            data_end=result.get("_data_end") or group.get("date_range_end") or "",
        )
        task.finish(success=True)
        log_analysis(group_id, "", "portrait", "success", duration_ms=result["duration_ms"])
    else:
        task.finish(success=False, error={"type": "ai_failed", "detail": result.get("error", "")})


@router.post("/portrait/{member_id}/refresh")
async def api_refresh_single_portrait(group_id: int, member_id: int):
    """刷新单个成员的画像（异步任务）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    member = get_member(group_id, member_id)
    if not member:
        raise HTTPException(404, detail="成员不存在")

    task = task_manager.create("portrait", group_id, {"member_id": member_id})
    task.update("pending", f"为 {member['display_name']} 生成画像...")
    asyncio.create_task(_run_portrait_and_save(group_id, member_id, task))

    return {
        "code": 200,
        "message": "任务已创建",
        "data": {"task_id": task.task_id, "status": "pending"},
    }


@router.post("/portraits/refresh-all")
async def api_refresh_all_portraits(group_id: int, force: bool = False):
    """刷新群内所有需要更新的画像"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    results = await refresh_portraits(
        group_id=group_id,
        group_name=group["name"],
        chat=chat,
        model=config.OLLAMA_MODEL,
        force=force,
    )

    refreshed_count = sum(1 for r in results if r["refreshed"])
    return {
        "code": 200,
        "message": f"画像刷新完成，{refreshed_count}/{len(results)} 个需要更新",
        "data": {
            "total": len(results),
            "refreshed": refreshed_count,
            "results": [
                {
                    "member_name": r["member"]["display_name"],
                    "refreshed": r["refreshed"],
                    "portrait": r["portrait"]["portrait_json"] if r["portrait"] and isinstance(r["portrait"], dict) and "portrait_json" in r["portrait"] else r.get("portrait"),
                }
                for r in results
            ],
        },
    }
