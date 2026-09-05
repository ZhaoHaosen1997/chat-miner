"""
异步任务管理器
管理 AI 分析任务的创建、执行、进度追踪和取消
通过 asyncio.Queue + SSE 实现实时进度推送
"""
import asyncio
import logging
import uuid
import time
from datetime import datetime
from typing import Optional, AsyncGenerator

logger = logging.getLogger(__name__)

# v1.19.6: 活跃/终态状态集中定义
# ACTIVE 含 parsing——解析阶段同样不可重入、可取消、需被 stale 清理覆盖
ACTIVE_STATUSES = ("pending", "waiting_gpu", "inference", "parsing")
TERMINAL_STATUSES = ("done", "failed", "cancelled")


class TaskBusyError(Exception):
    """v1.19.6: 同群同类型任务已在运行，拒绝重入（main.py 映射为 HTTP 409）"""
    def __init__(self, task_type: str, group_id):
        self.task_type = task_type
        self.group_id = group_id
        super().__init__(f"该群已有同类型任务运行中: {task_type}")


class TaskInfo:
    """单个任务的状态信息"""

    def __init__(self, task_id: str, task_type: str, group_id: int, params: dict = None):
        self.task_id = task_id
        self.type = task_type  # "analyze_day" | "analyze_all" | "portrait"
        self.group_id = group_id
        self.params = params or {}
        self.status = "pending"  # pending|waiting_gpu|inference|parsing|done|failed|cancelled
        self.step = "等待开始"
        self.progress = {"current": 0, "total": 0}  # 批量任务用
        self.error = None  # {type, detail}
        self.model_used = ""
        self.started_at = ""
        self.duration_ms = 0
        self.steps = []  # [{name, status, duration_ms, model, error}]
        self._start_time = 0.0
        # SSE 事件队列（v0.13.2: 增大队列防丢事件）
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        # v1.19.6: 订阅/创建时捕获的事件循环引用——工作线程经 to_thread 调 update()
        # 时 asyncio.Queue 非线程安全，必须用 call_soon_threadsafe 转投
        self._loop = None
        # 取消标志
        self._cancelled = False
        # v0.12.4: 降级标记
        self.fallback = False

    def start(self):
        self._start_time = time.time()
        self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status = "pending"

    def _capture_loop(self):
        """在事件循环上下文中捕获 loop（create/subscribe 时调用）"""
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass  # 工作线程上下文，无运行中的 loop

    def _push_event(self):
        """线程安全地推送事件到 SSE 队列"""
        event = self.to_event()
        loop = self._loop
        if loop is not None and loop.is_running():
            def _put():
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"SSE 队列已满，丢弃事件: task={self.task_id}")
            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                # loop 已关闭，退化为直接投递
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
        else:
            # 尚未捕获 loop：仅缓冲无订阅者，直接投递安全
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"SSE 队列已满，丢弃事件: task={self.task_id}")

    def update(self, status: str, step: str, progress: dict = None, error: dict = None, fallback: bool = False):
        # v1.19.6: 终态保护——取消/完成后不再接受状态翻转
        #（管线下一步 update("inference") 或收尾 finish(success=True) 不能把 cancelled 改回去）
        if self.status in TERMINAL_STATUSES:
            logger.debug(f"任务 {self.task_id} 已终态({self.status})，忽略 update({status})")
            return
        self.status = status
        self.step = step
        if progress:
            self.progress = progress
        if error:
            self.error = error
        if fallback:
            self.fallback = True
        if self._start_time:
            self.duration_ms = int((time.time() - self._start_time) * 1000)
        # 推送到 SSE 队列
        self._push_event()

    def clear_fallback(self):
        """清除降级标记（当在线模型恢复时调用）"""
        if self.fallback and self.status not in TERMINAL_STATUSES:
            self.fallback = False
            self._push_event()

    def finish(self, success: bool = True, error: dict = None, step: str = ""):
        if success:
            self.update("done", step or "完成")
        else:
            self.update("failed", step or "失败", error=error)

    def cancel(self):
        self._cancelled = True
        logger.info("任务已取消: %s", self.task_id)
        self.update("cancelled", "已取消")

    def add_step(self, name: str, status: str = "running", duration_ms: int = 0,
                 model: str = "", error: str = ""):
        """记录一个子步骤"""
        self.steps.append({
            "name": name, "status": status, "duration_ms": duration_ms,
            "model": model, "error": error,
        })
        # 推进到当前步骤
        done = sum(1 for s in self.steps if s["status"] == "done")
        self.update("inference", f"({done}/{len(self.steps)}) {name}...",
                   progress={"current": done, "total": len(self.steps)})

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "type": self.type,
            "group_id": self.group_id,
            "status": self.status,
            "step": self.step,
            "progress": self.progress,
            "error": self.error,
            "model_used": self.model_used,
            "fallback": self.fallback,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "steps": self.steps,
        }

    def to_event(self) -> str:
        import json
        return f"data: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n"


