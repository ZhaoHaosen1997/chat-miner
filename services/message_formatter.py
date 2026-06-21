"""
v1.19.0 共享消息格式化层 — 所有管线统一入口

替代各管线分散的消息→Prompt 格式化逻辑，统一处理：
- 无意义内容过滤（_has_meaningful_content）
- 游戏指令过滤（is_game_command）
- PII 脱敏（filter_pii）
- @提及剥离（strip_mention）
- 发送人匿名化（stable_id）
- 上下文截断（按 model token limit）
"""
import re
from services.desensitize import filter_pii, build_wxid_to_stable_id
from services.parser import _has_meaningful_content, is_game_command, strip_mention_from_content, get_model_token_limit


def format_messages_for_ai(
    messages: list[dict],
    *,
    max_chars: int = 50000,
    model: str = "",
    # 发送人选项
    include_sender: bool = True,
    use_stable_id: bool = True,
    senders: list[dict] | None = None,
    # 时间选项
    include_time: bool = True,
    time_format: str = "HH:MM",
    # 内容过滤
    member_names: set[str] | None = None,
    filter_content: bool = True,
    filter_game_cmds: bool = True,
    filter_pii_content: bool = True,
    # 头部
    header: str | None = None,
) -> str:
    """将消息列表格式化为 AI Prompt 文本

    Args:
        messages: 消息列表
        max_chars: 最大字符数限制
        model: 模型名，用于根据上下文窗口动态调整截断阈值
        include_sender: 是否输出发送人标识（画像为 False）
        use_stable_id: 是否用 stable_id 脱敏（画像为 False）
        senders: sender 列表，用于构建 stable_id 映射
        include_time: 是否输出时间
        time_format: 时间格式 "HH:MM" 或 "YYYY-MM-DD HH:MM"
        member_names: 群成员名字集合（用于剥离 @mention）
        filter_content: 是否过滤无意义内容
        filter_game_cmds: 是否过滤 / 开头的游戏指令
        filter_pii_content: 是否 PII 脱敏
        header: 可选的头部行（如 "xxx 的发言记录："）
    """
    # Token limit adjustment
    if model:
        token_limit = get_model_token_limit(model)
        effective_token_limit = int(token_limit * 0.7)
        char_limit = int(effective_token_limit / 1.5)
        max_chars = min(max_chars, char_limit)

    # Stable ID mapping
    if include_sender and use_stable_id and senders:
        wxid_to_stable = build_wxid_to_stable_id(senders)
    else:
        wxid_to_stable = None

    lines = []
    if header:
        lines.append(header)
        lines.append("---")

    total = sum(len(l) + 1 for l in lines)  # +1 for \n
    truncated = False

    for msg in messages:
        # 跳过引用消息（content 是被引用者原文，sender 却是引用者 → 张冠李戴）
        if msg.get("type") == "引用消息":
            continue

        # 内容提取
        raw_content = (msg.get("content") or "").strip()
        if not raw_content:
            continue

        # 游戏指令过滤
        if filter_game_cmds and is_game_command(raw_content):
            continue

        # @mention 剥离
        content = strip_mention_from_content(raw_content, member_names) if member_names else raw_content

        # 无意义内容过滤
        if filter_content and (not content or not _has_meaningful_content(content)):
            continue

        # PII 脱敏
        if filter_pii_content:
            content = filter_pii(content)

        # 构建行
        parts = []
        if include_time:
            ft = msg.get("formattedTime", "")
            if time_format == "HH:MM":
                parts.append(f"[{ft[11:16]}]")
            else:
                parts.append(f"[{ft[:16]}]")

        if include_sender:
            wxid = msg.get("wxid", "")
            sender = str(wxid_to_stable.get(wxid, msg.get("senderID", 0))) if wxid_to_stable else str(msg.get("senderID", 0))
            parts.append(f"[{sender}]:")

        parts.append(content)
        line = " ".join(parts)

        total += len(line) + 1  # +1 for \n
        if total > max_chars:
            truncated = True
            break
        lines.append(line)

    result = "\n".join(lines)
    if truncated:
        result += f"\n\n... (消息过多，已截断至 {len(lines) - (1 if header else 0)} 条)"
    return result
