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
from services.gpu_lock import gpu_lock

logger = logging.getLogger(__name__)

OLLAMA_CHAT_URL = f"{config.OLLAMA_HOST}/api/chat"

# 模块级 httpx 客户端复用（批量分析时避免频繁创建/销毁连接）
_ollama_client: httpx.AsyncClient | None = None

def _get_ollama_client(timeout: int = 120) -> httpx.AsyncClient:
    global _ollama_client
    if _ollama_client is None or _ollama_client.is_closed:
        _ollama_client = httpx.AsyncClient(timeout=timeout)
    return _ollama_client


def _normalize_report(data: dict) -> dict:
    """规范化 AI 返回的 JSON，修正常见格式问题"""
    if not isinstance(data, dict):
        return data

    # topic_summary: 对象数组 → 字符串数组
    topics = data.get("topic_summary", [])
    if topics and isinstance(topics[0], dict):
        data["topic_summary"] = [
            t.get("description") or t.get("topic") or t.get("summary") or str(t)
            for t in topics
        ]

    # keywords: 可能是逗号分隔字符串
    keywords = data.get("keywords", [])
    if isinstance(keywords, str):
        data["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]

    # funny_quotes: 确保每个元素有 speaker/quote/comment
    quotes = data.get("funny_quotes", [])
    if quotes and isinstance(quotes, list):
        normalized = []
        for q in quotes:
            if isinstance(q, str):
                normalized.append({"speaker": "某人", "quote": q, "comment": ""})
            elif isinstance(q, dict):
                normalized.append({
                    "speaker": q.get("speaker", "") or q.get("name", ""),
                    "quote": q.get("quote", "") or q.get("content", ""),
                    "comment": q.get("comment", "") or "",
                })
        data["funny_quotes"] = normalized

    return data


def _repair_json_text(text: str) -> str:
    """修复 LLM 生成 JSON 时的常见格式错误"""
    import re

    # 1. 尾随逗号：对象 {a:1,} 或数组 [1,2,]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # 2. 连续逗号：{a:1,,b:2} → {a:1,b:2}
    text = re.sub(r',\s*,', ',', text)

    # 3. 字符串值内部的未转义双引号（常见于 quote 内容）
    #    模式："quote": "他说"你好"世界" → 把内层引号替换为中文引号
    #    这是一个启发式修复，在 key: 后面的字符串值中进行
    def _fix_inner_quotes(m):
        key = m.group(1)
        value = m.group(2)
        # 把内部的英文双引号替换为中文引号（交替左右引号）
        result = []
        in_quote = False
        for ch in value:
            if ch == '"':
                if not in_quote:
                    result.append('“')  # "
                    in_quote = True
                else:
                    result.append('”')  # "
                    in_quote = False
            else:
                result.append(ch)
        return f'"{key}": "{"".join(result)}"'

    text = re.sub(r'"(\w+)":\s*"([^"]*?)"', _fix_inner_quotes, text)

    # 4. 单引号 JSON → 双引号（仅处理 key 和明显的 value）
    #    保守策略：只替换 key 层面的单引号
    #    （value 中可能包含合法单引号如 "I'm"，不处理）

    return text


def _extract_json(text: str) -> Optional[dict]:
    """从 AI 返回的文本中提取 JSON 对象

    处理各种情况：
    1. 纯 JSON 文本
    2. Markdown 代码块包裹
    3. JSON 前后有杂文
    4. LLM 常见格式错误（尾随逗号、未转义引号等）
    """
    if not text:
        return None

    text = text.strip()

    # 预处理：全角符号 → 半角
    text = text.replace("｛", "{").replace("｝", "}")
    text = text.replace("［", "[").replace("］", "]")
    text = text.replace("：", ":").replace("，", ",")

    # 补缺失的开头 {
    if text and text[0] not in "{[":
        text = "{" + text
    # 补缺失的结尾 }
    if text and text[-1] not in "}]":
        text = text + "}"

    # 尝试 1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试 2：修复后解析
    try:
        repaired = _repair_json_text(text)
        return json.loads(repaired)
    except (json.JSONDecodeError, Exception):
        pass

    # 尝试 3：提取 Markdown 代码块 ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        block = m.group(1).strip()
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_text(block))
            except (json.JSONDecodeError, Exception):
                pass

    # 尝试 4：找到第一个 {，然后从后往前找 }，逐步缩短直到解析成功
    start = text.find("{")
    if start != -1:
        end = text.rfind("}")
        while end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                try:
                    return json.loads(_repair_json_text(text[start:end + 1]))
                except (json.JSONDecodeError, Exception):
                    pass
                end = text.rfind("}", start, end)  # 往前找上一个 }

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
        "keep_alive": 300,  # 模型常驻 5 分钟，pipeline 期间避免反复加载卸载
        "options": {
            "temperature": 0.1,  # 极低温度让输出更稳定，适合小模型格式化输出
            "top_p": 0.9,
            "num_predict": 1024,  # 限制输出 token 数，防止 thinking 模型思考过长撑爆上下文
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

            client = _get_ollama_client(timeout)
            resp = await client.post(OLLAMA_CHAT_URL, json=payload)
            resp.raise_for_status()
            result = resp.json()

        # 进度：解析
        if task:
            task.update("parsing", "解析 AI 结果...")

        duration_ms = int((time.time() - start_time) * 1000)
        raw_content = result.get("message", {}).get("content", "")
        logger.info(f"Ollama 响应 ({model}): {duration_ms}ms, {len(raw_content)} 字符")

        # 尝试 JSON 解析，解析不到就用纯文本（pipeline 已改为纯文本提示词）
        data = _extract_json(raw_content)
        if data:
            data = _normalize_report(data)
            if task:
                task.model_used = model
                task.finish(success=True)
            return {"success": True, "data": data, "error": None, "model": model, "duration_ms": duration_ms}
        elif raw_content.strip():
            # 非 JSON 但有内容 → pipeline 会自己解析纯文本
            logger.info(f"纯文本响应 ({len(raw_content)}字符): {raw_content[:80]}...")
            if task:
                task.model_used = model
                task.finish(success=True)
            return {"success": True, "data": raw_content.strip(), "error": None, "model": model, "duration_ms": duration_ms}
        else:
            logger.warning(f"空响应 from {model}")
            return {"success": False, "data": None, "error": "AI 返回空内容", "model": model, "duration_ms": duration_ms}

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
    task=None,
    hourly_stats: str = "",
) -> dict:
    """分析一天的群聊内容，生成每日报告

    通过 5 步子任务管道执行：话题 → 搞笑发言 → 情绪 → 关键词 → 总结
    每个子任务独立调用 Ollama，降低单次复杂度，提高 9B 模型成功率。

    Returns:
        {"success": bool, "data": dict, "error": str, "model": str, "duration_ms": int}
    """
    import time as _time
    from services.pipelines import run_daily_pipeline

    logger.info(f"开始分析 {group_name} {date}: {msg_count} 条消息, {len(chat_text)} 字符 (pipeline模式)")

    start = _time.time()
    try:
        data = await run_daily_pipeline(chat_text, group_name, date, msg_count, task, hourly_stats)
        duration = int((_time.time() - start) * 1000)
        return {
            "success": True,
            "data": data,
            "error": None,
            "model": config.OLLAMA_MODEL,
            "duration_ms": duration,
        }
    except Exception as e:
        duration = int((_time.time() - start) * 1000)
        logger.error(f"Pipeline 失败: {e}")
        if task:
            task.finish(success=False, error={"type": "pipeline_failed", "detail": str(e)})
        return {
            "success": False,
            "data": None,
            "error": str(e),
            "model": config.OLLAMA_MODEL,
            "duration_ms": duration,
        }


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
