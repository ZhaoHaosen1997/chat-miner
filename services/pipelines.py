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
        "system": "你是一个话题提取工具。只输出话题，每行一个。不要输出任何其他内容。",
        "user": "{chat}\n\n列出今天讨论的 2-4 个话题，每行一个，每句话不超过 25 字。\n示例：\n春节回家抢票经历\n新手机开箱讨论\n下周聚餐地点投票",
    },
    "quotes": {
        "system": "你是一个金句挖掘工具。格式：发言人|原话|你的吐槽，每行一条。不要输出任何其他内容。",
        "user": "{chat}\n\n找出 3-5 条最搞笑/精彩的发言。输出格式（严格按此格式）：\n发言人|原话|你的吐槽\n示例：\n张三|我昨天梦到自己在写代码|社畜的自我修养\n李四|今天天气真好，适合摸鱼|说出了大家的心声\n\n你的输出：",
    },
    "mood": {
        "system": "你是一个情绪识别工具。只回答一个词：欢乐、温馨、严肃、吐槽、平淡、热闹、伤感、沙雕。不要输出任何其他内容。",
        "user": "{chat}\n\n今天群聊的整体氛围是什么？只回答一个词（从以下选一个）：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕",
    },
    "keywords": {
        "system": "你是一个关键词提取工具。只输出 3-5 个关键词，逗号分隔。不要输出任何其他内容。",
        "user": "{chat}\n\n提取今天聊天的 3-5 个关键话题词（每词 2-6 字），逗号分隔。\n示例：春节,回家,抢票,高铁,12306\n\n你的输出：",
    },
    "oneline": {
        "system": "你是一个群聊总结工具。先在心里回顾今天的聊天主线，然后严格输出两行：第一行总结，第二行高光时刻。不要加序号或前缀。",
        "user": "{chat}\n\n第一行：用20字内有梗的话总结今天群聊\n第二行：今天最值得记录的瞬间\n示例：\n红包大战和加班吐槽的周五\n张三连发10个红包手速惊人\n\n你的输出：",
    },
    "active_hours": {
        "system": "你是一个活跃度分析工具。一句话描述活跃规律。不要输出任何其他内容。",
        "user": "消息按小时分布：\n{hourly_stats}\n\n一句话描述活跃规律（如\"下午2-5点最活跃，上午安静\"）：",
    },
}

PORTRAIT_PROMPTS = {
    "persona": {
        "system": "你是一个人物分析工具。每行一个标签。不要输出任何其他内容，不要解释。",
        "user": "{chat}\n\n以上是 {name} 的发言。分析ta的特征，输出三行：\n第一行：性格标签（逗号分隔，2-3个，如：幽默,话痨,热心肠）\n第二行：说话风格（一个词，如：豪爽/温柔/毒舌/理性/活泼/老成）\n第三行：群内角色（从以下选一个：气氛组/和事佬/话题制造机/话题终结者/吃瓜群众/潜水大佬/毒舌评论员/科普达人）\n示例：\n幽默,话痨,热心肠\n活泼\n气氛组\n\n你的输出：",
    },
    "interests": {
        "system": "你是一个兴趣分析工具。输出两行，不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。分析ta的兴趣特征，输出两行：\n第一行：关注话题/兴趣（逗号分隔，3-5个，如：游戏,美食,科技,篮球,投资）\n第二行：活跃时段（如：夜猫子22:00-02:00 / 上班摸鱼9:00-18:00 / 周末活跃）\n示例：\n游戏,美食,科技,篮球\n夜猫子22:00-02:00\n\n你的输出：",
    },
    "phrase": {
        "system": "你是一个口头禅检测工具。只回答口头禅或\"无\"，不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。ta 有口头禅或习惯用语吗？\n- 如果有，直接写出那句口头禅（不要加引号或解释）\n- 如果没有明显口头禅，只回答：无\n示例：笑死\n你的输出：",
    },
    "oneline_portrait": {
        "system": "你是一个人物素描工具。两行输出：人设+emoji，不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。用一句话+emoji形容ta：\n第一行：15字一句话人设（如：爱吐槽但热心的老大哥）\n第二行：2个emoji形容ta（如：🤡🔥）\n示例：\n爱吐槽但热心的老大哥\n🤡🔥\n\n你的输出：",
    },
}


