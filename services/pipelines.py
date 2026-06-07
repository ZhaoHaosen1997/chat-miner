"""
子任务管道：把复杂 AI 分析拆成多个极简子任务
每个子任务只问一件事，返回极简格式，管道拼装完整 JSON
"""
import json
import re
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
        "system": "你是一个情绪识别工具。只回答一个词。不要输出任何其他内容。",
        "user": "{chat}\n\n今天群聊的整体氛围是什么？只回答一个词（从以下选）：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕 吃瓜 摸鱼 摆烂 内卷 开车 破防 凡尔赛 社死 真香 画饼 CPU 离谱 上头",
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
    # ---- v0.5.1 趣味功能 ----
    "headline": {
        "system": "你是一个综艺节目预告片编导。用UC震惊体/综艺体给群聊写一句话预告。要夸张有趣。只输出一句话，不要输出任何其他内容。",
        "user": "{chat}\n\n用综艺预告片的语气，写一句15字内的群聊今日预告（要抓马、有梗）：",
    },
    "scene_commentary": {
        "system": "你是一个综艺节目花字写手。给群聊名场面配花字吐槽，要犀利好笑。只输出一句话，不要输出任何其他内容。",
        "user": "群聊名场面：{scene}\n\n用综艺花字风格写一句吐槽点评（10字内，要犀利）：",
    },
}

# ---- 趣味称号 Prompt ----
FUN_TITLE_PROMPTS = {
    "system": "你是一个综艺节目人设编剧。根据数据给群友起一个有趣的称号，要精准有梗。只输出称号，不要输出任何其他内容。",
    "user": "成员 {name} 的数据：\n{data_summary}\n\n给ta起一个有趣的称号（6字内，如\"深夜哲学家\"\"红包闪电侠\"\"潜水冠军\"\"表情包大户\"\"奶茶品鉴师\"）：",
}

# ---- 关系趣味解读 Prompt ----
FUN_RELATION_PROMPTS = {
    "system": "你是一个综艺节目旁白。给一对群友的互动写趣味关系解读，要像星座配对一样好玩。只输出一句话，不要输出任何其他内容。",
    "user": "{name_a} 和 {name_b} 互动 {count} 次，关系类型：{relation_type}\n\n用一句话趣味解读他们的群内关系（15字内，如\"互怼328次的最佳损友\"\"深夜固定聊天搭子\"）：",
}

