"""
子任务管道：把复杂 AI 分析拆成多个极简子任务
每个子任务只问一件事，返回极简格式，管道拼装完整 JSON
"""
import json
import re
import time
import logging
from typing import Optional

from models.database import save_task_record, get_default_prompt
from services.analyzer import call_ollama_chat
from services.task_manager import task_manager
from config import config

logger = logging.getLogger(__name__)


def _is_cancelled(task) -> bool:
    """v1.2.11: 统一的取消检查，替代分散的 hasattr(task, '_cancelled') 模式"""
    return task is not None and task_manager.is_cancelled(task.task_id)

# ---- 私聊适配 ----
# 当群聊只有 2 人时，自动将 prompt 中的群聊话术替换为私聊话术
_PRIVATE_REPLACEMENTS = [
    ("群聊", "聊天"),
    ("群友", "对方"),
    ("群内", "聊天"),
    ("群里的", "聊天中的"),
    ("本群", "聊天"),
]


def _adapt_for_private(text: str) -> str:
    """将 prompt 文本中的群聊话术替换为私聊话术"""
    result = text
    for old, new in _PRIVATE_REPLACEMENTS:
        result = result.replace(old, new)
    return result


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
        "system": "你是一个综艺人物分析工具。只输出三行纯文字，不要加前缀、不要解释。标签要有区分度——\"幽默\"\"话痨\"\"沙雕\"几乎适用于所有人，只有确实突出时才用。要像给朋友贴标签一样有趣精准。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出三行纯文字：\n\n第一行：2-3个性格标签，逗号分隔。选最能区分ta的，参考（可自由发挥）：较真 随和 社恐 自来熟 刀子嘴 老好人 玻璃心 佛系 急性子 细节控 强迫症 摆烂王 卷王 乐子人 吃货 愤青 文艺 实用主义 养生达人 宠物博主 吃瓜能手 彩虹屁专家\n\n第二行：一个词的说话风格，参考（可自由发挥）：豪爽 温柔 毒舌 理性 活泼 老成 阴阳怪气 一本正经 骚话连篇 惜字如金 直球 拐弯抹角 杠精 捧场王 冷场王 凡尔赛口吻 领导腔 相声演员 戏精附体\n\n第三行：一个群内角色，从以下选：气氛组 和事佬 话题制造机 话题终结者 吃瓜群众 潜水大佬 毒舌评论员 科普达人 摸鱼冠军 卷王 凡尔赛大师 画饼专家 真香选手 社死担当 破防boy 摆烂王者 开车司机 红包侠\n\n只输出三行纯文字：",
    },
    "interests": {
        "system": "你是一个兴趣分析工具。只输出两行纯文字，不要加\"第一行：\"等前缀，不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。输出两行纯文字：\n第一行：关注话题/兴趣，逗号分隔3-5个，如：游戏,美食,科技,篮球,投资\n第二行：活跃时段，如：夜猫子22:00-02:00 / 上班摸鱼9:00-18:00 / 周末活跃\n示例：\n游戏,美食,科技,篮球\n夜猫子22:00-02:00",
    },
    "phrase": {
        "system": "你是一个口头禅检测工具。只输出口头禅，逗号分隔，或\"无\"。不要输出任何其他内容。",
        "user": "{chat}\n\n以上是 {name} 的发言。ta 有口头禅或习惯用语吗？\n- 如果有，输出 1-3 个口头禅，逗号分隔（如：笑死,哈哈哈,我去）\n- 如果没有明显口头禅，只回答：无\n你的输出：",
    },
    "oneline_portrait": {
        "system": "你是一个人物素描工具。只输出两行纯文字，不要加前缀和引号。第一行人设描述，第二行标签词。注意根据发言内容和语气判断性别，不要用性别错位的称呼（如对女生叫大哥、兄弟）。",
        "user": "{chat}\n\n以上是 {name} 的发言。分析ta最突出的特征，输出两行：\n\n第一行：8-18字的人设描述。不要写\"热心的老大哥\"\"爱吐槽的xxx\"这种泛泛模板。要抓最特别的一个点，可以调侃但要准确。\n\n第二行：选一个最匹配的标签词（只复制一个词，不要加数字和解释）：\n乐天派 整活王 暖心 暴脾气 老学究 派对咖 emo怪 沙雕\n吃瓜群众 摸鱼达人 摆烂王 卷王 老司机 玻璃心 凡尔赛\n社死选手 真香定律 画饼大师 CPU专家 外星人\n夜猫子 咖啡续命 游戏宅 美食家 潜水冠军 捧场王 毒舌 话痨 文艺青年 运动达人 追剧狂魔\n\n只输出两行，不要抄示例：",
    },
}


# ---- 管道执行 ----
# v1.17.0: 以下常量已迁移到 config.py + DB app_settings，通过 config.XXX 读取
# MAX_RETRIES       → config.PIPELINE_MAX_RETRIES (默认 3)
# STEP_TIMEOUT      → config.PIPELINE_STEP_TIMEOUT (默认 90)
# CIRCUIT_BREAKER_THRESHOLD → config.PIPELINE_CIRCUIT_BREAKER_THRESHOLD (默认 5)
# CIRCUIT_BREAKER_COOLDOWN   → config.PIPELINE_CIRCUIT_BREAKER_COOLDOWN (默认 30)

# 全局熔断器状态
_circuit_state = {
    "consecutive_failures": 0,
    "last_failure_time": 0.0,
    "tripped": False,
}
# v0.13.1: 熔断器异步锁，防止并发竞态
import asyncio
_circuit_lock = asyncio.Lock()


