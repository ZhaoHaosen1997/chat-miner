"""
社交关系分析服务
两步走：Python 统计互动频次 + AI 判断关系类型
"""
import logging
from typing import Optional

from services.parser import extract_interaction_context
from services.stats_engine import compute_social_relations
from services.analyzer import call_ollama_chat
from config import config

logger = logging.getLogger(__name__)

RELATION_JUDGE_PROMPT = {
    "system": "你是一个人际关系分析工具。基于两人的聊天互动片段，判断他们的关系类型。只输出一个词。",
    "user": """以下两段聊天记录，展示了 {name_a} 和 {name_b} 的互动片段。

片段1（{name_a}的视角）：
{context}

请判断 {name_a} 和 {name_b} 之间的关系类型。只输出一个词，从以下选择：
损友 同事 好友 普通群友 网友 领导与下属 亲密朋友 游戏搭子 饭搭子 奶茶搭子 深夜聊天搭子 互怼组合 捧哏逗哏 冤家 塑料姐妹 亲兄弟

你的输出：""",
}


async def ai_judge_relation(name_a: str, name_b: str,
                             context: str, model: str = "",
                             model_config: dict | None = None) -> Optional[str]:
    """AI 判断两人的关系类型

    Args:
        name_a: 目标成员名
        name_b: 对方名
        context: 互动上下文文本（已截断至 1000 字）
        model: 模型名
        model_config: v0.12.5 在线模型配置，优先于 model

    Returns:
        关系类型标签（如"损友"），失败返回 None
    """
    if not context or len(context) < 50:
        return None

    user_prompt = RELATION_JUDGE_PROMPT["user"].format(
        name_a=name_a, name_b=name_b, context=context
    )
    # 安全：输入已经过 extract_interaction_context 截断，再兜底
    if len(user_prompt) > 2000:
        user_prompt = user_prompt[:2000]

    if model_config and model_config.get("model_type") == "online" and model_config.get("api_key"):
        from services.online_model import call_online_chat
        result = await call_online_chat(
            RELATION_JUDGE_PROMPT["system"], user_prompt, model_config,
            temperature=0.3, max_tokens=20, timeout=15,
        )
    else:
        result = await call_ollama_chat(
            RELATION_JUDGE_PROMPT["system"],
            user_prompt,
            model=model or config.OLLAMA_MODEL,
            timeout=30,
        )

    if result["success"] and result["data"]:
        raw = str(result["data"]).strip()
        # 提取第一个匹配的类型
        valid_types = ["损友", "同事", "好友", "普通群友", "网友",
                       "饭搭子", "奶茶搭子", "深夜聊天搭子", "互怼组合",
                       "捧哏逗哏", "冤家", "塑料姐妹", "亲兄弟", "游戏搭子",
                       "领导与下属", "亲密朋友", "游戏搭子"]
        for t in valid_types:
            if t in raw:
                return t
        # 返回原始输出的前 10 字
        return raw[:10] if raw else None
    return None


async def analyze_social_relations(messages: list[dict],
                                    wxid: str,
                                    member_name: str,
                                    get_sender_name,
                                    get_name_by_wxid=None,
                                    model: str = "",
                                    model_config: dict | None = None) -> list[dict]:
    """分析成员的社交关系：Python 统计 + AI 判断

    Args:
        messages: 全部消息列表
        wxid: 目标成员 wxid
        member_name: 目标成员名
        get_sender_name: 兼容旧代码
        get_name_by_wxid: wxid → 名字 的映射函数
        model: 模型名
        model_config: v0.12.5 在线模型配置

    Returns:
        [{wxid, name, interaction_count, relation_type, note}] Top 5
    """
    # Step 1: Python 计算
    relations = compute_social_relations(messages, wxid, get_sender_name, get_name_by_wxid)

    if not relations:
        return []

    # Step 2: 对 Top 3 做 AI 关系判断
    top3 = relations[:3]
    for r in top3:
        context = extract_interaction_context(
            messages, wxid, r["wxid"], get_name_by_wxid or get_sender_name, max_chars=1000
        )
        if context:
            relation_type = await ai_judge_relation(
                member_name, r["name"], context, model, model_config=model_config
            )
            if relation_type:
                r["relation_type"] = relation_type
            else:
                r["relation_type"] = "普通群友"
        else:
            r["relation_type"] = "普通群友"

        if r["co_msg_count"] > 100:
            r["note"] = "互动频繁，经常同时在线"
        elif r["mention_count"] > 5:
            r["note"] = f"经常@对方（{r['mention_count']}次）"
        else:
            r["note"] = "偶尔互动"

    return top3
