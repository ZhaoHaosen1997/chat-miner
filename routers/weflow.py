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
from models.database import get_group, list_groups

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weflow", tags=["WeFlow"])


# ---- 请求模型 ----

class SyncRequest(BaseModel):
    group_id: int = Field(..., description="chat-miner 群 ID")


class LinkRequest(BaseModel):
    group_id: int = Field(..., description="chat-miner 群 ID")
    chatroom_id: str = Field(..., description="WeFlow 会话 ID (xxx@chatroom)")


# ---- 辅助函数 ----

def _get_client():
    """从 config 创建 WeFlow 客户端"""
    from services.weflow_client import WeFlowClient
    token = config.WEFLOW_ACCESS_TOKEN
    if not token:
        raise HTTPException(400, "WeFlow Access Token 未配置，请在设置页面填写")
    return WeFlowClient(base_url=config.WEFLOW_BASE_URL, access_token=token)


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

        # 标记关联状态
        for s in sessions:
            s["linked"] = s.get("id") in linked_wxids
            if s["linked"]:
                linked_group = next(
                    (g for g in groups if g.get("wxid") == s["id"]), None
                )
                if linked_group:
                    s["group_id"] = linked_group["id"]
                    s["group_name"] = linked_group["name"]
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

    group = get_group(group_id)
    if not group:
        raise HTTPException(404, f"群不存在: group_id={group_id}")

    wxid = group.get("wxid", "")
    if not wxid or "@chatroom" not in wxid:
        raise HTTPException(400, f"群 wxid 不是合法群聊: {wxid}，请先关联 WeFlow 会话")

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
            logger.info(f"[WeFlow Sync] {group['name']}: +{result['added']} 新消息")
        except Exception as e:
            logger.error(f"[WeFlow Sync] {group['name']} 失败: {e}")
            task.finish(success=False, error={"message": str(e)})
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

    group = get_group(req.group_id)
    if not group:
        raise HTTPException(404, f"群不存在: group_id={req.group_id}")

    if "@chatroom" not in req.chatroom_id:
        raise HTTPException(400, "chatroom_id 必须是 xxx@chatroom 格式")

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
        if "@chatroom" in wxid:
            group_status.append({
                "group_id": g["id"],
                "name": g["name"],
                "chatroom_id": wxid,
                "date_range_end": g.get("date_range_end", ""),
                "message_count": g.get("message_count", 0),
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