async def _check_circuit() -> bool:
    """检查熔断器状态，返回 True 表示可以继续"""
    async with _circuit_lock:
        if not _circuit_state["tripped"]:
            return True
        # 检查冷却时间是否到了
        if time.time() - _circuit_state["last_failure_time"] > config.PIPELINE_CIRCUIT_BREAKER_COOLDOWN:
            logger.info("熔断器冷却完毕，恢复调用")
            _circuit_state["tripped"] = False
            _circuit_state["consecutive_failures"] = 0
            return True
        return False


async def _report_failure():
    """报告一次失败，可能触发熔断"""
    async with _circuit_lock:
        _circuit_state["consecutive_failures"] += 1
        _circuit_state["last_failure_time"] = time.time()
        if _circuit_state["consecutive_failures"] >= config.PIPELINE_CIRCUIT_BREAKER_THRESHOLD:
            _circuit_state["tripped"] = True
            logger.warning(
                f"熔断器触发！连续 {_circuit_state['consecutive_failures']} 次失败，"
                f"冷却 {config.PIPELINE_CIRCUIT_BREAKER_COOLDOWN}s"
            )


async def _report_success():
    """报告一次成功，重置熔断计数"""
    async with _circuit_lock:
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


# 画像 emoji 标签映射（AI 输出标签词，Python 查表转 emoji）
# 比纯数字编号更鲁棒：14B 模型复制中文标签远比输出数字编号可靠
EMOJI_LABEL_MAP = {
    "乐天派": "😄✨", "整活王": "😈💀", "暖心": "🥰🌸", "暴脾气": "😤💢", "老学究": "🧐📚",
    "派对咖": "🎉🎊", "emo怪": "😢💧", "沙雕": "🤪👽", "吃瓜群众": "🍉☕", "摸鱼达人": "🎣🛋️",
    "摆烂王": "🫠💤", "卷王": "💪🔥", "老司机": "🚗💨", "玻璃心": "💔😭", "凡尔赛": "👑✨",
    "社死选手": "💀😱", "真香定律": "🍚🙏", "画饼大师": "🫓🤥", "CPU专家": "🔥🧠", "外星人": "👽🤯",
    # v0.6.4 新增
    "夜猫子": "🦉🌙", "咖啡续命": "☕😮‍💨", "游戏宅": "🎮🕹️", "美食家": "🍜🤤",
    "潜水冠军": "🤿💤", "捧场王": "👏🎉", "毒舌": "🐍☠️", "话痨": "🦜💬",
    "文艺青年": "🎨📖", "运动达人": "⚽🏃", "追剧狂魔": "📺🍿",
}

# 兼容旧版编号映射（AI 偶尔仍然输出数字）
EMOJI_CHOICES = {
    "1": "😄✨", "2": "😈💀", "3": "🥰🌸", "4": "😤💢", "5": "🧐📚",
    "6": "🎉🎊", "7": "😢💧", "8": "🤪👽", "9": "🍉☕", "10": "🎣🛋️",
    "11": "🫠💤", "12": "💪🔥", "13": "🚗💨", "14": "💔😭", "15": "👑✨",
    "16": "💀😱", "17": "🍚🙏", "18": "🫓🤥", "19": "🔥🧠", "20": "👽🤯",
}

def _match_emoji_by_label(label_text: str) -> str:
    """根据 AI 输出的标签文本匹配 emoji，支持精确匹配 + 模糊匹配"""
    if not label_text:
        return ""
    label = label_text.strip()
    # 1. 精确匹配
    if label in EMOJI_LABEL_MAP:
        return EMOJI_LABEL_MAP[label]
    # 2. 子串匹配（如 AI 输出"乐天派一枚" → 匹配"乐天派"）
    for key, emoji in EMOJI_LABEL_MAP.items():
        if key in label or label in key:
            return emoji
    return ""