PORTRAIT_PROMPTS = {
    "persona": {
        "system": "你是一个人物分析工具。只输出三行纯文字，不要加\"第一行：\"等前缀，不要解释。标签要具体、有区分度，避免用\"幽默\"\"话痨\"\"沙雕\"这种放谁身上都行的词。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出三行纯文字（不要加任何前缀）：\n第一行：2-3个性格标签，逗号分隔。要精准，可选：较真/随和/社恐/自来熟/刀子嘴/老好人/玻璃心/佛系/急性子/细节控/强迫症/摆烂王/卷王/乐子人/吃货/愤青/文艺/实用主义\n第二行：一个词的说话风格，如：豪爽/温柔/毒舌/理性/活泼/老成/阴阳怪气/一本正经/骚话连篇/惜字如金/直球/拐弯抹角/杠精/捧场王/冷场王\n第三行：一个群内角色，从以下选：气氛组/和事佬/话题制造机/话题终结者/吃瓜群众/潜水大佬/毒舌评论员/科普达人/摸鱼冠军/卷王/凡尔赛大师/画饼专家/真香选手/社死担当/破防boy/摆烂王者",
    },
    "interests": {
        "system": "你是一个兴趣分析工具。只输出两行纯文字，不要加\"第一行：\"等前缀，不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出两行纯文字：\n第一行：关注话题/兴趣，逗号分隔3-5个，如：游戏,美食,科技,篮球,投资\n第二行：活跃时段，如：夜猫子22:00-02:00 / 上班摸鱼9:00-18:00 / 周末活跃\n示例：\n游戏,美食,科技,篮球\n夜猫子22:00-02:00",
    },
    "phrase": {
        "system": "你是一个口头禅检测工具。只回答口头禅或\"无\"，不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。ta 有口头禅或习惯用语吗？\n- 如果有，直接写出那句口头禅（不要加引号或解释）\n- 如果没有明显口头禅，只回答：无\n示例：笑死\n你的输出：",
    },
    "oneline_portrait": {
        "system": "你是一个人物素描工具。只输出两行纯文字，不要加任何前缀和引号。第一行是人设描述，第二行是两个emoji。",
        "user": "{chat}\n\n以上是 {name} 的发言。参照以下格式，只输出两行：\n爱吐槽但热心的老大哥\n🤡🔥\n\n更多第一行参考：每天分享早餐的奶茶品鉴师 / 一开口就歪楼的飙车党 / 深夜emo完早上装没事的戏精\n\n你的两行输出（不要加前缀）：",
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
        line = line.strip()
        # 去掉 "第一行：" "第二行：" 等 AI 误输出的格式标签
        line = re.sub(r'^第[一二三四五六七八九十\d]+[行行][：:]\s*', '', line)
        line = line.lstrip("-*•1234567890.、）) ").strip()
        # 过滤空行、太短的行、道歉行
        if line and len(line) >= 1 and not _is_ai_apology(line):
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


MOOD_MAP = {
    "欢乐":"😄","温馨":"🥰","严肃":"🧐","吐槽":"😤","平淡":"😐","热闹":"🎉","伤感":"😢","沙雕":"🤪",
    "吃瓜":"🍉","摸鱼":"🎣","摆烂":"🫠","内卷":"💪","开车":"🚗","破防":"💔","凡尔赛":"👑",
    "社死":"💀","真香":"🍚","画饼":"🫓","CPU":"🔥","离谱":"👽","上头":"🤯",
}


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
        "抱怨": "吐槽", "不满": "吐槽", "阴阳": "吐槽",
        "无聊": "平淡", "安静": "平淡",
        "兴奋": "热闹", "活跃": "热闹",
        "难过": "伤感", "悲伤": "伤感", "emo": "伤感",
        "搞笑": "沙雕", "整活": "沙雕",
        "围观": "吃瓜", "八卦": "吃瓜", "吃瓜群众": "吃瓜",
        "偷懒": "摸鱼", "划水": "摸鱼", "摸鱼摸鱼": "摸鱼",
        "躺平": "摆烂", "放弃": "摆烂", "累了": "摆烂",
        "卷": "内卷", "加班": "内卷", "卷王": "内卷",
        "黄腔": "开车", "飙车": "开车", "车速": "开车",
        "心碎": "破防", "崩溃": "破防", "绷不住": "破防",
        "炫耀": "凡尔赛", "装逼": "凡尔赛",
        "尬": "社死", "尴尬": "社死", "社死现场": "社死",
        "打脸": "真香", "反转": "真香",
        "许诺": "画饼", "饼": "画饼", "画大饼": "画饼",
        "洗脑": "CPU", "PUA": "CPU",
        "夸张": "离谱", "离谱他妈": "离谱",
        "震惊": "上头", "震撼": "上头", "惊呆": "上头",
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
    PEAKS = {"上午摸鱼":"上午","午间活跃":"中午","下午茶话会":"下午","晚间热闹":"晚上","夜猫子专场":"深夜","全天在线":"全天","凌晨修仙":"凌晨","通宵战神":"通宵"}
    peak_label = ""
    for k, v in PEAKS.items():
        if k in text: peak_label = k; break
    if not peak_label:
        # 模糊匹配
        for kw, label in [("上午","上午摸鱼"),("中午","午间活跃"),("下午","下午茶话会"),("晚上","晚间热闹"),("夜间","夜猫子专场"),("凌晨","凌晨修仙"),("通宵","通宵战神"),("全天","全天在线")]:
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

    for attempt in range(1, MAX_RETRIES + 1):
        result2 = None  # 每轮重置，避免跨迭代污染

        # 取消检查
        if task and hasattr(task, '_cancelled') and task._cancelled:
            logger.info(f"{step_name}: 任务已取消")
            return None

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
        result = await call_ollama_chat(system, retry_user, model, timeout=60)

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
            result2 = await call_ollama_chat(
                system, retry_user, config.OLLAMA_MODEL_FALLBACK, timeout=60
            )

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
    """执行 8 步子任务管道，拼装每日报告 JSON（含趣味功能）"""
    total = 8

    if task:
        task.update("inference", f"(0/6) 开始分析...")
        task.steps.clear()


    failed_steps = []

    # 取消检查辅助
    def _cancelled():
        return task and hasattr(task, '_cancelled') and task._cancelled

    # 1. 话题（每行一个）
    if _cancelled(): return {}
    topics_data = await _run_sub(task, "提取话题", 1, total,
                                  PROMPTS["topics"]["system"],
                                  f"{chat_text}\n\n{PROMPTS['topics']['user']}")
    topics = _parse_lines(topics_data) if topics_data else []
    if not topics:
        topics = ["今日话题"]
        failed_steps.append("topics")

    # 2. 搞笑发言（发言人|原话|吐槽）
    if _cancelled(): return {}
    quotes_data = await _run_sub(task, "找搞笑发言", 2, total,
                                  PROMPTS["quotes"]["system"],
                                  f"{chat_text}\n\n{PROMPTS['quotes']['user']}")
    quotes = _parse_quotes(quotes_data) if quotes_data else []
    if not quotes and quotes_data is None:
        failed_steps.append("quotes")

    # 3. 情绪（一个词）
    if _cancelled(): return {}
    mood_data = await _run_sub(task, "判断情绪", 3, total,
                                PROMPTS["mood"]["system"],
                                f"{chat_text}\n\n{PROMPTS['mood']['user']}")
    mood, mood_emoji = _parse_mood(mood_data)
    if mood_data is None:
        failed_steps.append("mood")

    # 4. 关键词（逗号分隔）
    if _cancelled(): return {}
    kw_data = await _run_sub(task, "提取关键词", 4, total,
                              PROMPTS["keywords"]["system"],
                              f"{chat_text}\n\n{PROMPTS['keywords']['user']}")
    keywords = _parse_kw(kw_data)
    if kw_data is None:
        failed_steps.append("keywords")

    # 5. 一句话总结（两行：总结+高光）
    if _cancelled(): return {}
    ol_data = await _run_sub(task, "一句话总结", 5, total,
                              PROMPTS["oneline"]["system"],
                              f"{chat_text}\n\n{PROMPTS['oneline']['user']}")
    one_line, highlight = _parse_oneline(ol_data)
    if ol_data is None:
        failed_steps.append("oneline")

    # 6. 活跃时段（一句话描述）
    if _cancelled(): return {}
    hs = (hourly_stats or "(无小时分布数据)").replace("{", "{{").replace("}", "}}")
    hs_user = PROMPTS["active_hours"]["user"].replace("{hourly_stats}", hs)
    ah_data = await _run_sub(task, "活跃时段分析", 6, total,
                              PROMPTS["active_hours"]["system"], hs_user)
    ah = _parse_active_hours(ah_data)
    if ah_data is None:
        failed_steps.append("active_hours")

    # 7. 趣味标题（UC震惊体/综艺预告片风）
    if _cancelled(): return {}
    headline_data = await _run_sub(task, "趣味标题", 7, total,
                                    PROMPTS["headline"]["system"],
                                    f"{chat_text}\n\n{PROMPTS['headline']['user']}")
    headline = str(headline_data).strip() if headline_data else ""

    # 8. 名场面（取最佳搞笑发言，AI配花字吐槽）
    scene_commentary = ""
    if quotes and len(quotes) > 0:
        best_quote = quotes[0]
        scene_text = f"{best_quote.get('speaker','某人')}：「{best_quote.get('quote','')}」"
        scene_user = PROMPTS["scene_commentary"]["user"].format(scene=scene_text)
        scene_data = await _run_sub(task, "名场面吐槽", 8, total,
                                     PROMPTS["scene_commentary"]["system"],
                                     scene_user)
        scene_commentary = str(scene_data).strip() if scene_data else ""
    if headline_data is None:
        failed_steps.append("headline")

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
        "headline": headline or one_line,  # 趣味标题，无则回退到总结
        "scene_commentary": scene_commentary,  # 名场面花字吐槽
    }
    if failed_steps:
        report["_partial"] = True
        report["_failed_steps"] = failed_steps
        logger.warning(f"部分成功: {len(failed_steps)}/{total} 个子任务失败: {failed_steps}")

    if task:
        task.model_used = config.OLLAMA_MODEL
        # 批量任务不在这里 finish，由外层循环控制
        if task.type not in ("analyze_all", "full_portrait", "analyze_all_portraits"):
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
        if task.type != "full_portrait":
            task.steps.clear()  # 统一分析时不重置，追加到已有步骤

    prompt_user = f"{chat_text}\n\n以上是 {sender_name} 的发言。"
    role_opts = "气氛组/和事佬/话题制造机/话题终结者/吃瓜群众/潜水大佬/毒舌评论员/科普达人/摸鱼冠军/卷王/凡尔赛大师/画饼专家/真香选手/社死担当/开车司机/破防boy/摆烂王者"
    failed_steps = []

    def _cancelled_portrait():
        return task and hasattr(task, '_cancelled') and task._cancelled

    # 1. 性格+角色（三行文本）
    if _cancelled_portrait(): return {}
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
        if task.type not in ("analyze_all", "full_portrait", "analyze_all_portraits"):
            task.finish(success=True)
        _save_pipeline_record(task, group_name, sender_name)

    return portrait


# ---- 深度画像 Pipeline (v0.5) ----
# 基于 Python 统计数据摘要做 AI 分析，不直接读原始消息

DEEP_PORTRAIT_PROMPTS = {
    "emotion": {
        "system": "你是一个情绪分析工具。基于数据摘要，用一句话描述情绪特征。不要输出任何其他内容。",
        "user": "成员 {name} 的情绪数据：\n{emotion_summary}\n\n用一句话描述 {name} 的整体情绪特征（如\"乐天派，情绪稳定\"或\"情绪波动大，容易被激怒\"）：",
    },
    "language": {
        "system": "你是一个语言风格分析工具。基于数据摘要，用 2-3 句话描述语言风格。不要输出任何其他内容。",
        "user": "成员 {name} 的语言数据：\n{language_summary}\n\n用 2-3 句话描述 {name} 的语言风格（包括句长特点、emoji使用习惯、口头表达特点）：",
    },
    "emotion_trend": {
        "system": "你是一个情绪趋势分析工具。基于情绪数据，用一句话描述趋势。不要输出任何其他内容。",
        "user": "成员 {name} 的每日情绪变化：\n{emotion_details}\n\n用一句话描述 {name} 的情绪趋势（如\"越来越活跃积极\"、\"情绪相对稳定\"、\"最近开始变沉默\"）：",
    },
    "monthly_synthesis": {
        "system": "你是一个总结工具。把多个月的分析结果整合成一段趋势描述。不要输出任何其他内容。",
        "user": "成员 {name} 各月分析摘要：\n{monthly_summaries}\n\n用 2-3 句话总结 {name} 在 {total_months} 个月中的变化趋势（话题变化、活跃度变化、情绪变化）：",
    },
}


async def _run_monthly_slice(task, month_label: str, chat_text: str,
                              name: str, model: str = "") -> Optional[dict]:
    """对单个自然月的发言做极简 AI 分析（2 个子任务：话题 + 情绪）

    Args:
        month_label: "2025-01"
        chat_text: 该月的格式化发言文本（已截断 ≤ 3000 字）
        name: 成员名
        model: 模型名

    Returns:
        {"month": "2025-01", "topics": [...], "mood": "..."} 或 None
    """
    safe_chat = chat_text.replace("{", "{{").replace("}", "}}")
    safe_name = name.replace("{", "{{").replace("}", "}}")

    # 子任务 1：当月话题
    topic_system = "你是一个话题提取工具。只输出 2-3 个话题关键词，逗号分隔。不要输出任何其他内容。"
    topic_user = f"{safe_chat}\n\n以上是 {safe_name} 在 {month_label} 的发言。输出 2-3 个ta关注的话题关键词："
    topic_result = await _run_sub(task, f"月度话题 {month_label}", 0, 2,
                                   topic_system, topic_user, model)

    # 子任务 2：当月情绪
    mood_system = "你是一个情绪识别工具。只回答一个词。"
    mood_user = f"{safe_chat}\n\n以上是 {safe_name} 在 {month_label} 的发言。ta 这个月的发言情绪是什么？只回答一个词：欢乐 温馨 严肃 吐槽 平淡 热闹 伤感 沙雕 吃瓜 摸鱼 摆烂 内卷 破防 凡尔赛 社死 真香 画饼 离谱 上头"
    mood_result = await _run_sub(task, f"月度情绪 {month_label}", 0, 2,
                                  mood_system, mood_user, model)

    topics = _parse_kw(topic_result) if topic_result else ["未识别"]
    mood, _ = _parse_mood(mood_result)

    return {"month": month_label, "topics": topics, "mood": mood}


async def run_deep_portrait_pipeline(chat_text: str,  # 目标成员的部分发言（用于月度切片）
                                      messages: list[dict],  # 目标成员的全部消息
                                      sender_name: str,
                                      group_name: str,
                                      group_id: int,
                                      msg_count: int,
                                      stats_summary: dict,  # Python 统计数据摘要
                                      task=None) -> dict:
    """执行深度画像 Pipeline：月度切片 + 数据摘要 AI 分析

    不替代 run_portrait_pipeline，而是作为补充，产出更深维度的画像数据。

    Args:
        chat_text: 简短发言样本（用于月度切片分析，已截断）
        messages: 目标成员的全部消息（用于按月分块）
        sender_name: 成员名
        group_name: 群名
        group_id: 群 ID
        msg_count: 消息总数
        stats_summary: stats_engine.format_stats_for_ai() 的产出
        task: TaskInfo

    Returns:
        dict with emotion_profile, language_style, activity_deep, monthly_analysis
    """
    import time as _time
    from services.parser import chunk_messages_by_month

    if task:
        task.update("inference", "深度画像分析中...")
        if task.type != "full_portrait":
            task.steps.clear()

    failed_steps = []
    model = config.OLLAMA_MODEL
    safe_name = sender_name.replace("{", "{{").replace("}", "}}")
    TOTAL_STEPS = 5

    def _cancelled_deep():
        return task and hasattr(task, '_cancelled') and task._cancelled

    # ---- 1. 月度切片分析（先收集数据，后续情绪分析依赖这些数据） ----
    if _cancelled_deep(): return {}
    from services.parser import ParsedChat
    monthly_chunks = chunk_messages_by_month(messages, lambda sid: sender_name, max_chars_per_chunk=3000)

    monthly_analyses = []
    if monthly_chunks and task:
        task.update("inference", f"月度切片分析 (0/{len(monthly_chunks)})...")

    for i, (month_label, chunk) in enumerate(monthly_chunks):
        if _cancelled_deep(): break
        if task:
            task.update("inference", f"月度切片 ({i+1}/{len(monthly_chunks)}) {month_label}...")
        analysis = await _run_monthly_slice(task, month_label, chunk, sender_name, model)
        if analysis:
            monthly_analyses.append(analysis)

    # ---- 2. 情绪画像（基于月度切片的 mood 数据，不依赖 daily_reports） ----
    if monthly_analyses:
        emotion_details_lines = [
            f"{ma['month']}：情绪={ma['mood']}" for ma in monthly_analyses
        ]
        emotion_details = "\n".join(emotion_details_lines)
        emotion_timeline = [
            {"date": ma["month"], "mood": ma["mood"], "mood_emoji": ""}
            for ma in monthly_analyses
        ]
    else:
        emotion_details = "暂无情绪数据（月度切片不足）"
        emotion_timeline = []

    emo_user = DEEP_PORTRAIT_PROMPTS["emotion"]["user"].format(
        name=safe_name, emotion_summary=emotion_details
    )
    emo_data = await _run_sub(task, "深度-情绪总结", 2, TOTAL_STEPS,
                               DEEP_PORTRAIT_PROMPTS["emotion"]["system"], emo_user, model)
    emotion_primary = str(emo_data).strip() if emo_data else "暂无数据"

    trend_user = DEEP_PORTRAIT_PROMPTS["emotion_trend"]["user"].format(
        name=safe_name, emotion_details=emotion_details
    )
    trend_data = await _run_sub(task, "深度-情绪趋势", 2, TOTAL_STEPS,
                                 DEEP_PORTRAIT_PROMPTS["emotion_trend"]["system"],
                                 trend_user, model)
    emotion_trend = str(trend_data).strip() if trend_data else "暂无数据"

    emotion_profile = {
        "primary": emotion_primary,
        "trend": emotion_trend,
        "timeline": emotion_timeline,
    }
    if emo_data is None:
        failed_steps.append("emotion")

    # ---- 3. 语言风格洞察 ----
    lang_raw = stats_summary.get("language_summary", "暂无数据")
    lang_user = DEEP_PORTRAIT_PROMPTS["language"]["user"].format(
        name=safe_name, language_summary=lang_raw
    )
    lang_data = await _run_sub(task, "深度-语言风格", 3, TOTAL_STEPS,
                                DEEP_PORTRAIT_PROMPTS["language"]["system"],
                                lang_user, model)
    style_notes = str(lang_data).strip() if lang_data else "暂无数据"
    if lang_data is None:
        failed_steps.append("language")

    language_style = {
        "style_notes": style_notes,
    }

    # ---- 4. 月度汇总 ----
    monthly_summary_text = ""
    if monthly_analyses:
        lines = []
        for ma in monthly_analyses:
            lines.append(f"{ma['month']}：话题={'、'.join(ma['topics'])}，情绪={ma['mood']}")
        monthly_summary_text = "\n".join(lines)

        synth_user = DEEP_PORTRAIT_PROMPTS["monthly_synthesis"]["user"].format(
            name=safe_name,
            monthly_summaries=monthly_summary_text,
            total_months=len(monthly_analyses),
        )
        synth_data = await _run_sub(task, "深度-月度汇总", 4, TOTAL_STEPS,
                                     DEEP_PORTRAIT_PROMPTS["monthly_synthesis"]["system"],
                                     synth_user, model)
        monthly_synthesis = str(synth_data).strip() if synth_data else ""
    else:
        monthly_synthesis = "数据不足，无法生成月度汇总"

    if task:
        task.model_used = model
        if task.type not in ("analyze_all", "full_portrait", "analyze_all_portraits"):
            task.finish(success=True)
        _save_pipeline_record(task, group_name, sender_name)

    deep_portrait = {
        "emotion_profile": emotion_profile,
        "language_style": language_style,
        "monthly_analyses": monthly_analyses,
        "monthly_synthesis": monthly_synthesis,
    }
    if failed_steps:
        deep_portrait["_partial"] = True
        deep_portrait["_failed_steps"] = failed_steps
        logger.warning(f"深度画像部分成功: {len(failed_steps)} 个子任务失败: {failed_steps}")

    return deep_portrait


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
