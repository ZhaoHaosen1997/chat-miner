"""
统计 API：全局统计、群统计
"""
import logging

from fastapi import APIRouter, HTTPException
from config import config
from services.stats import compute_global_stats, compute_group_stats
from services.analyzer import check_ollama_health
from services.gpu_lock import check_gpu_free, get_lock_owner
from services.online_model import check_deepseek_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["统计"])


@router.get("/health")
async def api_health():
    """健康检查 + Ollama 连通性 + GPU 锁状态 + DeepSeek 连通性"""
    ollama = await check_ollama_health()
    deepseek = await check_deepseek_health()

    # GPU 锁状态
    gpu_status = {"enabled": config.GPU_LOCK_ENABLED, "lock_url": config.GPU_LOCK_URL}
    if config.GPU_LOCK_ENABLED:
        gpu_free = await check_gpu_free()
        gpu_status["gpu_free"] = gpu_free
        if not gpu_free:
            gpu_status["locked_by"] = await get_lock_owner()

    return {
        "code": 200,
        "message": "服务正常运行",
        "data": {
            "status": "ok",
            "ollama": ollama,
            "deepseek": deepseek,
            "gpu_lock": gpu_status,
        },
    }


@router.get("/stats/global")
async def api_global_stats():
    """全局统计（所有群汇总）"""
    stats = compute_global_stats()
    return {"code": 200, "message": "获取成功", "data": stats}


@router.get("/groups/{group_id}/stats")
async def api_group_stats(group_id: int):
    """某个群的统计"""
    stats = compute_group_stats(group_id)
    if not stats:
        raise HTTPException(404, detail="群不存在")
    return {"code": 200, "message": "获取成功", "data": stats}
