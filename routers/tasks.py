"""
任务 API：查询任务状态、SSE 进度流
"""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from services.task_manager import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["任务"])


@router.get("/{task_id}")
async def api_get_task(task_id: str):
    """查询任务状态"""
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    return {"code": 200, "message": "获取成功", "data": task.to_dict()}


@router.get("/{task_id}/stream")
async def api_task_stream(task_id: str):
    """SSE 实时进度流"""
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")

    async def generate():
        async for event in task_manager.subscribe(task_id):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{task_id}")
async def api_cancel_task(task_id: str):
    """取消正在执行的任务"""
    if task_manager.cancel(task_id):
        return {"code": 200, "message": "任务已取消", "data": None}
    raise HTTPException(404, detail="任务不存在或已完成")
