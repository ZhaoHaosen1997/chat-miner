"""
定时调度模块
基于 APScheduler，管理 WeFlow 增量同步定时任务
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler():
    """在 main.py lifespan 中调用，启动定时任务"""
    if not config.WEFLOW_ENABLED:
        logger.info("WeFlow 自动同步未启用，跳过调度器")
        return

    interval_hours = max(1, config.WEFLOW_SYNC_INTERVAL_HOURS)

    scheduler.add_job(
        run_scheduled_sync,
        trigger="interval",
        hours=interval_hours,
        id="weflow_sync",
        name="WeFlow 增量同步",
        replace_existing=True,
        misfire_grace_time=600,  # 错过 10 分钟内仍执行
    )

    scheduler.start()
    logger.info(f"WeFlow 调度器已启动: 每 {interval_hours} 小时同步一次")


def shutdown_scheduler():
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("WeFlow 调度器已关闭")


def reload_scheduler():
    """配置变更后重载调度器（修改间隔时调用）"""
    if not config.WEFLOW_ENABLED:
        if scheduler.running:
            shutdown_scheduler()
        return

    job = scheduler.get_job("weflow_sync")
    if job:
        new_interval = max(1, config.WEFLOW_SYNC_INTERVAL_HOURS)
        if job.trigger.interval != new_interval:
            job.reschedule(trigger="interval", hours=new_interval)
            logger.info(f"WeFlow 同步间隔已更新: {new_interval}h")

    if not scheduler.running:
        init_scheduler()


async def run_scheduled_sync():
    """定时任务：遍历所有已配 WeFlow 的群，执行增量同步"""
    from models.database import list_groups
    from services.weflow_client import WeFlowClient, WeFlowError
    from services.weflow_sync import sync_messages_incremental

    token = config.WEFLOW_ACCESS_TOKEN
    if not token:
        logger.warning("[WeFlow Scheduler] Token 未配置，跳过同步")
        return

    base_url = config.WEFLOW_BASE_URL
    client = WeFlowClient(base_url=base_url, access_token=token)

    if not client.health_check():
        logger.warning(f"[WeFlow Scheduler] WeFlow 不可用 ({base_url})，跳过本次同步")
        client.close()
        return

    groups = list_groups()
    synced = 0
    failed = 0

    for g in groups:
        wxid = g.get("wxid", "")
        # 只同步群聊（wxid 含 @chatroom）
        if not wxid or "@chatroom" not in wxid:
            continue

        try:
            result = await asyncio.to_thread(
                sync_messages_incremental, client, g["id"]
            )
            if result.get("added", 0) > 0:
                synced += 1
                logger.info(f"[WeFlow Scheduler] {g['name']}: "
                            f"+{result['added']} 条新消息")
            if result.get("cancelled"):
                break
        except Exception as e:
            failed += 1
            logger.error(f"[WeFlow Scheduler] {g['name']} 同步失败: {e}")

    client.close()
    logger.info(f"[WeFlow Scheduler] 完成: {synced} 群有新消息, "
                f"{failed} 失败, {len(groups) - synced - failed} 无变化")