def _auto_select_emoji(top_emojis: list[dict], peak_hour: int,
                       avg_msg_len: float, avg_daily: float) -> str:
    """纯 Python 兜底：根据成员实际数据自动选择画像 emoji
    完全不依赖 AI，保证每个成员都有区分度的 emoji

    Args:
        top_emojis: compute_language_stats 返回的 top_emojis 列表
        peak_hour: 最活跃小时 (0-23)
        avg_msg_len: 平均消息长度
        avg_daily: 日均发言数
    """
    # 1. 根据最常用表情判定
    emoji_texts = " ".join(e["emoji"] for e in (top_emojis or [])[:5])
    if any(e in emoji_texts for e in ["偷笑", "捂脸", "呲牙", "憨笑", "大笑"]):
        return "😄✨"  # 乐天派
    if any(e in emoji_texts for e in ["强", "抱拳", "OK", "好的", "赞"]):
        return "👏🎉"  # 捧场王
    if any(e in emoji_texts for e in ["裂开", "苦涩", "流泪", "大哭", "心碎"]):
        return "😢💧"  # emo怪
    if any(e in emoji_texts for e in ["狗头", "机智", "斜眼", "坏笑", "阴险"]):
        return "🐍☠️"  # 毒舌
    if any(e in emoji_texts for e in ["红包", "發", "恭喜", "发财"]):
        return "🎉🎊"  # 派对咖

    # 2. 根据活跃时段判定
    if 23 <= peak_hour or peak_hour <= 5:
        return "🦉🌙"  # 夜猫子
    if 6 <= peak_hour <= 8:
        return "☕😮‍💨"  # 咖啡续命
    if 9 <= peak_hour <= 17:
        return "🎣🛋️"  # 摸鱼达人

    # 3. 根据发言特征判定
    if avg_daily <= 2:
        return "🤿💤"  # 潜水冠军
    if avg_daily >= 30:
        return "🦜💬"  # 话痨
    if avg_msg_len >= 50:
        return "🧐📚"  # 老学究

    return "🍉☕"  # 吃瓜群众（通用兜底，比其他默认更有个性）

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

    last_error = ""
    total_start = time.time()
    circuit_waits = 0  # v1.2.11: 熔断器等待计数，防止无限循环

    for attempt in range(1, config.PIPELINE_MAX_RETRIES + 1):
        result2 = None  # 每轮重置，避免跨迭代污染

        # 取消检查
        if _is_cancelled(task):
            logger.info(f"{step_name}: 任务已取消")
            return None

        # 熔断器检查（v1.2.11: 加最大等待次数，防止无限循环）
        if _circuit_state["tripped"] and not await _check_circuit():
            circuit_waits += 1
            if circuit_waits > 6:
                last_error = f"熔断器等待超时（{circuit_waits * 5}s），放弃重试"
                logger.error(f"{step_name}: {last_error}")
                break
            last_error = f"熔断器触发，冷却中（还需 {config.PIPELINE_CIRCUIT_BREAKER_COOLDOWN - int(time.time() - _circuit_state['last_failure_time'])}s）"
            logger.warning(f"{step_name}: {last_error}")
            await asyncio.sleep(5)
            continue
        circuit_waits = 0  # 熔断器恢复，重置计数
        # 总超时检查
        if time.time() - total_start > config.PIPELINE_STEP_TIMEOUT:
            last_error = f"子任务总超时 ({config.PIPELINE_STEP_TIMEOUT}s)"
            logger.warning(f"{step_name}: {last_error}")
            break

        label = f"({step_idx}/{total}) {step_name}" if attempt == 1 else f"({step_idx}/{total}) {step_name} 重试{attempt}/{config.PIPELINE_MAX_RETRIES}"
        if task:
            task.update("inference", f"{label}...")
        logger.debug(f"{step_name} 第{attempt}次尝试, 模型={model or config.OLLAMA_MODEL}")

        # 重试时在 prompt 末尾追加格式提醒
        retry_user = user
        if attempt > 1:
            retry_user = user + "\n\n（⚠️ 上次你的回答格式不符合要求，请严格按上述格式输出，不要添加任何解释、序号、前缀或额外文字。只输出答案本身。）"

        # --- 主模型 ---
        start = time.time()
        result = await call_ollama_chat(system, retry_user, model, timeout=60)

        duration = int((time.time() - start) * 1000)
        logger.debug(f"{step_name} 主模型: success={result['success']}, duration={duration}ms, model={result.get('model','')}")

        # 1. 主模型成功
        if result["success"] and result["data"] is not None:
            await _report_success()
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
                await _report_success()
                if task:
                    task.add_step(name=step_name, status="done",
                                 duration_ms=int((time.time() - total_start) * 1000),
                                 model=result2.get("model", ""), error="")
                return result2["data"]

        # 3. 都失败了
        last_error = result.get("error", "") or (result2.get("error", "") if result2 else "")
        if attempt < config.PIPELINE_MAX_RETRIES:
            logger.warning(f"{step_name}: 第{attempt}次失败，2s后重试")
            if task:
                task.update("inference", f"({step_idx}/{total}) {step_name} 失败，2s后重试...")
            await asyncio.sleep(2)

    # 所有重试都失败
    await _report_failure()
    logger.error(f"{step_name}: 全部{config.PIPELINE_MAX_RETRIES}次重试失败: {last_error}")
    if task:
        task.add_step(name=step_name, status="failed",
                     duration_ms=int((time.time() - total_start) * 1000),
                     model=config.OLLAMA_MODEL, error=last_error)
    return None


