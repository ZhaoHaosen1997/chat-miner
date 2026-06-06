"""
画像服务：群友画像生成
累积成员的发言，定期调用 AI 更新画像
"""
import logging
from typing import Optional

from models.database import (
    get_members, get_portrait, save_member_portrait, log_analysis,
    get_member_by_sender_id, get_analyzed_dates,
)
from services.analyzer import call_ollama_chat
from services.parser import format_sender_messages_for_portrait, ParsedChat
from prompts.portrait import PORTRAIT_SYSTEM, PORTRAIT_USER
from config import config

logger = logging.getLogger(__name__)


async def generate_single_portrait(
    group_id: int,
    group_name: str,
    sender_id: int,
    sender_name: str,
    chat: ParsedChat,
    model: str = "",
) -> dict:
    """为单个成员生成画像

    Args:
        group_id: 群 ID
        group_name: 群名
        sender_id: JSON 中的原始 senderID
        sender_name: 发言人名称
        chat: 解析后的聊天数据
        model: 模型名

    Returns:
        {"success": bool, "data": dict|None, ...}
    """
    # 收集该成员在所有已分析日期中的发言
    all_msgs = []
    analyzed_dates = get_analyzed_dates(group_id)

    for date in analyzed_dates:
        day_msgs = chat.get_text_messages_for_date(date)
        sender_day_msgs = [m for m in day_msgs if m.get("senderID") == sender_id]
        all_msgs.extend(sender_day_msgs)

    if len(all_msgs) < 5:
        return {
            "success": False,
            "data": None,
            "error": f"{sender_name} 的文本消息过少（{len(all_msgs)}条），不足以生成画像",
            "model": "",
            "duration_ms": 0,
        }

    # 格式化发言
    chat_text = format_sender_messages_for_portrait(all_msgs, sender_name)

    # 组装 prompt
    user_prompt = PORTRAIT_USER.format(
        sender_name=sender_name,
        group_name=group_name,
        msg_count=len(all_msgs),
        chat_text=chat_text,
    )

    logger.info(f"生成画像: {sender_name} ({len(all_msgs)} 条消息, {len(chat_text)} 字符)")
    result = await call_ollama_chat(PORTRAIT_SYSTEM, user_prompt, model)

    if not result["success"] and config.OLLAMA_MODEL_FALLBACK:
        result = await call_ollama_chat(PORTRAIT_SYSTEM, user_prompt,
                                         config.OLLAMA_MODEL_FALLBACK)

    return result


async def refresh_portraits(
    group_id: int,
    group_name: str,
    chat: ParsedChat,
    model: str = "",
    force: bool = False,
) -> list[dict]:
    """刷新群内所有需要更新的画像

    Args:
        group_id: 群 ID
        group_name: 群名
        chat: 解析后的聊天数据
        model: 模型名
        force: 是否强制刷新所有画像（忽略阈值）

    Returns:
        [{"member": dict, "portrait": dict, "refreshed": bool}, ...]
    """
    members = get_members(group_id)
    results = []

    for member in members:
        sender_id = member["sender_id"]
        sender_name = member["display_name"] or member["nickname"]

        # 检查是否需要刷新
        existing = get_portrait(group_id, member["id"])
        needs_refresh = force or (existing is None)

        if not needs_refresh and existing:
            # 检查累积新消息是否超过阈值
            new_msgs = member["message_count"] - existing.get("total_analyzed_messages", 0)
            if new_msgs >= config.PORTRAIT_REFRESH_DAYS * 50:
                needs_refresh = True

        if not needs_refresh:
            results.append({"member": member, "portrait": existing, "refreshed": False})
            continue

        # 生成/刷新画像
        result = await generate_single_portrait(
            group_id, group_name, sender_id, sender_name, chat, model
        )

        if result["success"] and result["data"]:
            import json
            portrait_json = json.dumps(result["data"], ensure_ascii=False)
            save_member_portrait(
                group_id=group_id,
                member_id=member["id"],
                display_name=sender_name,
                total_messages=member["message_count"],
                portrait_json=portrait_json,
            )
            log_analysis(group_id, "", "portrait", "success",
                        model=result["model"], duration_ms=result["duration_ms"])

            results.append({
                "member": member,
                "portrait": result["data"],
                "refreshed": True,
                "model": result["model"],
            })
        else:
            log_analysis(group_id, "", "portrait", "failed",
                        error_msg=result.get("error", ""))
            results.append({
                "member": member,
                "portrait": existing,
                "refreshed": False,
                "error": result.get("error", ""),
            })

    return results
