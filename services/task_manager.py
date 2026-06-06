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
        self._start_time = 0.0
        # SSE 事件队列
        self._queue: asyncio.Queue = asyncio.Queue()
        # 取消标志
        self._cancelled = False

    def start(self):
        self._start_time = time.time()
        self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status = "pending"

    def update(self, status: str, step: str, progress: dict = None, error: dict = None):
        self.status = status
        self.step = step
        if progress:
            self.progress = progress
        if error:
            self.error = error
        if self._start_time:
            self.duration_ms = int((time.time() - self._start_time) * 1000)
        # 推送到 SSE 队列
        try:
            self._queue.put_nowait(self.to_event())
        except asyncio.QueueFull:
            pass

    def finish(self, success: bool = True, error: dict = None):
        if success:
            self.update("done", "完成")
        else:
            self.update("failed", "失败", error=error)

    def cancel(self):
        self._cancelled = True
        self.update("cancelled", "已取消")

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
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
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
        task_id = uuid.uuid4().hex[:12]
        task = TaskInfo(task_id, task_type, group_id, params)
        task.start()
        self._tasks[task_id] = task
        logger.info(f"创建任务: {task_id} type={task_type} group={group_id}")
        return task

    def get(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in ("pending", "waiting_gpu", "inference"):
            task.cancel()
            return True
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

        # 先发当前状态
        yield task.to_event()

        # 持续监听状态变化
        while task.status not in ("done", "failed", "cancelled"):
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