async def run_daily_pipeline(chat_text: str, group_name: str,
                              date: str, msg_count: int, task=None,
                              hourly_stats: str = "",
                              is_private: bool = False,
                              primary_model: str = "") -> dict:
    """执行 8 步子任务管道，拼装每日报告 JSON（含趣味功能）

    is_private: 私聊模式，将 prompt 中的"群聊"替换为"聊天"、"群友"替换为"对方"
    primary_model: 指定主模型名（空则使用 config.OLLAMA_MODEL）
    """
    total = 8
    p_model = primary_model or config.OLLAMA_MODEL

    if task:
        task.model_used = p_model  # v0.12.4: 入口即设，进度面板可持续显示
        task.update("inference", f"(0/6) 开始分析...")
        task.steps.clear()


    failed_steps = []

    # 私聊模式：适配 prompt 话术
    def _p(key):
        """获取 prompt dict，私聊时自动替换群聊话术"""
        prompt = PROMPTS[key]
        if not is_private:
            return prompt
        # prompt 是 {"system": ..., "user": ...} dict
        return {k: _adapt_for_private(v) for k, v in prompt.items()}

    # 1. 话题（每行一个）
    if _is_cancelled(task): return {}
    topics_data = await _run_sub(task, "🔍 挖掘今日话题", 1, total,
                                  _p("topics")["system"],
                                  f"{chat_text}\n\n{_p('topics')['user']}",
                                  model=p_model)
    topics = _parse_lines(topics_data) if topics_data else []
    if not topics:
        topics = ["今日话题"]
        failed_steps.append("topics")

    # 2. 搞笑发言（发言人|原话|吐槽）
    if _is_cancelled(task): return {}
    quotes_data = await _run_sub(task, "😂 捕捉名场面", 2, total,
                                  _p("quotes")["system"],
                                  f"{chat_text}\n\n{_p('quotes')['user']}",
                                  model=p_model)
    quotes = _parse_quotes(quotes_data) if quotes_data else []
    if not quotes and quotes_data is None:
        failed_steps.append("quotes")

    # 3. 情绪（一个词）
    if _is_cancelled(task): return {}
    mood_data = await _run_sub(task, "🎭 感知群聊情绪", 3, total,
                                _p("mood")["system"],
                                f"{chat_text}\n\n{_p('mood')['user']}",
                                model=p_model)
    mood, mood_emoji = _parse_mood(mood_data)
    if mood_data is None:
        failed_steps.append("mood")

    # 4. 关键词（逗号分隔）
    if _is_cancelled(task): return {}
    kw_data = await _run_sub(task, "🏷️ 提取热词", 4, total,
                              _p("keywords")["system"],
                              f"{chat_text}\n\n{_p('keywords')['user']}",
                              model=p_model)
    keywords = _parse_kw(kw_data)
    if kw_data is None:
        failed_steps.append("keywords")

    # 5. 一句话总结（两行：总结+高光）
    if _is_cancelled(task): return {}
    ol_data = await _run_sub(task, "✍️ 写一句话总结", 5, total,
                              _p("oneline")["system"],
                              f"{chat_text}\n\n{_p('oneline')['user']}",
                              model=p_model)
    one_line, highlight = _parse_oneline(ol_data)
    if ol_data is None:
        failed_steps.append("oneline")

    # 6. 活跃时段（一句话描述）
    if _is_cancelled(task): return {}
    hs = (hourly_stats or "(无小时分布数据)").replace("{", "{{").replace("}", "}}")
    hs_user = PROMPTS["active_hours"]["user"].replace("{hourly_stats}", hs)
    ah_data = await _run_sub(task, "⏰ 分析活跃时段", 6, total,
                              _p("active_hours")["system"], hs_user,
                              model=p_model)
    ah = _parse_active_hours(ah_data)
    if ah_data is None:
        failed_steps.append("active_hours")

    # 7. 趣味标题（UC震惊体/综艺预告片风）
    if _is_cancelled(task): return {}
    headline_data = await _run_sub(task, "📺 编导起标题", 7, total,
                                    _p("headline")["system"],
                                    f"{chat_text}\n\n{_p('headline')['user']}",
                                    model=p_model)
    headline = str(headline_data).strip() if headline_data else ""
    if headline_data is None:
        failed_steps.append("headline")

    # 8. 名场面（取最佳搞笑发言，AI配花字吐槽）
    scene_commentary = ""
    if quotes and len(quotes) > 0:
        best_quote = quotes[0]
        scene_text = f"{best_quote.get('speaker','某人')}：「{best_quote.get('quote','')}」"
        sc = _p("scene_commentary")
        scene_user = sc["user"].format(scene=scene_text)
        scene_data = await _run_sub(task, "🎙️ 花字吐槽", 8, total,
                                     sc["system"], scene_user,
                                     model=p_model)
        scene_commentary = str(scene_data).strip() if scene_data else ""
        if scene_data is None:
            failed_steps.append("scene_commentary")

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


# ---- 在线模型单次调用日报 v0.12.0 ----

DAILY_ONLINE_SYSTEM = """你是一个群聊观察员，负责生成群聊日报。严格按JSON格式输出，不要输出任何其他内容。"""

DAILY_ONLINE_USER = """分析以下群聊记录，生成一份完整的日报JSON。

{chat}

输出JSON格式（严格按此结构，不要输出任何解释）：
{{
  "topic_summary": ["话题1", "话题2", "话题3"],
  "funny_quotes": [
    {{"speaker": "发言人", "quote": "原话", "comment": "你的犀利吐槽"}}
  ],
  "mood": "欢乐/温馨/严肃/吐槽/平淡/热闹/伤感/沙雕/吃瓜/摸鱼/摆烂/内卷/破防/离谱/上头 (选一个)",
  "mood_emoji": "对应emoji",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4"],
  "one_line": "20字内有梗的一句话总结",
  "highlight": "今天最值得记录的瞬间",
  "active_hours": {{"peak_label": "如 晚间热闹", "peak_desc": "一句话描述活跃规律"}},
  "headline": "综艺预告片风格的趣味标题（15字内）",
  "scene_commentary": "对最搞笑的名场面配一句花字吐槽（10字内）"
}}

话题提取2-4个，搞笑发言找3-5条，情绪严格从选项中选择。"""


