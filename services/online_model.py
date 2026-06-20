"""
在线模型调用服务：通用 OpenAI 兼容 API 抽象层 v0.12.0
支持 DeepSeek、OpenAI 及任意兼容端点，按 model_config 动态切换。

Usage:
    result = await call_online_chat("system prompt", "user prompt", model_config)
    if result["success"]:
        text = result["data"]
"""
import json
import logging
import time
import httpx

from config import config

logger = logging.getLogger(__name__)

# v0.13.0: 模块级 httpx 连接池，按 (endpoint, api_key) 缓存复用
_online_clients: dict[str, httpx.AsyncClient] = {}


def _get_online_client(endpoint: str, api_key: str, timeout: int = 90) -> httpx.AsyncClient:
    """获取或创建缓存的 httpx 客户端（按端点+Key 缓存）"""
    cache_key = f"{endpoint}|{api_key[:8] if api_key else 'nokey'}"
    client = _online_clients.get(cache_key)
    if client is None or client.is_closed:
        _online_clients[cache_key] = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            } if api_key else {"Content-Type": "application/json"},
        )
    else:
        # v0.13.4: 每次调用更新超时
        client.timeout = httpx.Timeout(timeout)
    return _online_clients[cache_key]


# 保留旧兼容函数（内部转调连接池）
def _get_deepseek_client(timeout: int = 90) -> httpx.AsyncClient:
    return _get_online_client(config.DEEPSEEK_API_URL, config.DEEPSEEK_API_KEY, timeout)


def _build_api_url(endpoint: str) -> str:
    """确保 endpoint 是完整的 chat/completions URL"""
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    if endpoint.endswith("/v1"):
        return endpoint + "/chat/completions"
    return endpoint + "/v1/chat/completions"


async def call_online_chat(
    system_prompt: str,
    user_prompt: str,
    model_config: dict,
    temperature: float = 0.8,
    json_mode: bool = False,
    thinking: bool = False,
    max_tokens: int = 0,
    timeout: int = 0,
) -> dict:
    """通用在线模型调用（OpenAI 兼容 API）

    根据 model_config dict 动态切换端点、API Key 和模型名。
    支持 DeepSeek、OpenAI 及自建代理等任意兼容端点。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model_config: 模型配置 dict（来自 model_config.py 解析层）
            - endpoint: API 基础 URL
            - api_key: API Key
            - model_name: 模型名
            - extra_params: dict，可选 {temperature, max_tokens, ...}
        temperature: 温度参数（若 extra_params 有则被覆盖）
        json_mode: 是否要求 JSON 格式输出
        thinking: DeepSeek 深度推理模式
        max_tokens: 最大输出 token 数

    Returns:
        {"success": bool, "data": str, "error": str, "model": str, "duration_ms": int}
    """
    api_key = model_config.get("api_key", "")
    endpoint = model_config.get("endpoint", "")
    model_name = model_config.get("model_name", "")
    extra = model_config.get("extra_params", {})

    if not api_key:
        logger.warning("在线模型 '%s' 未配置 API Key", model_config.get('name', 'unknown'))
        return {
            "success": False,
            "data": None,
            "error": f"在线模型 '{model_config.get('name', 'unknown')}' 未配置 API Key",
            "model": model_name,
            "duration_ms": 0,
        }

    # extra_params 中可以覆盖 temperature / max_tokens
    if isinstance(extra, dict):
        temperature = extra.get("temperature", temperature)
        max_tokens = max_tokens or extra.get("max_tokens", 4096)
    else:
        max_tokens = max_tokens or 4096

    timeout = timeout or config.DEEPSEEK_TIMEOUT  # 优先调用方指定，否则统一超时配置
    api_url = _build_api_url(endpoint)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "max_tokens": max_tokens,
    }

    if thinking and model_name.lower().startswith("deepseek"):
        payload["thinking"] = {"type": "enabled"}

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    start_time = time.time()
    try:
        client = _get_online_client(endpoint, api_key, timeout)
        resp = await client.post(api_url, json=payload)
        duration_ms = int((time.time() - start_time) * 1000)

        if resp.status_code == 401:
            return {
                "success": False, "data": None,
                "error": f"API Key 无效 ({model_name})",
                "model": model_name, "duration_ms": duration_ms,
            }
        if resp.status_code == 402:
            return {
                "success": False, "data": None,
                "error": f"API 余额不足 ({model_name})",
                "model": model_name, "duration_ms": duration_ms,
            }
        if resp.status_code == 429:
            return {
                "success": False, "data": None,
                "error": f"API 请求太频繁，请稍后重试 ({model_name})",
                "model": model_name, "duration_ms": duration_ms,
            }

        resp.raise_for_status()
        result = resp.json()
        msg = result.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "")
        if not content:
            # SenseNova deepseek-v4-flash 可能把回复放 reasoning_content
            content = msg.get("reasoning_content", "")
        if not content:
            content = result.get("choices", [{}])[0].get("text", "")
        if not content:
            logger.warning(f"在线模型返回空内容，原始响应: {json.dumps(result, ensure_ascii=False)[:500]}")
        logger.debug(f"在线模型响应 ({model_name}): {duration_ms}ms, {len(content)} 字符")

        if content.strip():
            return {
                "success": True, "data": content.strip(),
                "error": None, "model": model_name, "duration_ms": duration_ms,
            }
        return {
            "success": False, "data": None,
            "error": f"{model_name} 返回空内容",
            "model": model_name, "duration_ms": duration_ms,
        }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False, "data": None,
            "error": f"在线模型请求超时 ({timeout}s)",
            "model": model_name, "duration_ms": duration_ms,
        }
    except httpx.ConnectError:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False, "data": None,
            "error": f"无法连接到 API 端点 ({endpoint})",
            "model": model_name, "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("在线模型调用异常: %s", e, exc_info=True)
        return {
            "success": False, "data": None,
            "error": str(e), "model": model_name, "duration_ms": duration_ms,
        }


