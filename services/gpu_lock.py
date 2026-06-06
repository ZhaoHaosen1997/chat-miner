"""
GPU 分布式锁模块
通过 Dashboard (8850) 的 GPU 锁接口，协调多个应用对 GPU 的使用
防止 Ollama、ComfyUI 等同时抢占显存导致 OOM

接口规格参考: E:/hermes/gpu-lock-usage.md
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import httpx

from config import config

logger = logging.getLogger(__name__)

LOCK_CHECK_URL = f"{config.GPU_LOCK_URL}/api/gpu/lock/check"
LOCK_URL = f"{config.GPU_LOCK_URL}/api/gpu/lock"


async def check_gpu_free() -> bool:
    """检测 GPU 是否空闲

    Returns:
        True: GPU 空闲可用
        False: GPU 被占用
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(LOCK_CHECK_URL)
            return resp.status_code == 200
    except httpx.ConnectError:
        logger.warning(f"无法连接到 GPU 锁服务 ({config.GPU_LOCK_URL})，假定 GPU 空闲")
        return True
    except Exception as e:
        logger.warning(f"GPU 锁检查异常: {e}，假定 GPU 空闲")
        return True


async def get_lock_owner() -> str | None:
    """查看谁占着 GPU

    Returns:
        占用者名称，空闲返回 None
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(LOCK_URL)
            data = resp.json()
            if data.get("locked"):
                return data.get("who", "unknown")
            return None
    except Exception as e:
        logger.warning(f"查询 GPU 锁持有者失败: {e}")
        return None


async def acquire_lock(who: str = "") -> bool:
    """加锁，标记 GPU 正在被使用

    Args:
        who: 使用者标识，默认使用配置中的 GPU_LOCK_WHO

    Returns:
        True: 加锁成功
        False: 加锁失败（已被他人占用）
    """
    who = who or config.GPU_LOCK_WHO
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.put(
                LOCK_URL,
                headers={"Content-Type": "application/json"},
                json={"who": who},
            )
            if resp.status_code == 200:
                logger.info(f"GPU 锁已获取 (who={who})")
                return True
            else:
                logger.warning(f"GPU 锁获取失败: HTTP {resp.status_code}")
                return False
    except Exception as e:
        logger.warning(f"GPU 锁获取异常: {e}")
        return False


async def release_lock() -> bool:
    """解锁，释放 GPU

    Returns:
        True: 解锁成功
        False: 解锁失败
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.delete(LOCK_URL)
            if resp.status_code == 200:
                logger.info("GPU 锁已释放")
                return True
            else:
                logger.warning(f"GPU 锁释放失败: HTTP {resp.status_code}")
                return False
    except Exception as e:
        logger.warning(f"GPU 锁释放异常: {e}")
        return False


@asynccontextmanager
async def gpu_lock(who: str = ""):
    """GPU 锁异步上下文管理器

    自动处理：检查 → 等待 → 加锁 → [执行任务] → 解锁

    Usage:
        async with gpu_lock("chat-miner"):
            result = await call_ollama(...)

    如果 GPU 被占用，会等待并重试，直到超时。
    如果锁服务不可达，降级为直接执行（不阻塞）。

    Raises:
        RuntimeError: 超过最大重试次数仍未获取到锁
    """
    who = who or config.GPU_LOCK_WHO

    if not config.GPU_LOCK_ENABLED:
        logger.debug("GPU 锁已禁用，跳过")
        yield
        return

    # 1. 检查 + 等待
    retries = 0
    while retries < config.GPU_LOCK_MAX_RETRIES:
        is_free = await check_gpu_free()
        if is_free:
            break

        owner = await get_lock_owner()
        # 如果锁是 chat-miner 自己持有的（上次崩溃残留），强制解锁
        if owner == who:
            logger.warning(f"GPU 锁被自己({who})占用（可能是上次崩溃残留），强制解锁")
            await release_lock()
            await asyncio.sleep(1)
            continue

        retries += 1
        logger.info(
            f"GPU 被 '{owner}' 占用，等待 {config.GPU_LOCK_RETRY_INTERVAL}s "
            f"({retries}/{config.GPU_LOCK_MAX_RETRIES})..."
        )
        await asyncio.sleep(config.GPU_LOCK_RETRY_INTERVAL)
    else:
        owner = await get_lock_owner()
        raise RuntimeError(
            f"GPU 一直被 '{owner}' 占用，等待 {config.GPU_LOCK_MAX_RETRIES * config.GPU_LOCK_RETRY_INTERVAL}s 后放弃"
        )

    # 2. 加锁
    acquired = await acquire_lock(who)
    if not acquired:
        # 可能刚好被别人抢了，再等一轮
        await asyncio.sleep(config.GPU_LOCK_RETRY_INTERVAL)
        acquired = await acquire_lock(who)
        if not acquired:
            logger.warning("GPU 加锁失败，降级为无锁执行")
            # 降级：不阻塞，直接执行
            yield
            return

    # 3. 执行任务
    try:
        yield
    finally:
        # 4. 解锁
        await release_lock()
