"""
在线模型调用服务：DeepSeek API 抽象层
用于周报/月报的深度推理，本地 14B 负责脱敏消化

Usage:
    result = await call_deepseek_chat("system prompt", "user prompt")
    if result["success"]:
        text = result["data"]
"""
import time
import logging
import httpx
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# 模块级 httpx 客户端复用
_deepseek_client: httpx.AsyncClient | None = None


def _get_deepseek_client(timeout: int = 90) -> httpx.AsyncClient:
    global _deepseek_client
    if _deepseek_client is None or _deepseek_client.is_closed:
        _deepseek_client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    return _deepseek_client


async def call_deepseek_chat(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
    timeout: int = 0,
    json_mode: bool = False,
) -> dict:
    """调用 DeepSeek Chat API

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model: 模型名（默认 deepseek-chat，月报可用 deepseek-reasoner）
        temperature: 温度参数（0-1，越低越确定）
        timeout: 超时秒数（默认使用配置值）
        json_mode: 是否要求 JSON 格式输出（仅 deepseek-chat 支持）

    Returns:
        {"success": bool, "data": str, "error": str, "model": str, "duration_ms": int}
    """
    model = model or config.DEEPSEEK_MODEL
    timeout = timeout or config.DEEPSEEK_TIMEOUT

    if not config.DEEPSEEK_API_KEY:
        return {
            "success": False,
            "data": None,
            "error": "DeepSeek API Key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY",
            "model": model,
            "duration_ms": 0,
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": 2048,
    }

    # deepseek-reasoner 不支持 temperature 和 json_mode
    if "reasoner" in model:
        payload.pop("temperature", None)
        payload.pop("top_p", None)
        json_mode = False

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    start_time = time.time()
    try:
        client = _get_deepseek_client(timeout)
        resp = await client.post(config.DEEPSEEK_API_URL, json=payload)
        duration_ms = int((time.time() - start_time) * 1000)

        if resp.status_code == 401:
            return {
                "success": False,
                "data": None,
                "error": "DeepSeek API Key 无效，请检查 .env 中的 DEEPSEEK_API_KEY",
                "model": model,
                "duration_ms": duration_ms,
            }
        if resp.status_code == 402:
            return {
                "success": False,
                "data": None,
                "error": "DeepSeek API 余额不足",
                "model": model,
                "duration_ms": duration_ms,
            }
        if resp.status_code == 429:
            return {
                "success": False,
                "data": None,
                "error": "DeepSeek API 请求太频繁，请稍后重试",
                "model": model,
                "duration_ms": duration_ms,
            }

        resp.raise_for_status()
        result = resp.json()

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        logger.info(f"DeepSeek 响应 ({model}): {duration_ms}ms, {len(content)} 字符")

        if content.strip():
            return {
                "success": True,
                "data": content.strip(),
                "error": None,
                "model": model,
                "duration_ms": duration_ms,
            }
        return {
            "success": False,
            "data": None,
            "error": "DeepSeek 返回空内容",
            "model": model,
            "duration_ms": duration_ms,
        }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "data": None,
            "error": f"DeepSeek API 请求超时 ({timeout}s)",
            "model": model,
            "duration_ms": duration_ms,
        }
    except httpx.ConnectError:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "data": None,
            "error": f"无法连接到 DeepSeek API ({config.DEEPSEEK_API_URL})",
            "model": model,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"DeepSeek 调用异常: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e),
            "model": model,
            "duration_ms": duration_ms,
        }


async def check_deepseek_health() -> dict:
    """检查 DeepSeek API 连通性和余额（轻量调用）"""
    if not config.DEEPSEEK_API_KEY:
        return {
            "configured": False,
            "online": False,
            "error": "未配置 DEEPSEEK_API_KEY",
        }
    try:
        result = await call_deepseek_chat(
            system_prompt="回复一个单词 OK",
            user_prompt="OK",
            temperature=0.0,
            timeout=15,
        )
        return {
            "configured": True,
            "online": result["success"],
            "model": result.get("model", config.DEEPSEEK_MODEL),
            "duration_ms": result.get("duration_ms", 0),
            "error": result.get("error") if not result["success"] else None,
        }
    except Exception as e:
        return {
            "configured": True,
            "online": False,
            "error": str(e),
        }