async def run_daily_pipeline_online(
    chat_text: str,
    group_name: str,
    date: str,
    msg_count: int,
    model_config: dict,
    task=None,
    hourly_stats: str = "",
    is_private: bool = False,
    group_id: int = 0,
) -> dict:
    """在线模型单次调用日报管线 v0.12.0

    将 8 个子任务合并为一个 JSON prompt，一次性输出完整日报。
    利用在线模型的大上下文和强指令跟随能力，跳过拆分重试。
    失败时自动降级到本地 8 子任务管线。

    Returns:
        与 run_daily_pipeline() 相同结构的 dict
    """
    from services.online_model import call_online_chat
    from services.model_config import get_effective_model
    import asyncio

    mname = model_config.get("model_name") or ""
    if task:
        task.update("inference", f"🎬 {mname or '在线模型'} 正在解读今日群聊...")

    # 适配私聊话术
    chat_for_prompt = _adapt_for_private(chat_text) if is_private else chat_text

    # 构建 prompt
    hs = (hourly_stats or "(无小时分布数据)")
    full_chat = chat_for_prompt + f"\n\n小时消息分布：\n{hs}"
    user_prompt = DAILY_ONLINE_USER.format(chat=full_chat)

    # v1.18.3: 注入梗百科
    if group_id:
        from services.desensitize import build_meme_prefix
        mp = build_meme_prefix(group_id)
        if mp:
            user_prompt = mp + "\n" + user_prompt

    logger.info(f"在线模型日报: {group_name} {date}, 模型={model_config.get('model_name')}")

    try:
        result = await call_online_chat(
            system_prompt=get_default_prompt("daily") or DAILY_ONLINE_SYSTEM,
            user_prompt=user_prompt,
            model_config=model_config,
            temperature=0.3,
            json_mode=True,
            max_tokens=4096,
            pipeline="daily", group_id=group_id,
        )

        if result["success"] and result["data"]:
            # 解析 JSON
            data = _extract_json_from_text(result["data"])
            if data and isinstance(data, dict):
                # 用现有解析函数做安全网格式化
                report = _normalize_online_report(data)
                if task:
                    task.model_used = result.get("model", mname)
                    task.clear_fallback()  # v1.0.1: 在线模型恢复，清除降级标记
                    if task.type not in ("analyze_all", "full_portrait", "analyze_all_portraits"):
                        task.finish(success=True)
                    _save_pipeline_record(task, group_name, date)
                return report
            else:
                logger.warning("在线模型日报 JSON 解析失败，降级到本地管线")
        else:
            logger.warning(f"在线模型日报调用失败: {result.get('error')}，降级到本地管线")

    except Exception as e:
        logger.error(f"在线模型日报异常: {e}，降级到本地管线")

    # 降级：使用本地 8 子任务管线
    if not config.LOCAL_LLM_ENABLED:
        logger.warning(f"在线模型日报失败但本地模型已禁用，跳过降级: {group_name} {date}")
        if task:
            task.finish(success=False, error={"type": "no_fallback",
                "detail": "在线模型不可用且本地模型已禁用，请在高级设置中开启本地大模型"})
        return {"error": "在线模型不可用且本地模型已禁用"}
    logger.warning(f"降级到本地管线为 {group_name} {date} 生成日报")
    if task:
        task.update("inference", "⚠️ 在线模型未能响应，切换本地模型接力...", fallback=True)
    try:
        local_config = get_effective_model("local")
        return await run_daily_pipeline(
            chat_text=chat_text,
            group_name=group_name,
            date=date,
            msg_count=msg_count,
            task=task,
            hourly_stats=hourly_stats,
            is_private=is_private,
            primary_model=local_config.get("model_name", ""),
        )
    except Exception as e2:
        logger.error(f"本地管线降级也失败: {e2}")
        if task:
            task.finish(success=False, error={"type": "pipeline_failed", "detail": str(e2)})
        return {}


def _extract_json_from_text(text: str) -> dict | None:
    """从 AI 返回的文本中提取 JSON 对象"""
    # 先尝试直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 尝试找第一个 { ... } 块
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _normalize_online_report(data: dict) -> dict:
    """将在线模型 JSON 输出归一化为与 8 子任务管线相同的结构"""
    # 情绪
    mood, mood_emoji = _parse_mood(data.get("mood", ""))
    if not mood:
        mood = "平淡"
        mood_emoji = "😐"

    # 话题
    topics = data.get("topic_summary", [])
    if isinstance(topics, str):
        topics = _parse_lines(topics)
    if not topics:
        topics = ["今日话题"]

    # 搞笑发言
    quotes = data.get("funny_quotes", [])
    if isinstance(quotes, str):
        quotes = _parse_quotes(quotes)
    # 确保是 list[dict] 格式
    if quotes and isinstance(quotes, list):
        normalized_quotes = []
        for q in quotes:
            if isinstance(q, dict):
                normalized_quotes.append({
                    "speaker": q.get("speaker", q.get("发言人", "某人")),
                    "quote": q.get("quote", q.get("原话", "")),
                    "comment": q.get("comment", q.get("吐槽", "")),
                })
            elif isinstance(q, str):
                normalized_quotes.append({"speaker": "某人", "quote": q, "comment": ""})
        quotes = normalized_quotes

    # 关键词
    keywords = data.get("keywords", [])
    if isinstance(keywords, str):
        keywords = _parse_kw(keywords)
    if not keywords:
        keywords = ["聊天"]

    # 一句话总结
    one_line = data.get("one_line", "")
    highlight = data.get("highlight", "")
    if not one_line or not highlight:
        ol, hl = _parse_oneline(f"{one_line}\n{highlight}")
        one_line = ol or one_line or "今天又是热闹的一天"
        highlight = hl or highlight or "暂无高光"

    # 活跃时段
    ah = data.get("active_hours", {})
    if isinstance(ah, str):
        ah = _parse_active_hours(ah)
    if not isinstance(ah, dict):
        ah = {"peak_label": "全天活跃", "peak_desc": "消息分布均匀"}

    # 标题
    headline = data.get("headline", "") or one_line

    # 名场面吐槽
    scene = data.get("scene_commentary", "")

    report = {
        "topic_summary": topics,
        "funny_quotes": quotes,
        "mood": mood,
        "mood_emoji": mood_emoji,
        "highlight": highlight,
        "keywords": keywords,
        "one_line": one_line,
        "active_hours": ah,
        "headline": headline,
        "scene_commentary": scene,
    }
    return report


