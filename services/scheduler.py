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


def _update_sync_status(group_id: int, result: str):
    """更新群的上次同步时间和结果"""
    from models.database import get_conn
    from datetime import datetime
    conn = None
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE chat_groups SET weflow_last_sync_at=?, weflow_last_sync_result=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), result, group_id)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


async def run_scheduled_sync():
    """定时任务：只同步开启了 weflow_auto_sync 的群"""
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
    skipped = 0

    for g in groups:
        wxid = g.get("wxid", "")
        if not wxid:
            continue
        # 只同步开启了自动同步的群
        if not g.get("weflow_auto_sync", 0):
            skipped += 1
            continue

        try:
            result = await asyncio.to_thread(
                sync_messages_incremental, client, g["id"]
            )
            added = result.get("added", 0)
            if added > 0:
                synced += 1
                _update_sync_status(g["id"], f"+{added} 条")
                logger.info(f"[WeFlow Scheduler] {g['name']}: +{added} 条新消息")
            else:
                _update_sync_status(g["id"], "无新消息")
            if result.get("cancelled"):
                break
        except Exception as e:
            failed += 1
            _update_sync_status(g["id"], f"失败: {str(e)[:80]}")
            logger.error(f"[WeFlow Scheduler] {g['name']} 同步失败: {e}")

    client.close()
    logger.info(f"[WeFlow Scheduler] 完成: {synced} 群有新消息, "
                f"{failed} 失败, {skipped} 未开启, "
                f"{len(groups) - synced - failed - skipped} 无变化")
