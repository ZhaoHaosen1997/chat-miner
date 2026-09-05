"""
在线模型调用服务：通用 OpenAI 兼容 API 抽象层 v0.12.0
支持 DeepSeek、OpenAI 及任意兼容端点，按 model_config 动态切换。

Usage:
    result = await call_online_chat("system prompt", "user prompt", model_config)
    if result["success"]:
        text = result["data"]
"""
import asyncio
import hashlib
import json
import logging
import re
import time
import httpx

from config import config


def _parse_json_safe(content: str) -> tuple:
    """尝试将 AI 响应解析为 JSON。返回 (is_valid, error_message)。"""
    text = content.strip()
    # 1. 直接解析
    try:
        json.loads(text)
        return True, ""
    except json.JSONDecodeError:
        pass
    # 2. 尝试从 markdown 代码块提取 ```json ... ```
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            json.loads(m.group(1).strip())
            return True, ""
        except json.JSONDecodeError:
            pass
    return False, f"JSON 解析失败，内容前100字符: {text[:100]}"

logger = logging.getLogger(__name__)

# v0.13.0: 模块级 httpx 连接池，按 (endpoint, api_key) 缓存复用
_online_clients: dict[str, httpx.AsyncClient] = {}


def _key_fingerprint(api_key: str) -> str:
    """v1.19.7: 完整 key 的哈希前缀——旧实现取 key 前 8 字符，
    同端点下两个 key 前缀相同（如都是 sk- 开头风格）会复用错 client 导致神秘 401"""
    if not api_key:
        return "nokey"
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def _get_online_client(endpoint: str, api_key: str, timeout: int = 90) -> httpx.AsyncClient:
    """获取或创建缓存的 httpx 客户端（按端点+Key 缓存）"""
    cache_key = f"{endpoint}|{_key_fingerprint(api_key)}"
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
    # v1.19.0: 日志记录参数
    task_id: str = "",
    pipeline: str = "",
    group_id: int = 0,
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
    ret = None  # v1.19.0: 统一返回点，便于记录日志

    # v1.19.7: 429/5xx/网络错误在本层指数退避重试——此前"请稍后重试"只是文案，
    # 代码从不重试，批量分析时一次瞬时抖动即导致该日期整体失败
    max_attempts = max(1, int(getattr(config, "ONLINE_RETRY_COUNT", 2)) + 1)
    retryable_status = {429, 500, 502, 503, 504}

    def _error_ret(error_msg: str, status: str = "error") -> dict:
        return {"success": False, "data": None, "status": status, "error": error_msg,
                "model": model_name, "duration_ms": int((time.time() - start_time) * 1000)}

    try:
        for attempt in range(max_attempts):
            client = _get_online_client(endpoint, api_key, timeout)
            resp = await client.post(api_url, json=payload)

            if resp.status_code == 401:
                ret = _error_ret(f"API Key 无效 ({model_name})")
                break
            if resp.status_code == 402:
                ret = _error_ret(f"API 余额不足 ({model_name})")
                break

            if resp.status_code in retryable_status and attempt < max_attempts - 1:
                # Retry-After 优先（上限 30s），否则指数退避 1s/2s/4s...
                try:
                    delay = min(30.0, float(resp.headers.get("Retry-After") or 0))
                except (TypeError, ValueError):
                    delay = 0.0
                if delay <= 0:
                    delay = float(2 ** attempt)
                logger.warning(f"在线模型可重试错误 {resp.status_code} "
                               f"(尝试 {attempt + 1}/{max_attempts}): {delay}s 后重试")
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            resp_json = resp.json()
            # v1.19.7: 空 choices 数组防 IndexError
            choices = resp_json.get("choices") or [{}]
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            if not content or not content.strip():
                rc = msg.get("reasoning_content", "")
                if rc and rc.strip():
                    content = rc
            if not content or not content.strip():
                content = choices[0].get("text", "")
            if not content or not content.strip():
                # v1.19.7: 原始响应可能回显聊天内容，debug 级 + 截断防敏感信息进日志
                logger.debug(f"在线模型返回空/空白内容, 原始响应: {json.dumps(resp_json, ensure_ascii=False)[:200]}")

            logger.debug(f"在线模型响应 ({model_name}): {int((time.time() - start_time) * 1000)}ms, {len(content)} 字符")

            if not content.strip():
                ret = _error_ret(f"{model_name} 返回空内容")
                break

            status = "success"
            error_msg = None
            if json_mode:
                ok, err = _parse_json_safe(content)
                if not ok:
                    status = "parse_error"
                    error_msg = err
                    logger.warning(f"在线模型 JSON 解析失败 ({model_name}): {err}")
            ret = {"success": status == "success", "data": content.strip(),
                   "status": status, "error": error_msg,
                   "model": model_name, "duration_ms": int((time.time() - start_time) * 1000)}
            break

    except httpx.ConnectError:
        logger.error("在线模型连接失败: %s", endpoint, exc_info=True)
        ret = _error_ret(f"无法连接到 API 端点 ({endpoint})")
    except httpx.TimeoutException:
        # 超时不重试：长 prompt 重试大概率再次超时且成倍计费
        ret = _error_ret(f"在线模型请求超时 ({timeout}s)")
    except Exception as e:
        logger.error("在线模型调用异常: %s", e, exc_info=True)
        ret = _error_ret(str(e))

    # v1.19.0: 记录 AI 调用日志
    if ret and (pipeline or task_id):
        try:
            from services.ai_logger import AILogger
            # v1.19.6: 日志含三段大文本的同步 SQLite 写，移入工作线程防阻塞事件循环
            await asyncio.to_thread(
                AILogger.log,
                task_id=task_id or None, pipeline=pipeline, group_id=group_id,
                model_name=model_name, system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_raw=(ret.get("data") or ret.get("error") or ""),
                duration_ms=ret.get("duration_ms", 0),
                success=ret.get("success", False),
                error=ret.get("error") or "",
                status=ret.get("status", ""),
            )
        except Exception as e:
            logger.warning("AI 调用日志记录失败: %s", e)

    return ret



async def check_deepseek_health() -> dict:
    """检查 DeepSeek API 连通性和余额（轻量调用）"""
    if not config.DEEPSEEK_API_KEY:
        return {
            "configured": False,
            "online": False,
            "error": "未配置 DEEPSEEK_API_KEY",
        }
    try:
        model_config = {
            "name": "DeepSeek (.env)",
            "endpoint": config.DEEPSEEK_API_URL,
            "api_key": config.DEEPSEEK_API_KEY,
            "model_name": config.DEEPSEEK_MODEL,
        }
        result = await call_online_chat(
            system_prompt="回复一个单词 OK",
            user_prompt="OK",
            model_config=model_config,
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
            timeout=15,  # v1.19.7: 健康检查用短超时，此前走 120s 默认值最坏挂 2 分钟
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
