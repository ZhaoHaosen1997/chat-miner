"""
WeFlow 同步 API 路由
提供会话列表、增量同步、群关联、状态查询
"""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import config
from models.database import get_group, list_groups, save_task_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weflow", tags=["WeFlow"])


# ---- 请求模型 ----

class SyncRequest(BaseModel):
    group_id: int = Field(..., description="chat-miner 群 ID")


class LinkRequest(BaseModel):
    group_id: int = Field(..., description="chat-miner 群 ID")
    chatroom_id: str = Field(..., description="WeFlow 会话 ID (群聊: xxx@chatroom / 私聊: wxid_xxx)")


# ---- 辅助函数 ----

def _get_client():
    """从 config 创建 WeFlow 客户端"""
    from services.weflow_client import WeFlowClient
    token = config.WEFLOW_ACCESS_TOKEN
    if not token:
        raise HTTPException(400, "WeFlow Access Token 未配置，请在设置页面填写")
    return WeFlowClient(base_url=config.WEFLOW_BASE_URL, access_token=token)


def _require_wechat_group(group_id: int) -> dict:
    """验证群存在且为微信平台（WeFlow 仅支持微信群聊）

    Returns:
        group dict on success
    Raises:
        HTTPException(404) if group not found
        HTTPException(400) if group is QQ (platform='qq')
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, f"群不存在: group_id={group_id}")
    if group.get("platform") == "qq":
        raise HTTPException(400, "QQ 群不支持 WeFlow 同步，WeFlow 仅支持微信群聊")
    return group


# ---- API ----

@router.get("/sessions")
async def get_sessions(keyword: str = "", limit: int = 200):
    """获取 WeFlow 会话列表（用于关联已有群）"""
    client = _get_client()
    try:
        sessions = client.list_sessions(keyword=keyword, limit=limit)
        # 获取已关联的群 wxid 列表
        groups = list_groups()
        linked_wxids = {g["wxid"] for g in groups if g.get("wxid")}

        # 标记关联状态 + 附带自动同步信息
        for s in sessions:
            s["linked"] = s.get("id") in linked_wxids
            if s["linked"]:
                linked_group = next(
                    (g for g in groups if g.get("wxid") == s["id"]), None
                )
                if linked_group:
                    s["group_id"] = linked_group["id"]
                    s["group_name"] = linked_group["name"]
                    s["auto_sync"] = bool(linked_group.get("weflow_auto_sync", 0))
                    s["last_sync_at"] = linked_group.get("weflow_last_sync_at", "")
                    s["last_sync_result"] = linked_group.get("weflow_last_sync_result", "")
        return {
            "code": 200,
            "message": "ok",
            "data": {"sessions": sessions, "count": len(sessions)},
        }
    except Exception as e:
        raise HTTPException(500, f"WeFlow 请求失败: {e}")
    finally:
        client.close()


@router.post("/sync/{group_id}")
async def trigger_sync(group_id: int):
    """手动触发增量同步（返回 task_id 供 ProgressPanel 订阅）"""
    from services.task_manager import task_manager
    from services.weflow_client import WeFlowClient, WeFlowError
    from services.weflow_sync import sync_messages_incremental

    group = _require_wechat_group(group_id)

    wxid = group.get("wxid", "")
    if not wxid:
        raise HTTPException(400, f"群 wxid 为空，请先关联 WeFlow 会话")

    client = _get_client()

    # 检查 WeFlow 可用性
    if not client.health_check():
        client.close()
        raise HTTPException(503, f"WeFlow 不可用 ({config.WEFLOW_BASE_URL})，请确认 WeFlow 正在运行")

    task = task_manager.create("weflow_sync", group_id, {"group_name": group["name"]})
    task.update("pending", f"开始增量同步 {group['name']}...")

    async def _run():
        try:
            result = await asyncio.to_thread(
                sync_messages_incremental, client, group_id, task=task
            )
            if result.get("cancelled"):
                return
            added = result.get("added", 0)
            logger.info(f"[WeFlow Sync] {group['name']}: +{added} 新消息")
            task.finish(success=True)
            # v1.3.0: 持久化任务记录
            save_task_record(
                task_id=task.task_id, group_id=group_id, task_type="weflow_sync",
                target=group["name"], status=task.status,
                total_duration_ms=task.duration_ms, model_used="",
                steps_json="[]", error_summary="",
                message_count=added,
            )
        except Exception as e:
            logger.error(f"[WeFlow Sync] {group['name']} 失败: {e}")
            task.finish(success=False, error={"message": str(e)})
            # v1.13.0: 失败也持久化
            save_task_record(
                task_id=task.task_id, group_id=group_id, task_type="weflow_sync",
                target=group["name"], status="failed",
                total_duration_ms=task.duration_ms, model_used="",
                steps_json="[]", error_summary=str(e)[:200],
            )
        finally:
            client.close()

    asyncio.create_task(_run())
    return {
        "code": 200,
        "message": "同步任务已创建",
        "data": {"task_id": task.task_id},
    }


@router.post("/link")
async def link_group(req: LinkRequest):
    """关联已有群到 WeFlow 会话"""
    from services.weflow_client import WeFlowClient, WeFlowError
    from services.weflow_sync import link_group_to_weflow

    group = _require_wechat_group(req.group_id)

    if not req.chatroom_id:
        raise HTTPException(400, "chatroom_id 不能为空")

    client = _get_client()
    try:
        result = link_group_to_weflow(req.group_id, req.chatroom_id, client)
        return {"code": 200, "message": "关联成功", "data": result}
    except WeFlowError as e:
        raise HTTPException(503, f"WeFlow 请求失败: {e}")
    finally:
        client.close()


@router.get("/status")
async def get_status():
    """获取 WeFlow 连接状态 + 各群上次同步时间"""
    from services.weflow_client import WeFlowClient

    token = config.WEFLOW_ACCESS_TOKEN
    if not token:
        return {
            "code": 200, "message": "ok",
            "data": {
                "enabled": config.WEFLOW_ENABLED,
                "connected": False,
                "error": "Token 未配置",
                "groups": [],
            },
        }

    client = WeFlowClient(base_url=config.WEFLOW_BASE_URL, access_token=token)
    connected = client.health_check()
    client.close()

    groups = list_groups()
    group_status = []
    for g in groups:
        wxid = g.get("wxid", "")
        if wxid:
            group_status.append({
                "group_id": g["id"],
                "name": g["name"],
                "chatroom_id": wxid,
                "date_range_end": g.get("date_range_end", ""),
                "message_count": g.get("message_count", 0),
                "auto_sync": bool(g.get("weflow_auto_sync", 0)),
                "last_sync_at": g.get("weflow_last_sync_at", ""),
                "last_sync_result": g.get("weflow_last_sync_result", ""),
            })

    return {
        "code": 200, "message": "ok",
        "data": {
            "enabled": config.WEFLOW_ENABLED,
            "connected": connected,
            "base_url": config.WEFLOW_BASE_URL,
            "sync_interval_hours": config.WEFLOW_SYNC_INTERVAL_HOURS,
            "groups": group_status,
        },
    }


@router.post("/unlink/{group_id}")
async def unlink_group(group_id: int):
    """取消群与 WeFlow 会话的关联"""
    from models.database import get_conn
    group = _require_wechat_group(group_id)
    conn = None
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE chat_groups SET weflow_auto_sync=0 WHERE id=?",
            (group_id,)
        )
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {
        "code": 200,
        "message": "已取消关联",
        "data": {"group_id": group_id},
    }


class AutoSyncToggle(BaseModel):
    enabled: bool = Field(..., description="是否开启自动同步")


@router.put("/auto-sync/{group_id}")
async def toggle_auto_sync(group_id: int, body: AutoSyncToggle):
    """按群开关 WeFlow 自动同步"""
    from models.database import get_conn
    group = _require_wechat_group(group_id)
    conn = None
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE chat_groups SET weflow_auto_sync=? WHERE id=?",
            (1 if body.enabled else 0, group_id)
        )
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {
        "code": 200,
        "message": f"自动同步已{'开启' if body.enabled else '关闭'}",
        "data": {"group_id": group_id, "auto_sync": body.enabled},
    }
