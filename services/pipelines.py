"""
子任务管道：把复杂 AI 分析拆成多个极简子任务
每个子任务只问一件事，返回极简格式，管道拼装完整 JSON
"""
import json
import time
import logging
from typing import Optional

from models.database import save_task_record
from services.analyzer import call_ollama_chat
from config import config

logger = logging.getLogger(__name__)

# ---- 极简子任务 Prompt ----

def _safe_format(template: str, **kwargs) -> str:
    """安全格式化：先转义 chat 中的花括号，再 format，防止用户消息中的 {xxx} 被当成占位符"""
    chat = kwargs.pop("chat", "")
    name = kwargs.pop("name", "")
    # 转义聊天内容中的花括号
    safe_chat = chat.replace("{", "{{").replace("}", "}}")
    safe_name = name.replace("{", "{{").replace("}", "}}")
    return template.format(chat=safe_chat, name=safe_name, **kwargs)


PROMPTS = {
    "topics": {
        "system": "你是一个话题提取工具。只输出话题，每行一个。",
        "user": "{chat}\n\n列出今天讨论的 2-4 个话题，每行一个，每句话不超过 25 字：",
    },
    "quotes": {
        "system": "你是一个金句挖掘工具。格式：发言人|原话|吐槽，每行一条。",
        "user": "{chat}\n\n找出 3-5 条最搞笑/精彩的发言，每行一条，格式：发言人|原话|你的吐槽",
    },
    "mood": {
        "system": "你是一个情绪识别工具。只回答一个词。",
        "user": "{chat}\n\n今天群聊氛围是什么？只回答一个词：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕",
    },
    "keywords": {
        "system": "你是一个关键词提取工具。只输出关键词，逗号分隔。",
        "user": "{chat}\n\n提取今天聊天的 3-5 个关键词，逗号分隔：",
    },
    "oneline": {
        "system": "你是一个群聊总结工具。两行回答：第一行总结，第二行高光时刻。",
        "user": "{chat}\n\n第一行：用20字内有梗的话总结今天群聊\n第二行：今天最值得记录的瞬间",
    },
    "active_hours": {
        "system": "你是一个活跃度分析工具。一句话描述活跃规律。",
        "user": "消息按小时分布：\n{hourly_stats}\n\n一句话描述活跃规律（如\"下午2-5点最活跃，上午安静\"）：",
    },
}

PORTRAIT_PROMPTS = {
    "persona": {
        "system": "你是一个人物分析工具。每行一个标签。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出三行：\n第一行：性格标签（逗号分隔，2-3个）\n第二行：说话风格（一个词）\n第三行：群内角色（从气氛组/和事佬/话题制造机/话题终结者/吃瓜群众/潜水大佬/毒舌评论员/科普达人中选）",
    },
    "interests": {
        "system": "你是一个兴趣分析工具。输出两行。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出两行：\n第一行：关注话题/兴趣（逗号分隔，3-5个）\n第二行：活跃时段（如\"夜猫子22:00-02:00\"）",
    },
    "phrase": {
        "system": "你是一个口头禅检测工具。只回答口头禅或\"无\"。",
        "user": "{chat}\n\n以上是 {name} 的发言。ta 有口头禅吗？有就直接写出来，没有就回答：无",
    },
    "oneline_portrait": {
        "system": "你是一个人物素描工具。两行输出：人设+emoji。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出两行：\n第一行：15字一句话人设\n第二行：2个emoji形容ta",
    },
}


# ---- 管道执行 ----

MAX_RETRIES = 3
STEP_TIMEOUT = 90  # 单个子任务（含重试）总超时秒数


def _parse_lines(raw) -> list[str]:
    """解析 AI 返回的文本为行列表（过滤空行和编号前缀）"""
    if not raw: return []
    text = raw if isinstance(raw, str) else str(raw)
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip().lstrip("-*•1234567890.、）) ").strip()
        if line and len(line) > 2:
            lines.append(line)
    return lines


def _parse_quotes(raw) -> list[dict]:
    """解析 发言人|原话|吐槽 格式"""
    if not raw: return []
    text = raw if isinstance(raw, str) else str(raw)
    quotes = []
    for line in text.strip().split("\n"):
        line = line.strip()
        parts = line.split("|")
        if len(parts) >= 2:
            quotes.append({
                "speaker": parts[0].strip(),
                "quote": parts[1].strip(),
                "comment": parts[2].strip() if len(parts) > 2 else "",
            })
    return quotes


