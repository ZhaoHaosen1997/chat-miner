"""
v1.19.0 AI 调用日志 — 所有管线共享的调用记录器
"""
import time
import logging
from models.database import add_ai_call_log, cleanup_ai_call_logs, get_app_setting

logger = logging.getLogger(__name__)


class AILogger:
    """AI 调用日志记录器，供各管线在调用 AI 前后使用"""

    @staticmethod
    def log(task_id: int | None, pipeline: str, group_id: int,
            model_name: str, system_prompt: str, user_prompt: str,
            response_raw: str, duration_ms: int, success: bool,
            error: str = "") -> int:
        """记录一次 AI 调用。返回日志 ID"""
        token_estimate = len(system_prompt) + len(user_prompt) + len(response_raw)
        input_chars = len(system_prompt) + len(user_prompt)
        output_chars = len(response_raw)
        try:
            log_id = add_ai_call_log(
                task_id=task_id, pipeline=pipeline, group_id=group_id,
                model_name=model_name, system_prompt=system_prompt,
                user_prompt=user_prompt, response_raw=response_raw,
                token_estimate=token_estimate,
                input_chars=input_chars, output_chars=output_chars,
                duration_ms=duration_ms, success=success, error=error,
            )
            return log_id
        except Exception as e:
            logger.warning("AI 调用日志写入失败: %s", e)
            return 0

    @staticmethod
    def cleanup():
        """清理过期的成功日志"""
        try:
            setting = get_app_setting("ai_log_retention_days")
            days_str = setting["value"] if isinstance(setting, dict) and setting.get("value") else "7"
            retention_days = int(days_str)
            cleanup_ai_call_logs(retention_days)
        except Exception as e:
            logger.warning("AI 调用日志清理失败: %s", e)


# 便捷包装：在 async 管线中使用的上下文管理器
class AICallContext:
    """AI 调用上下文管理器，自动计时和记录"""

    def __init__(self, task_id: int | None, pipeline: str, group_id: int,
                 model_name: str, system_prompt: str, user_prompt: str):
        self.task_id = task_id
        self.pipeline = pipeline
        self.group_id = group_id
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.start_time = None
        self.log_id = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # async 管线用 async with 或手动调用

    async def __aenter__(self):
        self.start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def finish(self, response_raw: str, success: bool, error: str = "") -> int:
        """记录调用结果"""
        duration_ms = int((time.time() - self.start_time) * 1000) if self.start_time else 0
        self.log_id = AILogger.log(
            task_id=self.task_id, pipeline=self.pipeline, group_id=self.group_id,
            model_name=self.model_name, system_prompt=self.system_prompt,
            user_prompt=self.user_prompt, response_raw=response_raw,
            duration_ms=duration_ms, success=success, error=error,
        )
        return self.log_id