async def run_portrait_pipeline(chat_text: str, sender_name: str,
                                 group_name: str, msg_count: int,
                                 task=None, is_private: bool = False) -> dict:
    """执行 4 步子任务管道，拼装画像 JSON

    is_private: 私聊模式，将 prompt 中的"群聊"替换为"聊天"、"群友"替换为"对方"
    """
    total = 4

    if task:
        task.update("inference", f"(0/4) 分析 {sender_name}...")
        if task.type != "full_portrait":
            task.steps.clear()  # 统一分析时不重置，追加到已有步骤

    # 私聊模式：适配 prompt 话术
    def _pp(key):
        """获取 PORTRAIT_PROMPTS dict，私聊时自动替换群聊话术"""
        prompt = PORTRAIT_PROMPTS[key]
        if not is_private:
            return prompt
        return {k: _adapt_for_private(v) for k, v in prompt.items()}

    prompt_user = f"{chat_text}\n\n以上是 {sender_name} 的发言。"
    role_opts = "气氛组/和事佬/话题制造机/话题终结者/吃瓜群众/潜水大佬/毒舌评论员/科普达人/摸鱼冠军/卷王/凡尔赛大师/画饼专家/真香选手/社死担当/开车司机/破防boy/摆烂王者"
    failed_steps = []

    if task:
        task.model_used = config.OLLAMA_MODEL  # v0.12.4: 入口即设

    # 1. 性格+角色（三行文本）
    if _is_cancelled(task): return {}
    p_data = await _run_sub(task, "🧠 分析性格角色", 1, total,
                             _pp("persona")["system"],
                             f"{prompt_user}{_pp('persona')['user'].replace('{name}', sender_name)}")
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
    i_data = await _run_sub(task, "🎯 挖掘兴趣爱好", 2, total,
                             _pp("interests")["system"],
                             f"{prompt_user}{_pp('interests')['user'].replace('{name}', sender_name)}")
    i_lines = _parse_lines(i_data)
    interests = [t.strip() for t in i_lines[0].replace("，",",").split(",")] if len(i_lines) > 0 else []
    active_hours = i_lines[1] if len(i_lines) > 1 else ""
    if i_data is None:
        failed_steps.append("interests")

    # 3. 口头禅（v0.6.4: 支持多条，逗号分隔）
    ph_data = await _run_sub(task, "💬 检测口头禅", 3, total,
                              _pp("phrase")["system"],
                              f"{prompt_user}{_pp('phrase')['user'].replace('{name}', sender_name)}")
    ph_text = str(ph_data or "").strip()
    if "无" in ph_text or not ph_text or _is_ai_apology(ph_text):
        signature_phrases = []
    else:
        # 逗号或顿号分隔，每条最多 20 字，最多 3 条
        ph_list = re.split(r"[,，、]+", ph_text)
        signature_phrases = [p.strip()[:20] for p in ph_list if p.strip()][:3]
    if ph_data is None:
        failed_steps.append("phrase")

    # 4. 一句话+emoji（两行文本）
    # v0.6.4: AI 输出标签词 → Python 查表转 emoji，比数字编号更鲁棒
    ol_data = None
    one_line = ""
    emoji_style = ""  # 空字符串表示待填充，调用方可传入 stats 兜底
    ol_prompt_user = f"{prompt_user}{_pp('oneline_portrait')['user'].replace('{name}', sender_name)}"
    for ol_attempt in range(2):
        ol_data = await _run_sub(task, "🖼️ 素描人设", 4, total,
                                  _pp("oneline_portrait")["system"],
                                  ol_prompt_user)
        # 用 _parse_lines 提取第一行（人设描述）
        ol_lines = _parse_lines(ol_data)
        one_line = ol_lines[0] if len(ol_lines) > 0 else ""
        # 放宽校验：2-25 字，减少误杀
        if len(one_line) < 2 or len(one_line) > 25:
            one_line = ""

        # 从原始 AI 输出中提取第二行标签（不用 _parse_lines，因为它会 strip 掉数字/中文）
        raw_text = str(ol_data).strip() if ol_data else ""
        raw_lines = raw_text.split("\n")
        emoji_raw = raw_lines[1].strip() if len(raw_lines) > 1 else ""
        emoji_raw = re.sub(r'^第[一二三四五六七八九十\d]+[行行][：:]\s*', '', emoji_raw)
        emoji_raw = emoji_raw.strip()

        # 尝试匹配标签 → emoji
        emoji_style = _match_emoji_by_label(emoji_raw)
        if emoji_style:
            # emoji 匹配成功，但 one_line 可能仍然为空 → 重试 one_line
            if not one_line and ol_attempt == 0:
                ol_prompt_user = ol_prompt_user + (
                    f"\n\n（⚠️ 上次你的第一行描述\"{ol_lines[0][:30] if ol_lines else ''}\"格式不对。"
                    f"请输出 8-18 字的一句话描述，不要超出。）"
                )
                continue
            break

        # 兼容旧版：AI 输出了纯数字编号
        if emoji_raw in EMOJI_CHOICES:
            emoji_style = EMOJI_CHOICES[emoji_raw]
            if not one_line and ol_attempt == 0:
                ol_prompt_user = ol_prompt_user + "\n\n（⚠️ 第一行描述格式不对，请输出 8-18 字。）"
                continue
            break

        # 不合法：标签未匹配 + 不是有效编号 → 重试
        if ol_attempt == 0:
            retry_hint = "（⚠️ 上次你第二行输出了\"" + emoji_raw[:30] + "\"，不是有效标签。请只复制上述列表中的一个标签词，如\"乐天派\"、\"夜猫子\"。）"
            if not one_line:
                retry_hint += "\n（同时第一行描述请控制在 8-18 字。）"
            ol_prompt_user = ol_prompt_user + "\n\n" + retry_hint
            continue
        else:
            emoji_style = ""
            break

    if ol_data is None:
        failed_steps.append("oneline_portrait")

    # v0.6.4: one_line 兜底 — 从已有数据拼一个，避免展示"——"
    if not one_line:
        role = role or ""
        pers = personality[:2] if personality else []
        if role and pers:
            one_line = f"一个{pers[0]}的{role}"
        elif pers:
            one_line = f"一个{pers[0]}的{'聊天对象' if is_private else '群友'}"
        elif role:
            one_line = f"{'聊天中的' if is_private else '群里的'}{role}"

    # 拼装
    portrait = {
        "personality": personality[:3],
        "speaking_style": speaking_style,
        "role": role,
        "interests": interests[:5],
        "active_hours": active_hours,
        "signature_phrase": signature_phrases[0] if signature_phrases else None,  # 向后兼容
        "signature_phrases": signature_phrases,  # v0.6.4: 多条口头禅
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


# ---- 在线模型单次调用画像 v0.12.2 ----

PORTRAIT_ONLINE_SYSTEM = """你是一个群聊人物画像分析师。根据发言记录生成一份完整的成员画像JSON。严格按JSON格式输出，不要输出任何其他内容。"""

PORTRAIT_ONLINE_USER = """分析成员 {name} 的发言，生成完整画像JSON。

{chat}

输出JSON格式（严格按此结构）：
{{
  "personality": ["标签1", "标签2", "标签3"],
  "speaking_style": "一个词的说话风格",
  "role": "群内角色",
  "interests": ["兴趣1", "兴趣2", "兴趣3"],
  "active_hours": "活跃时段描述，如 夜猫子22:00-02:00",
  "signature_phrases": ["口头禅1", "口头禅2"],
  "one_line": "8-18字人设描述",
  "emoji_label": "标签词（从下面的列表选一个）",
  "emotion_summary": "一句话情绪特征总结",
  "language_notes": "2-3句话的语言风格描述",
  "deep_insight": "一段话的深度分析：这个人的变化趋势、隐藏特质、在群里的独特价值"
}}

性格标签参考（可自由发挥）：较真 随和 社恐 自来熟 刀子嘴 老好人 玻璃心 佛系 急性子 细节控 强迫症 摆烂王 卷王 乐子人 吃货 愤青 文艺

说话风格参考：豪爽 温柔 毒舌 理性 活泼 老成 阴阳怪气 一本正经 骚话连篇 惜字如金 直球 拐弯抹角

群内角色参考：气氛组 和事佬 话题制造机 话题终结者 吃瓜群众 潜水大佬 毒舌评论员 科普达人 摸鱼冠军 卷王

emoji标签参考：乐天派 整活王 暖心 暴脾气 老学究 派对咖 emo怪 沙雕 吃瓜群众 摸鱼达人 摆烂王 卷王 老司机 玻璃心 凡尔赛 社死选手 夜猫子 游戏宅 美食家 潜水冠军 捧场王 毒舌 话痨 文艺青年

注意：根据发言判断性别，不要用性别错位的称呼。deep_insight 要有洞察力，不要泛泛而谈。"""


async def run_portrait_pipeline_online(
    chat_text: str,
    sender_name: str,
    group_name: str,
    msg_count: int,
    model_config: dict,
    task=None,
    is_private: bool = False,
) -> dict:
    """在线模型单次调用画像管线 v0.12.2

    将基础画像 4 个子任务 + 深度分析合并为一个 JSON prompt，一次性输出完整画像。
    利用在线模型的大上下文和强推理能力，跳过拆分重试。
    失败时自动降级到本地 4 步子任务管线。

    Returns:
        与 run_portrait_pipeline() 相同结构的 dict，额外含 emotion_summary/language_notes/deep_insight
    """
    from services.online_model import call_online_chat
    from services.model_config import get_effective_model

    mname = model_config.get("model_name") or ""
    if task:
        task.update("inference", f"🎨 {mname or '在线模型'} 正在描绘 {sender_name} 的群聊人格...")

    # 私聊模式适配
    chat_for_prompt = _adapt_for_private(chat_text) if is_private else chat_text
    user_prompt = PORTRAIT_ONLINE_USER.format(name=sender_name, chat=chat_for_prompt)

    logger.info(f"在线模型画像: {sender_name}, 模型={model_config.get('model_name')}")

    try:
        result = await call_online_chat(
            system_prompt=get_default_prompt("portrait") or PORTRAIT_ONLINE_SYSTEM,
            user_prompt=user_prompt,
            model_config=model_config,
            temperature=0.4,
            json_mode=True, pipeline="portrait",
            max_tokens=4096,
        )

        if result["success"] and result["data"]:
            data = _extract_json_from_text(result["data"])
            if data and isinstance(data, dict):
                portrait = _normalize_online_portrait(data, sender_name, is_private)
                if task:
                    task.model_used = result.get("model", mname)
                    task.clear_fallback()  # v1.0.1: 在线模型恢复，清除降级标记
                return portrait
            else:
                logger.warning(f"在线模型画像 JSON 解析失败，降级到本地管线")
        else:
            logger.warning(f"在线模型画像调用失败: {result.get('error')}，降级到本地管线")

    except Exception as e:
        logger.error(f"在线模型画像异常: {e}，降级到本地管线")

    # 降级：使用本地 4 步子任务管线
    if not config.LOCAL_LLM_ENABLED:
        logger.warning(f"在线模型画像失败但本地模型已禁用，跳过降级: {sender_name}")
        if task:
            task.finish(success=False, error={"type": "no_fallback",
                "detail": "在线模型不可用且本地模型已禁用，请在高级设置中开启本地大模型"})
        return {"error": "在线模型不可用且本地模型已禁用"}
    logger.warning(f"降级到本地管线为 {sender_name} 生成画像")
    if task:
        task.update("inference", f"⚠️ 在线模型未能响应，切换本地模型继续描绘 {sender_name}...", fallback=True)
    try:
        return await run_portrait_pipeline(
            chat_text=chat_text,
            sender_name=sender_name,
            group_name=group_name,
            msg_count=msg_count,
            task=task,
            is_private=is_private,
        )
    except Exception as e2:
        logger.error(f"本地管线降级也失败: {e2}")
        return {}


def _normalize_online_portrait(data: dict, sender_name: str, is_private: bool = False) -> dict:
    """将在线模型 JSON 输出归一化为与本地管线兼容的结构，并附加深度字段"""
    # 基础字段归一化
    personality = data.get("personality", [])
    if isinstance(personality, str):
        personality = [t.strip() for t in personality.replace("，", ",").split(",")]
    personality = [p for p in personality if p][:3]

    speaking_style = str(data.get("speaking_style", ""))[:20]

    role = str(data.get("role", ""))[:20]

    interests = data.get("interests", [])
    if isinstance(interests, str):
        interests = [t.strip() for t in interests.replace("，", ",").split(",")]
    interests = [i for i in interests if i][:5]

    active_hours = str(data.get("active_hours", ""))[:50]

    sig = data.get("signature_phrases", [])
    if isinstance(sig, str):
        sig = [t.strip() for t in sig.replace("，", ",").split(",")]
    signature_phrases = [s[:20] for s in sig if s and s != "无"][:3]

    one_line = str(data.get("one_line", ""))[:30]
    if not one_line or len(one_line) < 2:
        parts = []
        if personality:
            parts.append(personality[0])
        if role:
            parts.append(role)
        one_line = f"一个{'·'.join(parts)}" if parts else f"{'聊天中的' if is_private else '群里的'}神秘人"

    # emoji 匹配
    emoji_label = data.get("emoji_label") or ""
    emoji_style = _match_emoji_by_label(emoji_label) if emoji_label else ""

    portrait = {
        "personality": personality,
        "speaking_style": speaking_style,
        "role": role,
        "interests": interests,
        "active_hours": active_hours,
        "signature_phrase": signature_phrases[0] if signature_phrases else None,
        "signature_phrases": signature_phrases,
        "one_line": one_line[:30],
        "emoji_style": emoji_style[:10],
        # v0.12.2: 在线模型额外深度字段
        "emotion_summary": str(data.get("emotion_summary", ""))[:200],
        "language_notes": str(data.get("language_notes", ""))[:300],
        "deep_insight": str(data.get("deep_insight", ""))[:500],
    }
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

    # ---- 1. 月度切片分析（先收集数据，后续情绪分析依赖这些数据） ----
    if _is_cancelled(task): return {}
    from services.parser import ParsedChat
    monthly_chunks = chunk_messages_by_month(messages, lambda sid: sender_name, max_chars_per_chunk=3000)

    monthly_analyses = []
    if monthly_chunks and task:
        task.update("inference", f"月度切片分析 (0/{len(monthly_chunks)})...")

    for i, (month_label, chunk) in enumerate(monthly_chunks):
        if _is_cancelled(task): break
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
            {"date": ma["month"], "mood": ma["mood"],
             "mood_emoji": MOOD_MAP.get(ma["mood"], "😐")}
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
    """持久化任务记录到数据库（v1.3.0: 批量任务子步骤状态修正）"""
    try:
        failed_steps = [s for s in task.steps if s["status"] == "failed"]
        model = task.model_used or config.OLLAMA_MODEL
        # v1.3.0: 批量任务（analyze_all/full_portrait 等）外层控制 finish，
        # 子步骤调用时 task.status 仍为 "inference"，需修正为 "done"
        batch_types = ("analyze_all", "full_portrait", "analyze_all_portraits",
                       "portrait_all", "generate_all_weekly", "generate_all_monthly")
        if task.type in batch_types:
            status = "failed" if failed_steps else "done"
        else:
            status = "failed" if failed_steps else task.status
        save_task_record(
            task_id=task.task_id,
            group_id=task.group_id,
            task_type=task.type,
            target=f"{group_name}/{target}",
            status=status,
            total_duration_ms=task.duration_ms,
            model_used=model,
            steps_json=json.dumps(task.steps, ensure_ascii=False),
            error_summary="; ".join(f"{s['name']}:{s['error']}" for s in failed_steps) if failed_steps else "",
        )
    except Exception as e:
        logger.warning(f"保存任务记录失败: {e}")
