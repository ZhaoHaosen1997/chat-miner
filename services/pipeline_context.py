"""
v1.19.x PipelineContext — 统一的管线执行上下文

封装 task_manager + call_online_chat + save_task_record，
让各管线只需关注业务逻辑，日志和任务记录自动就位。
"""
import logging
from models.database import save_task_record

logger = logging.getLogger(__name__)


class PipelineContext:
    """管线执行上下文，封装任务生命周期和 AI 调用日志"""

    def __init__(self, pipeline: str, group_id: int, group_name: str,
                 model_config: dict):
        self.pipeline = pipeline
        self.group_id = group_id
        self.group_name = group_name
        self.model_config = model_config
        self._task = None  # TaskInfo | None

    @property
    def task(self):
        return self._task

    # ── 任务生命周期 ────────────────────────────────────────

    def start_task(self, task_type: str, target: str = "", params: dict = None):
        """创建任务记录（内存 + 后续 finish 时写 DB）"""
        from services.task_manager import task_manager
        self._task = task_manager.create(task_type, self.group_id, params or {})
        self._task.update("pending", target or task_type)
        return self._task

    def update_task(self, status: str, step: str, progress: dict = None):
        """更新任务状态"""
        if self._task:
            self._task.update(status, step, progress=progress)

    def finish_task(self, success: bool = True, error: dict = None):
        """完成任务 + 持久化到 DB"""
        if not self._task:
            return
        self._task.finish(success=success, error=error)
        try:
            status = "done" if success else "failed"
            error_summary = error.get("detail", "") if error else ""
            save_task_record(
                task_id=self._task.task_id,
                group_id=self.group_id,
                task_type=self._task.type,
                target=f"{self.group_name}/{self._task.step}",
                status=status,
                total_duration_ms=self._task.duration_ms,
                model_used=self._task.model_used,
                steps_json="[]",
                error_summary=error_summary,
            )
        except Exception as e:
            logger.warning("PipelineContext finish_task 持久化失败: %s", e)

    # ── AI 调用 ──────────────────────────────────────────────

    async def call_ai(self, system_prompt: str, user_prompt: str,
                      **kwargs) -> dict:
        """调用在线模型，自动注入 pipeline/group_id/task_id"""
        from services.online_model import call_online_chat

        # 注入上下文参数，kwargs 中的同名值优先（允许覆盖）
        ctx_params = {
            "pipeline": self.pipeline,
            "group_id": self.group_id,
        }
        if self._task:
            ctx_params["task_id"] = self._task.task_id

        # kwargs 优先级高于 ctx（特殊情况允许覆盖）
        for k, v in ctx_params.items():
            if k not in kwargs:
                kwargs[k] = v

        return await call_online_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_config=self.model_config,
            **kwargs,
        )