# ---- 管道执行 ----

MAX_RETRIES = 3
STEP_TIMEOUT = 90  # 单个子任务（含重试）总超时秒数
CIRCUIT_BREAKER_THRESHOLD = 5  # 连续失败 N 次触发熔断
CIRCUIT_BREAKER_COOLDOWN = 30  # 熔断冷却时间（秒）

# 全局熔断器状态
_circuit_state = {
    "consecutive_failures": 0,
    "last_failure_time": 0.0,
    "tripped": False,
}


def _check_circuit() -> bool:
    """检查熔断器状态，返回 True 表示可以继续"""
    global _circuit_state
    if not _circuit_state["tripped"]:
        return True
    # 检查冷却时间是否到了
    if time.time() - _circuit_state["last_failure_time"] > CIRCUIT_BREAKER_COOLDOWN:
        logger.info("熔断器冷却完毕，恢复调用")
        _circuit_state["tripped"] = False
        _circuit_state["consecutive_failures"] = 0
        return True
    return False


def _report_failure():
    """报告一次失败，可能触发熔断"""
    global _circuit_state
    _circuit_state["consecutive_failures"] += 1
    _circuit_state["last_failure_time"] = time.time()
    if _circuit_state["consecutive_failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        _circuit_state["tripped"] = True
        logger.warning(
            f"熔断器触发！连续 {_circuit_state['consecutive_failures']} 次失败，"
            f"冷却 {CIRCUIT_BREAKER_COOLDOWN}s"
        )


def _report_success():
    """报告一次成功，重置熔断计数"""
    global _circuit_state
    _circuit_state["consecutive_failures"] = 0
    _circuit_state["tripped"] = False


# AI 常见道歉/拒绝输出的模式
_AI_APOLOGY_PATTERNS = [
    "抱歉", "对不起", "无法", "不能", "作为AI", "作为人工智能",
    "我是一个AI", "我无法", "我不能", "请提供", "需要更多",
    "sorry", "I cannot", "I can't", "as an AI",
]


def _is_ai_apology(text: str) -> bool:
    """检测是否是 AI 的道歉/拒绝式输出"""
    t = text.lower()
    return any(p.lower() in t for p in _AI_APOLOGY_PATTERNS)


def _parse_lines(raw) -> list[str]:
    """解析 AI 返回的文本为行列表（过滤空行、编号前缀和道歉文本）"""
    if not raw: return []
    text = raw if isinstance(raw, str) else str(raw)
    # AI 道歉检测：如果整体是道歉文本，返回空
    if _is_ai_apology(text):
        return []
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip().lstrip("-*•1234567890.、）) ").strip()
        # 过滤空行、太短的行、道歉行
        if line and len(line) > 2 and not _is_ai_apology(line):
            lines.append(line)
    return lines


def _parse_quotes(raw) -> list[dict]:
    """解析 发言人|原话|吐槽 格式"""
    if not raw: return []
    text = raw if isinstance(raw, str) else str(raw)
    quotes = []
    for line in text.strip().split("\n"):
        line = line.strip()
        parts = line.split("|", 2)  # 最多切3段，防止消息内容中的|被误切
        if len(parts) >= 2:
            quotes.append({
                "speaker": parts[0].strip(),
                "quote": parts[1].strip(),
                "comment": parts[2].strip() if len(parts) > 2 else "",
            })
    return quotes


def _parse_kw(raw) -> list[str]:
    """解析逗号/顿号分隔的关键词，过滤过长（疑似句子）的项"""
    if not raw: return ["群聊"]
    text = raw if isinstance(raw, str) else str(raw)
    # AI 道歉检测
    if _is_ai_apology(text):
        return ["群聊"]
    import re
    kws = re.split(r"[,，、\n]+", text.strip())
    result = []
    for k in kws:
        k = k.strip().lstrip("#")
        # 过滤：太短、太长（疑似句子）、纯数字
        if len(k) < 2 or len(k) > 12 or k.isdigit():
            continue
        result.append(k)
    return result[:5] if result else ["群聊"]


MOOD_MAP = {"欢乐":"😄","温馨":"🥰","严肃":"🧐","吐槽":"😤","平淡":"😐","热闹":"🎉","伤感":"😢","沙雕":"🤪"}


def _parse_mood(raw) -> tuple[str, str]:
    """从文本中提取 mood 词并映射 emoji，无法识别时返回默认值"""
    text = str(raw).strip() if raw else ""
    # AI 道歉检测
    if _is_ai_apology(text):
        return "平淡", "😐"
    for m, e in MOOD_MAP.items():
        if m in text:
            return m, e
    # 模糊匹配更多情绪
    MOOD_ALIAS = {
        "开心": "欢乐", "高兴": "欢乐", "愉快": "欢乐", "快乐": "欢乐",
        "温暖": "温馨", "感动": "温馨",
        "吵架": "严肃", "争论": "严肃", "认真": "严肃",
        "抱怨": "吐槽", "不满": "吐槽",
        "无聊": "平淡", "安静": "平淡",
        "兴奋": "热闹", "活跃": "热闹",
        "难过": "伤感", "悲伤": "伤感", "emo": "伤感",
        "搞笑": "沙雕", "整活": "沙雕",
    }
    for alias, mood in MOOD_ALIAS.items():
        if alias in text:
            return mood, MOOD_MAP.get(mood, "😐")
    return "平淡", "😐"


def _parse_oneline(raw) -> tuple[str, str]:
    """解析两行：第一行总结，第二行高光。加长度校验和道歉检测"""
    text = str(raw) if raw else ""
    if _is_ai_apology(text):
        return "今天也是热闹的一天", ""
    lines = _parse_lines(raw)
    one_line = lines[0] if len(lines) > 0 else "今天也是热闹的一天"
    highlight = lines[1] if len(lines) > 1 else ""
    # 截断过长内容
    return one_line[:50], highlight[:100]


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
                   system: str, user: str, model: str = "",
                   result_validator = None) -> Optional[dict]:
    """执行一个子任务，失败自动重试（最多 3 次），返回解析后的 dict

    Args:
        result_validator: 可选的结果校验函数，接收 (data) 返回 (is_valid, hint)
                          如果前次输出格式不对，hint 会追加到重试 prompt 中
    """
    import asyncio

    last_error = ""
    total_start = time.time()

    for attempt in range(1, MAX_RETRIES + 1):
        result2 = None  # 每轮重置，避免跨迭代污染

        # 熔断器检查
        if _circuit_state["tripped"] and not _check_circuit():
            last_error = f"熔断器触发，冷却中（还需 {CIRCUIT_BREAKER_COOLDOWN - int(time.time() - _circuit_state['last_failure_time'])}s）"
            logger.warning(f"{step_name}: {last_error}")
            await asyncio.sleep(5)
            continue
        # 总超时检查
        if time.time() - total_start > STEP_TIMEOUT:
            last_error = f"子任务总超时 ({STEP_TIMEOUT}s)"
            logger.warning(f"{step_name}: {last_error}")
            break

        label = f"({step_idx}/{total}) {step_name}" if attempt == 1 else f"({step_idx}/{total}) {step_name} 重试{attempt}/{MAX_RETRIES}"
        if task:
            task.update("inference", f"{label}...")
        logger.info(f"{step_name} 第{attempt}次尝试, 模型={model or config.OLLAMA_MODEL}")

        # 重试时在 prompt 末尾追加格式提醒
        retry_user = user
        if attempt > 1:
            retry_user = user + "\n\n（⚠️ 上次你的回答格式不符合要求，请严格按上述格式输出，不要添加任何解释、序号、前缀或额外文字。只输出答案本身。）"

        # --- 主模型 ---
        start = time.time()
        try:
            result = await asyncio.wait_for(
                call_ollama_chat(system, retry_user, model, timeout=40),  # 单次调用 40s 超时
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
            _report_success()
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
                    call_ollama_chat(system, retry_user, config.OLLAMA_MODEL_FALLBACK, timeout=40),
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
                _report_success()
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
    _report_failure()
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


    failed_steps = []

    # 1. 话题（每行一个）
    topics_data = await _run_sub(task, "提取话题", 1, total,
                                  PROMPTS["topics"]["system"],
                                  f"{chat_text}\n\n{PROMPTS['topics']['user']}")
    topics = _parse_lines(topics_data) if topics_data else []
    if not topics:
        topics = ["今日话题"]
        failed_steps.append("topics")

    # 2. 搞笑发言（发言人|原话|吐槽）
    quotes_data = await _run_sub(task, "找搞笑发言", 2, total,
                                  PROMPTS["quotes"]["system"],
                                  f"{chat_text}\n\n{PROMPTS['quotes']['user']}")
    quotes = _parse_quotes(quotes_data) if quotes_data else []
    if not quotes and quotes_data is None:
        failed_steps.append("quotes")

    # 3. 情绪（一个词）
    mood_data = await _run_sub(task, "判断情绪", 3, total,
                                PROMPTS["mood"]["system"],
                                f"{chat_text}\n\n{PROMPTS['mood']['user']}")
    mood, mood_emoji = _parse_mood(mood_data)
    if mood_data is None:
        failed_steps.append("mood")

    # 4. 关键词（逗号分隔）
    kw_data = await _run_sub(task, "提取关键词", 4, total,
                              PROMPTS["keywords"]["system"],
                              f"{chat_text}\n\n{PROMPTS['keywords']['user']}")
    keywords = _parse_kw(kw_data)
    if kw_data is None:
        failed_steps.append("keywords")

    # 5. 一句话总结（两行：总结+高光）
    ol_data = await _run_sub(task, "一句话总结", 5, total,
                              PROMPTS["oneline"]["system"],
                              f"{chat_text}\n\n{PROMPTS['oneline']['user']}")
    one_line, highlight = _parse_oneline(ol_data)
    if ol_data is None:
        failed_steps.append("oneline")

    # 6. 活跃时段（一句话描述）
    hs = (hourly_stats or "(无小时分布数据)").replace("{", "{{").replace("}", "}}")
    hs_user = PROMPTS["active_hours"]["user"].replace("{hourly_stats}", hs)
    ah_data = await _run_sub(task, "活跃时段分析", 6, total,
                              PROMPTS["active_hours"]["system"], hs_user)
    ah = _parse_active_hours(ah_data)
    if ah_data is None:
        failed_steps.append("active_hours")

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
    if failed_steps:
        report["_partial"] = True
        report["_failed_steps"] = failed_steps
        logger.warning(f"部分成功: {len(failed_steps)}/{total} 个子任务失败: {failed_steps}")

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
    failed_steps = []

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
    if p_data is None:
        failed_steps.append("persona")

    # 2. 兴趣+活跃时段（两行文本）
    i_data = await _run_sub(task, "分析兴趣爱好", 2, total,
                             PORTRAIT_PROMPTS["interests"]["system"],
                             f"{prompt_user}{PORTRAIT_PROMPTS['interests']['user'].replace('{name}', sender_name)}")
    i_lines = _parse_lines(i_data)
    interests = [t.strip() for t in i_lines[0].replace("，",",").split(",")] if len(i_lines) > 0 else []
    active_hours = i_lines[1] if len(i_lines) > 1 else ""
    if i_data is None:
        failed_steps.append("interests")

    # 3. 口头禅（一个词或"无"）
    ph_data = await _run_sub(task, "检测口头禅", 3, total,
                              PORTRAIT_PROMPTS["phrase"]["system"],
                              f"{prompt_user}{PORTRAIT_PROMPTS['phrase']['user'].replace('{name}', sender_name)}")
    ph_text = str(ph_data or "").strip()
    signature_phrase = None if "无" in ph_text or not ph_text else ph_text[:50]
    if ph_data is None:
        failed_steps.append("phrase")

    # 4. 一句话+emoji（两行文本）
    ol_data = await _run_sub(task, "一句话素描", 4, total,
                              PORTRAIT_PROMPTS["oneline_portrait"]["system"],
                              f"{prompt_user}{PORTRAIT_PROMPTS['oneline_portrait']['user'].replace('{name}', sender_name)}")
    ol_lines = _parse_lines(ol_data)
    one_line = ol_lines[0] if len(ol_lines) > 0 else ""
    emoji_style = ol_lines[1] if len(ol_lines) > 1 else "👤"
    if ol_data is None:
        failed_steps.append("oneline_portrait")

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
    if failed_steps:
        portrait["_partial"] = True
        portrait["_failed_steps"] = failed_steps
        logger.warning(f"画像部分成功: {len(failed_steps)}/{total} 个子任务失败: {failed_steps}")

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
