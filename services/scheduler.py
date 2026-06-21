"""
定时调度模块
基于 APScheduler，管理 WeFlow 增量同步定时任务
"""
import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config

logger = logging.getLogger(__name__)
from models.database import save_task_record

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
        start_date=datetime.now() + timedelta(seconds=120),  # 延迟 2min，等待 WeFlow 完全就绪
    )

    scheduler.start()
    logger.info(f"WeFlow 调度器已启动: 每 {interval_hours} 小时同步一次")

    # 输出启用自动同步的群列表
    try:
        from models.database import list_groups
        groups = list_groups()
        auto_sync_groups = [g for g in groups if g.get("weflow_auto_sync", 0)]
        if auto_sync_groups:
            names = [g.get("name", "?") for g in auto_sync_groups]
            logger.info(f"WeFlow 自动同步: {len(auto_sync_groups)} 个群启用 — {', '.join(names)}")
        else:
            logger.info("WeFlow 自动同步: 当前没有群启用自动同步（请在同步弹窗中为各群开启）")
    except Exception as e:
        logger.debug("统计自动同步群数量失败: %s", e)


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
        if job.trigger.interval.total_seconds() / 3600 != new_interval:
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
    except Exception as e:
        logger.warning("更新同步时间戳失败: %s", e)
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
            logger.info(f"[WeFlow Scheduler] 跳过 {g.get('name', '?')} (id={g['id']}): wxid 为空，请先关联 WeFlow 会话")
            continue
        # 只同步开启了自动同步的群
        if not g.get("weflow_auto_sync", 0):
            logger.debug(f"[WeFlow Scheduler] 跳过 {g['name']} (id={g['id']}): 未开启自动同步")
            skipped += 1
            continue

        logger.info(f"[WeFlow Scheduler] 开始自动同步 {g['name']} (id={g['id']})")
        try:
            start = asyncio.get_event_loop().time()
            result = await asyncio.to_thread(
                sync_messages_incremental, client, g["id"]
            )
            duration = int((asyncio.get_event_loop().time() - start) * 1000)
            added = result.get("added", 0)
            if added > 0:
                synced += 1
                _update_sync_status(g["id"], f"+{added} 条")
                logger.info(f"[WeFlow Scheduler] {g['name']}: +{added} 条新消息")
            else:
                _update_sync_status(g["id"], "无新消息")
            # v1.13.0: 持久化任务记录
            save_task_record(
                task_id=f"auto_{g['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                group_id=g["id"], task_type="weflow_auto_sync",
                target=g["name"], status="done",
                total_duration_ms=duration, model_used="",
                steps_json="[]", error_summary="",
                message_count=added,
            )
            if result.get("cancelled"):
                break
        except Exception as e:
            failed += 1
            _update_sync_status(g["id"], f"失败: {str(e)[:80]}")
            logger.error(f"[WeFlow Scheduler] {g['name']} 同步失败: {e}")
            # v1.13.0: 失败也持久化
            save_task_record(
                task_id=f"auto_{g['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                group_id=g["id"], task_type="weflow_auto_sync",
                target=g["name"], status="failed",
                total_duration_ms=0, model_used="",
                steps_json="[]", error_summary=str(e)[:200],
            )

    client.close()

    auto_count = synced + failed + (len(groups) - synced - failed - skipped)
    logger.info(f"[WeFlow Scheduler] 完成: {synced} 群有新消息, "
                f"{failed} 失败, {skipped} 未开启, "
                f"{len(groups) - synced - failed - skipped} 无变化")

    # 如果所有开启自动同步的群都返回 0 条消息（可能是 WeFlow 未完全就绪），重试最多 3 次
    MAX_RETRIES = 3
    RETRY_DELAY = 60
    if synced == 0 and failed == 0 and auto_count > 0:
        logger.warning(f"[WeFlow Scheduler] 所有群均无新消息，可能 WeFlow 未就绪，开始重试（最多 {MAX_RETRIES} 次）...")
        for retry in range(1, MAX_RETRIES + 1):
            await asyncio.sleep(RETRY_DELAY)
            client2 = WeFlowClient(base_url=base_url, access_token=token)
            if not client2.health_check():
                logger.warning(f"[WeFlow Scheduler] 重试 {retry}/{MAX_RETRIES}: WeFlow 不可用")
                client2.close()
                continue
            retry_synced = 0
            for g in groups:
                if not g.get("wxid") or not g.get("weflow_auto_sync", 0):
                    continue
                try:
                    result = await asyncio.to_thread(
                        sync_messages_incremental, client2, g["id"]
                    )
                    added = result.get("added", 0)
                    if added > 0:
                        retry_synced += 1
                        _update_sync_status(g["id"], f"+{added} 条（重试{retry}）")
                        logger.info(f"[WeFlow Scheduler] 重试{retry} {g['name']}: +{added} 条")
                except Exception as e:
                    logger.error(f"[WeFlow Scheduler] 重试{retry} {g['name']} 失败: {e}")
            client2.close()
            if retry_synced > 0:
                logger.info(f"[WeFlow Scheduler] 重试{retry} 完成: {retry_synced} 群有新消息，停止重试")
                break
            logger.warning(f"[WeFlow Scheduler] 重试{retry}/{MAX_RETRIES}: 仍无新消息"
                           f"{'，继续重试...' if retry < MAX_RETRIES else '，已达上限'}")


# ==================== v1.16.1: 静默鱼塘调度器 ====================

async def run_pond_events():
    """被动事件 job：遍历所有群触发随机事件"""
    from models.database import list_groups
    groups = list_groups()
    if not groups:
        return

    triggered = 0
    for g in groups:
        try:
            from services.passive_events import trigger_passive_events
            results = trigger_passive_events(g["id"])
            if results:
                triggered += 1
        except Exception as e:
            logger.warning(f"鱼塘事件触发失败 group={g['id']}: {e}")

    if triggered:
        logger.info(f"[Pond Scheduler] {triggered}/{len(groups)} 个群触发被动事件")


def init_pond_scheduler():
    """启动鱼塘被动事件调度器"""
    if not getattr(config, "POND_AUTO_EVENTS_ENABLED", False):
        logger.info("静默鱼塘未开启，跳过调度器")
        return

    interval_minutes = max(1, getattr(config, "POND_EVENT_INTERVAL_MINUTES", 30))

    scheduler.add_job(
        run_pond_events,
        trigger="interval",
        minutes=interval_minutes,
        id="pond_events",
        name="鱼塘被动事件",
        replace_existing=True,
        misfire_grace_time=300,
    )

    if not scheduler.running:
        scheduler.start()

    logger.info(f"鱼塘调度器已启动: 每 {interval_minutes} 分钟触发一次被动事件")


def shutdown_pond_scheduler():
    """停止鱼塘调度器"""
    job = scheduler.get_job("pond_events")
    if job:
        job.remove()
        logger.info("鱼塘调度器已停止")


def reload_pond_scheduler():
    """配置变更后重载鱼塘调度器"""
    if not getattr(config, "POND_AUTO_EVENTS_ENABLED", False):
        if scheduler.get_job("pond_events"):
            shutdown_pond_scheduler()
        return

    job = scheduler.get_job("pond_events")
    new_interval = max(1, getattr(config, "POND_EVENT_INTERVAL_MINUTES", 30))

    if job:
        if job.trigger.interval.total_seconds() != new_interval * 60:
            job.reschedule(trigger="interval", minutes=new_interval)
            logger.info(f"鱼塘事件间隔已更新: {new_interval}min")
    else:
        init_pond_scheduler()