async def call_deepseek_chat(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.8,
    timeout: int = 0,
    json_mode: bool = False,
    thinking: bool = False,
    max_tokens: int = 0,
) -> dict:
    """调用 DeepSeek API（向后兼容包装）

    v0.12.0: 内部转为 call_online_chat，使用 .env 中的 DeepSeek 配置。
    请优先使用 call_online_chat(model_config=...) 以支持动态模型配置。
    """
    model = model or config.DEEPSEEK_MODEL
    max_tokens = max_tokens or 4096

    if not config.DEEPSEEK_API_KEY:
        return {
            "success": False,
            "data": None,
            "error": "DeepSeek API Key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY",
            "model": model,
            "duration_ms": 0,
        }

    model_config = {
        "name": "DeepSeek (.env)",
        "endpoint": config.DEEPSEEK_API_URL,
        "api_key": config.DEEPSEEK_API_KEY,
        "model_name": model,
        "extra_params": {"temperature": temperature, "max_tokens": max_tokens},
    }
    return await call_online_chat(
        system_prompt, user_prompt, model_config,
        temperature=temperature, json_mode=json_mode,
        thinking=thinking, max_tokens=max_tokens,
        timeout=timeout,
    )


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


async def check_online_model_health(model_config: dict) -> dict:
    """检查指定在线模型配置的连通性（用于设置页健康检查）

    Args:
        model_config: 模型配置 dict（来自 model_config.py）

    Returns:
        {"configured": bool, "online": bool, "model": str, "duration_ms": int, "error": str|None}
    """
    if not model_config.get("api_key"):
        return {
            "configured": False,
            "online": False,
            "model": model_config.get("model_name", ""),
            "duration_ms": 0,
            "error": "未配置 API Key",
        }
    try:
        result = await call_online_chat(
            system_prompt="回复一个单词 OK",
            user_prompt="OK",
            model_config=model_config,
            temperature=0.0,
            max_tokens=10,
        )
        return {
            "configured": True,
            "online": result["success"],
            "model": result.get("model", model_config.get("model_name", "")),
            "duration_ms": result.get("duration_ms", 0),
            "error": result.get("error") if not result["success"] else None,
        }
    except Exception as e:
        return {
            "configured": True,
            "online": False,
            "model": model_config.get("model_name", ""),
            "duration_ms": 0,
            "error": str(e),
        }