def _parse_kw(raw) -> list[str]:
    """解析逗号/顿号分隔的关键词"""
    if not raw: return ["群聊"]
    text = raw if isinstance(raw, str) else str(raw)
    import re
    kws = re.split(r"[,，、\n]+", text.strip())
    return [k.strip().lstrip("#") for k in kws if k.strip() and len(k.strip()) > 1][:5]


MOOD_MAP = {"欢乐":"😄","温馨":"🥰","严肃":"🧐","吐槽":"😤","平淡":"😐","热闹":"🎉","伤感":"😢","沙雕":"🤪"}


def _parse_mood(raw) -> tuple[str, str]:
    """从文本中提取 mood 词并映射 emoji"""
    text = str(raw) if raw else ""
    for m, e in MOOD_MAP.items():
        if m in text:
            return m, e
    return "平淡", "😐"


def _parse_oneline(raw) -> tuple[str, str]:
    """解析两行：第一行总结，第二行高光"""
    lines = _parse_lines(raw)
    one_line = lines[0] if len(lines) > 0 else "今天也是热闹的一天"
    highlight = lines[1] if len(lines) > 1 else ""
    return one_line[:40], highlight


def _parse_active_hours(raw) -> dict:
    """解析活跃规律描述"""
    text = str(raw).strip() if raw else ""
    # 从描述中推断 peak_label，先精确后模糊
    PEAKS = {"上午摸鱼":"上午","午间活跃":"中午","下午茶话会":"下午","晚间热闹":"晚上","夜猫子专场":"深夜","全天在线":"全天"}
    peak_label = ""
    for k, v in PEAKS.items():
        if k in text: peak_label = k; break
    if not peak_label:
        # 模糊匹配
        for kw, label in [("上午","上午摸鱼"),("中午","午间活跃"),("下午","下午茶话会"),("晚上","晚间热闹"),("夜间","夜猫子专场"),("凌晨","夜猫子专场"),("全天","全天在线")]:
            if kw in text: peak_label = label; break
    if not peak_label:
        peak_label = "全天在线"  # 兜底
    return {"peak_label": peak_label, "peak_desc": text, "quiet_note": ""}


