"""
AI 分析服务：调用 Ollama API 生成每日报告
使用 httpx 异步请求，支持重试和 JSON 提取
通过 GPU 分布式锁防止多应用抢占显存
每次调用独立会话（keep_alive=0），防止上下文累积
"""
import json
import re
import time
import logging
import uuid
import httpx
from typing import Optional

from config import config
from prompts.daily_report import DAILY_REPORT_SYSTEM, DAILY_REPORT_USER
from services.gpu_lock import gpu_lock

logger = logging.getLogger(__name__)

OLLAMA_CHAT_URL = f"{config.OLLAMA_HOST}/api/chat"


def _extract_json(text: str) -> Optional[dict]:
    """从 AI 返回的文本中提取 JSON 对象

    处理各种情况：
    1. 纯 JSON 文本
    2. Markdown 代码块包裹
    3. JSON 前后有杂文
    """
    if not text:
        return None

    text = text.strip()

    # 尝试 1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试 2：提取 Markdown 代码块 ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试 3：找到第一个 { 和最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


async def call_ollama_chat(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    timeout: int = 0,
    task=None,  # TaskInfo for progress reporting
) -> dict:
    """调用 Ollama chat API，返回解析后的 JSON

    自动通过 GPU 分布式锁协调多应用对 GPU 的访问。
    如果 GPU 被占用（如 ComfyUI），会等待并重试。
    每次调用创建独立会话（keep_alive=0），防止上下文累积。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model: 模型名（默认使用配置的模型）
        timeout: 超时秒数（默认使用配置值）
        task: 可选的 TaskInfo，用于报告进度

    Returns:
        {"success": bool, "data": dict|None, "error": str, "model": str, "duration_ms": int}
    """
    model = model or config.OLLAMA_MODEL
    timeout = timeout or config.OLLAMA_TIMEOUT

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "keep_alive": 0,  # 推理完成后立即卸载模型，释放显存，防止上下文累积
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
        },
    }

    start_time = time.time()
    try:
        # 进度：等待 GPU
        if task:
            task.update("waiting_gpu", "等待 GPU 释放...")

        # 获取 GPU 锁后再调用 Ollama
        async with gpu_lock(config.GPU_LOCK_WHO):
            if task:
                task.update("inference", "AI 推理中...")

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(OLLAMA_CHAT_URL, json=payload)
                resp.raise_for_status()
                result = resp.json()

        # 进度：解析
        if task:
            task.update("parsing", "解析 AI 结果...")

        duration_ms = int((time.time() - start_time) * 1000)
        raw_content = result.get("message", {}).get("content", "")
        logger.info(f"Ollama 响应 ({model}): {duration_ms}ms, {len(raw_content)} 字符")

        # 解析 JSON
        data = _extract_json(raw_content)
        if data:
            if task:
                task.model_used = model
                task.finish(success=True)
            return {
                "success": True,
                "data": data,
                "error": None,
                "model": model,
                "duration_ms": duration_ms,
            }
        else:
            logger.warning(f"JSON 解析失败，原始返回: {raw_content[:300]}...")
            if task:
                task.finish(success=False, error={"type": "json_parse", "detail": f"AI 返回无法解析为 JSON"})
            return {
                "success": False,
                "data": None,
                "error": f"无法从 AI 返回中提取 JSON。原始返回前300字: {raw_content[:300]}",
                "model": model,
                "duration_ms": duration_ms,
            }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        err = {"type": "timeout", "detail": f"Ollama 请求超时 ({timeout}s)"}
        if task:
            task.finish(success=False, error=err)
        return {"success": False, "data": None,
                "error": f"Ollama 请求超时 ({timeout}s)", "model": model,
                "duration_ms": duration_ms}
    except httpx.ConnectError:
        duration_ms = int((time.time() - start_time) * 1000)
        err = {"type": "ollama_down", "detail": f"无法连接到 Ollama ({config.OLLAMA_HOST})"}
        if task:
            task.finish(success=False, error=err)
        return {"success": False, "data": None,
                "error": f"无法连接到 Ollama ({config.OLLAMA_HOST})，请确认 Ollama 已启动",
                "model": model, "duration_ms": duration_ms}
    except RuntimeError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        err = {"type": "gpu_busy", "detail": str(e)}
        if task:
            task.finish(success=False, error=err)
        return {"success": False, "data": None,
                "error": f"GPU 被占用，无法获取锁: {e}", "model": model,
                "duration_ms": duration_ms}
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Ollama 调用异常: {e}")
        if task:
            task.finish(success=False, error={"type": "unknown", "detail": str(e)})
        return {"success": False, "data": None,
                "error": str(e), "model": model, "duration_ms": duration_ms}


async def analyze_daily_chat(
    group_name: str,
    date: str,
    chat_text: str,
    msg_count: int,
    model: str = "",
) -> dict:
    """分析一天的群聊内容，生成每日报告

    Args:
        group_name: 群名
        date: 日期字符串 "2025-09-01"
        chat_text: 格式化后的聊天记录文本
        msg_count: 文本消息数量
        model: 使用的模型

    Returns:
        同 call_ollama_chat 的返回格式
    """
    user_prompt = DAILY_REPORT_USER.format(
        group_name=group_name,
        date=date,
        msg_count=msg_count,
        chat_text=chat_text,
    )

    logger.info(f"开始分析 {group_name} {date}: {msg_count} 条消息, {len(chat_text)} 字符")
    result = await call_ollama_chat(DAILY_REPORT_SYSTEM, user_prompt, model)

    # 如果主模型失败，尝试 fallback
    if not result["success"] and config.OLLAMA_MODEL_FALLBACK:
        fallback = config.OLLAMA_MODEL_FALLBACK
        if result["model"] != fallback:
            logger.info(f"主模型失败，尝试 fallback: {fallback}")
            result = await call_ollama_chat(DAILY_REPORT_SYSTEM, user_prompt, fallback)

    return result


async def check_ollama_health() -> dict:
    """检查 Ollama 服务连通性和可用模型"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 检查 tags
            resp = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                tags_data = resp.json()
                models = [m.get("name", "") for m in tags_data.get("models", [])]
                return {
                    "ollama_online": True,
                    "available_models": models,
                    "configured_model": config.OLLAMA_MODEL,
                    "fallback_model": config.OLLAMA_MODEL_FALLBACK,
                    "model_available": config.OLLAMA_MODEL in [m.split(":")[0]
                                       if ":" in m else m for m in models]
                                       or config.OLLAMA_MODEL in models,
                }
            else:
                return {"ollama_online": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ollama_online": False, "error": str(e)}
