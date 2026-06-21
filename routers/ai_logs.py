"""
v1.19.0 AI 调用日志 API
"""
from fastapi import APIRouter, Query
from models.database import get_ai_call_logs, get_ai_call_log
from services.ai_logger import AILogger

router = APIRouter(prefix="/api/ai-logs", tags=["AI调用日志"])


@router.get("")
async def api_list_logs(
    task_id: int = Query(0, description="按任务 ID 筛选"),
    pipeline: str = Query("", description="按管线筛选"),
    group_id: int = Query(0, description="按群 ID 筛选"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    logs = get_ai_call_logs(
        task_id=task_id, pipeline=pipeline, group_id=group_id,
        limit=limit, offset=offset,
    )
    return {"code": 200, "message": "ok", "data": logs}


@router.get("/{log_id}")
async def api_get_log(log_id: int):
    log = get_ai_call_log(log_id)
    if not log:
        return {"code": 404, "message": "日志不存在", "data": None}
    return {"code": 200, "message": "ok", "data": log}


@router.post("/cleanup")
async def api_cleanup_logs():
    AILogger.cleanup()
    return {"code": 200, "message": "清理完成", "data": None}