async def _run_sub(task, step_name: str, step_idx: int, total: int,
                   system: str, user: str, model: str = "") -> Optional[dict]:
    """执行一个子任务，失败自动重试（最多 3 次），返回解析后的 dict"""
    import asyncio

    last_error = ""
    total_start = time.time()
    result2 = None  # 避免 UnboundLocalError

    for attempt in range(1, MAX_RETRIES + 1):
        # 总超时检查
        if time.time() - total_start > STEP_TIMEOUT:
            last_error = f"子任务总超时 ({STEP_TIMEOUT}s)"
            logger.warning(f"{step_name}: {last_error}")
            break

        label = f"({step_idx}/{total}) {step_name}" if attempt == 1 else f"({step_idx}/{total}) {step_name} 重试{attempt}/{MAX_RETRIES}"
        if task:
            task.update("inference", f"{label}...")
        logger.info(f"{step_name} 第{attempt}次尝试, 模型={model or config.OLLAMA_MODEL}")

        # --- 主模型 ---
        start = time.time()
        try:
            result = await asyncio.wait_for(
                call_ollama_chat(system, user, model, timeout=40),  # 单次调用 40s 超时
                timeout=50  # asyncio 兜底
            )
        except asyncio.TimeoutError:
            last_error = "主模型调用超时"
            logger.warning(f"{step_name}: {last_error}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2)
            continue

        duration = int((time.time() - start) * 1000)
        logger.info(f"{step_name} 主模型: success={result['success']}, duration={duration}ms, model={result.get('model','')}")

        # 1. 主模型成功
        if result["success"] and result["data"] is not None:
            if task:
                task.add_step(name=step_name, status="done", duration_ms=int((time.time() - total_start) * 1000),
                             model=result.get("model", ""), error="")
            return result["data"]

        # 2. 主模型失败，试 fallback（先等 1s 确保主模型从 GPU 卸载）
        if config.OLLAMA_MODEL_FALLBACK and result.get("model") != config.OLLAMA_MODEL_FALLBACK:
            logger.info(f"{step_name}: 主模型失败，1s后尝试 {config.OLLAMA_MODEL_FALLBACK}")
            await asyncio.sleep(1)
            start2 = time.time()
            try:
                result2 = await asyncio.wait_for(
                    call_ollama_chat(system, user, config.OLLAMA_MODEL_FALLBACK, timeout=40),
                    timeout=50
                )
            except asyncio.TimeoutError:
                last_error = "fallback 模型调用超时"
                logger.warning(f"{step_name}: {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2)
                continue

            d2 = int((time.time() - start2) * 1000)
            logger.info(f"{step_name} fallback: success={result2['success']}, duration={d2}ms")
            if result2["success"] and result2["data"] is not None:
                if task:
                    task.add_step(name=step_name, status="done",
                                 duration_ms=int((time.time() - total_start) * 1000),
                                 model=result2.get("model", ""), error="")
                return result2["data"]

        # 3. 都失败了
        last_error = result.get("error", "") or (result2.get("error", "") if result2 else "")
        if attempt < MAX_RETRIES:
            logger.warning(f"{step_name}: 第{attempt}次失败，2s后重试")
            if task:
                task.update("inference", f"({step_idx}/{total}) {step_name} 失败，2s后重试...")
            await asyncio.sleep(2)

    # 所有重试都失败
    logger.error(f"{step_name}: 全部{MAX_RETRIES}次重试失败: {last_error}")
    if task:
        task.add_step(name=step_name, status="failed",
                     duration_ms=int((time.time() - total_start) * 1000),
                     model=config.OLLAMA_MODEL, error=last_error)
    return None


async def run_daily_pipeline(chat_text: str, group_name: str,
                              date: str, msg_count: int, task=None,
                              hourly_stats: str = "") -> dict:
    """执行 6 步子任务管道，拼装每日报告 JSON"""
    total = 6

    if task:
        task.update("inference", f"(0/6) 开始分析...")
        task.steps.clear()


    # 1. 话题（每行一个）
    topics_data = await _run_sub(task, "提取话题", 1, total,
                                  PROMPTS["topics"]["system"],
                                  f"{chat_text}\n\n{PROMPTS['topics']['user']}")
    topics = _parse_lines(topics_data) if topics_data else ["今日话题"]

    # 2. 搞笑发言（发言人|原话|吐槽）
    quotes_data = await _run_sub(task, "找搞笑发言", 2, total,
                                  PROMPTS["quotes"]["system"],
                                  f"{chat_text}\n\n{PROMPTS['quotes']['user']}")
    quotes = _parse_quotes(quotes_data) if quotes_data else []

    # 3. 情绪（一个词）
    mood_data = await _run_sub(task, "判断情绪", 3, total,
                                PROMPTS["mood"]["system"],
                                f"{chat_text}\n\n{PROMPTS['mood']['user']}")
    mood, mood_emoji = _parse_mood(mood_data)

    # 4. 关键词（逗号分隔）
    kw_data = await _run_sub(task, "提取关键词", 4, total,
                              PROMPTS["keywords"]["system"],
                              f"{chat_text}\n\n{PROMPTS['keywords']['user']}")
    keywords = _parse_kw(kw_data)

    # 5. 一句话总结（两行：总结+高光）
    ol_data = await _run_sub(task, "一句话总结", 5, total,
                              PROMPTS["oneline"]["system"],
                              f"{chat_text}\n\n{PROMPTS['oneline']['user']}")
    one_line, highlight = _parse_oneline(ol_data)

    # 6. 活跃时段（一句话描述）
    hs = (hourly_stats or "(无小时分布数据)").replace("{", "{{").replace("}", "}}")
    hs_user = PROMPTS["active_hours"]["user"].replace("{hourly_stats}", hs)
    ah_data = await _run_sub(task, "活跃时段分析", 6, total,
                              PROMPTS["active_hours"]["system"], hs_user)
    ah = _parse_active_hours(ah_data)

    # 拼装
    report = {
        "topic_summary": topics,
        "funny_quotes": quotes,
        "mood": mood,
        "mood_emoji": mood_emoji,
        "highlight": highlight,
        "keywords": keywords,
        "one_line": one_line,
        "active_hours": ah,
    }

    if task:
        task.model_used = config.OLLAMA_MODEL
        # 批量任务不在这里 finish，由外层循环控制
        if task.type != "analyze_all":
            task.finish(success=True)
        # 持久化任务记录
        _save_pipeline_record(task, group_name, date)

    return report


async def run_portrait_pipeline(chat_text: str, sender_name: str,
                                 group_name: str, msg_count: int,
                                 task=None) -> dict:
    """执行 4 步子任务管道，拼装画像 JSON"""
    total = 4

    if task:
        task.update("inference", f"(0/4) 分析 {sender_name}...")
        task.steps.clear()

    prompt_user = f"{chat_text}\n\n以上是 {sender_name} 的发言。"
    role_opts = "气氛组/和事佬/话题制造机/话题终结者/吃瓜群众/潜水大佬/毒舌评论员/科普达人"

    # 1. 性格+角色（三行文本）
    p_data = await _run_sub(task, "分析性格角色", 1, total,
                             PORTRAIT_PROMPTS["persona"]["system"],
                             f"{prompt_user}{PORTRAIT_PROMPTS['persona']['user'].replace('{name}', sender_name)}")
    p_lines = _parse_lines(p_data)
    personality = [t.strip() for t in p_lines[0].replace("，",",").split(",")] if len(p_lines) > 0 else []
    speaking_style = p_lines[1] if len(p_lines) > 1 else ""
    role = p_lines[2] if len(p_lines) > 2 else ""
    # 从 role 选项中匹配
    for r in role_opts.split("/"):
        if r in str(p_data or ""):
            role = r
            break

    # 2. 兴趣+活跃时段（两行文本）
    i_data = await _run_sub(task, "分析兴趣爱好", 2, total,
                             PORTRAIT_PROMPTS["interests"]["system"],
                             f"{prompt_user}{PORTRAIT_PROMPTS['interests']['user'].replace('{name}', sender_name)}")
    i_lines = _parse_lines(i_data)
    interests = [t.strip() for t in i_lines[0].replace("，",",").split(",")] if len(i_lines) > 0 else []
    active_hours = i_lines[1] if len(i_lines) > 1 else ""

    # 3. 口头禅（一个词或"无"）
    ph_data = await _run_sub(task, "检测口头禅", 3, total,
                              PORTRAIT_PROMPTS["phrase"]["system"],
                              f"{prompt_user}{PORTRAIT_PROMPTS['phrase']['user'].replace('{name}', sender_name)}")
    ph_text = str(ph_data or "").strip()
    signature_phrase = None if "无" in ph_text or not ph_text else ph_text[:50]

    # 4. 一句话+emoji（两行文本）
    ol_data = await _run_sub(task, "一句话素描", 4, total,
                              PORTRAIT_PROMPTS["oneline_portrait"]["system"],
                              f"{prompt_user}{PORTRAIT_PROMPTS['oneline_portrait']['user'].replace('{name}', sender_name)}")
    ol_lines = _parse_lines(ol_data)
    one_line = ol_lines[0] if len(ol_lines) > 0 else ""
    emoji_style = ol_lines[1] if len(ol_lines) > 1 else "👤"

    # 拼装
    portrait = {
        "personality": personality[:3],
        "speaking_style": speaking_style,
        "role": role,
        "interests": interests[:5],
        "active_hours": active_hours,
        "signature_phrase": signature_phrase,
        "one_line": one_line[:30],
        "emoji_style": emoji_style[:10],
    }

    if task:
        task.model_used = config.OLLAMA_MODEL
        if task.type != "analyze_all":
            task.finish(success=True)
        _save_pipeline_record(task, group_name, sender_name)

    return portrait


# ---- 辅助函数 ----

def _as_list(data) -> list:
    """确保返回 list"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 可能是 {"topic": "..."} 格式
        for v in data.values():
            if isinstance(v, list):
                return v
        return list(data.values())
    if isinstance(data, str):
        return [data]
    return []


def _save_pipeline_record(task, group_name: str, target: str):
    """持久化任务记录到数据库"""
    try:
        failed_steps = [s for s in task.steps if s["status"] == "failed"]
        model = task.model_used or config.OLLAMA_MODEL
        save_task_record(
            task_id=task.task_id,
            group_id=task.group_id,
            task_type=task.type,
            target=f"{group_name}/{target}",
            status="failed" if failed_steps else task.status,
            total_duration_ms=task.duration_ms,
            model_used=model,
            steps_json=json.dumps(task.steps, ensure_ascii=False),
            error_summary="; ".join(f"{s['name']}:{s['error']}" for s in failed_steps) if failed_steps else "",
        )
    except Exception as e:
        logger.warning(f"保存任务记录失败: {e}")