class TaskManager:
    """单例任务管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks = {}
        return cls._instance

    def create(self, task_type: str, group_id: int, params: dict = None) -> TaskInfo:
        # 清理已完成超过 30 分钟的旧任务（防止内存泄漏）
        self._cleanup_stale()
        task_id = uuid.uuid4().hex[:12]
        task = TaskInfo(task_id, task_type, group_id, params)
        task.start()
        task._capture_loop()  # 路由多为 async 上下文，尽早捕获 loop
        self._tasks[task_id] = task
        logger.debug(f"创建任务: {task_id} type={task_type} group={group_id}")
        return task

    def create_checked(self, task_type: str, group_id: int, params: dict = None) -> TaskInfo:
        """v1.19.6: 带防重入闸门的创建——同群同类型任务活跃时抛 TaskBusyError。

        group_id 为 None 的任务（如画像综合）不做群级防重入，保持原 create 行为。"""
        if group_id is not None and self.has_active(task_type, group_id):
            raise TaskBusyError(task_type, group_id)
        return self.create(task_type, group_id, params)

    def _cleanup_stale(self, max_age_seconds: int = 1800):
        """清理已完成/失败/取消的旧任务（默认 30 分钟）
        v0.13.3: 同时清理卡住的 running 任务（超过 2 小时无进度）
        v1.19.6: 卡住任务置为 failed 时推送终态事件，唤醒 SSE 订阅循环退出（防连接泄漏）
        """
        now = time.time()
        stale_ids = []
        for tid, t in self._tasks.items():
            if t.status in TERMINAL_STATUSES:
                if t._start_time > 0 and (now - t._start_time) > max_age_seconds:
                    stale_ids.append(tid)
            # 卡住的活跃任务（超过 2 小时）
            elif t.status in ACTIVE_STATUSES:
                if t._start_time > 0 and (now - t._start_time) > 7200:
                    logger.warning(f"清理卡住的任务: {tid} type={t.type} status={t.status}")
                    t.update("failed", "任务执行超时（2小时），已自动清理",
                             error={"type": "stale_task", "detail": "任务执行超时（2小时），已自动清理"})
                    stale_ids.append(tid)
        for tid in stale_ids:
            self._tasks.pop(tid, None)
        if stale_ids:
            logger.info(f"清理 {len(stale_ids)} 个过期/卡住任务")

    def get(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def has_active(self, task_type: str, group_id: int) -> bool:
        """检查指定群是否已有同类型任务正在执行。"""
        for t in self._tasks.values():
            if (t.type == task_type and t.group_id == group_id
                    and t.status in ACTIVE_STATUSES):
                return True
        return False

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in ACTIVE_STATUSES:
            task.cancel()
            return True
        logger.warning("无法取消任务 %s: 未找到或已完成", task_id)
        return False

    def remove(self, task_id: str):
        self._tasks.pop(task_id, None)

    def list_tasks(self, group_id: int = None) -> list[dict]:
        tasks = list(self._tasks.values())
        if group_id is not None:
            tasks = [t for t in tasks if t.group_id == group_id]
        return [t.to_dict() for t in tasks]

    async def subscribe(self, task_id: str) -> AsyncGenerator[str, None]:
        """SSE 事件流订阅

        Args:
            task_id: 任务 ID

        Yields:
            SSE 格式的事件字符串
        """
        task = self._tasks.get(task_id)
        if not task:
            yield f"data: {{\"error\": \"任务不存在\"}}\n\n"
            return

        # v1.19.6: 捕获订阅方所在事件循环，后续工作线程的 update 经
        # call_soon_threadsafe 转投，保证 get() 等待者被正确唤醒
        task._capture_loop()

        # 先发重连间隔设置（30 秒，避免浏览器默认 3 秒过于激进）
        yield "retry: 30000\n\n"

        # 再发当前状态
        yield task.to_event()

        # 持续监听状态变化
        while task.status not in TERMINAL_STATUSES:
            try:
                event = await asyncio.wait_for(task._queue.get(), timeout=30)
                yield event
            except asyncio.TimeoutError:
                # 心跳
                yield f": heartbeat\n\n"

        # 最终状态
        yield task.to_event()

    def is_cancelled(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return task._cancelled if task else False


# 全局单例
task_manager = TaskManager()
