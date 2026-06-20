"""共享脱敏模块 — PII 过滤 + senderID↔昵称 还原

发送给 AI：senderID 数字（非实名）+ PII 过滤后的消息内容
AI 返回后：将 AI 输出中的 [senderID] 还原为昵称再存储

名称降级优先级：displayName → nickname → str(senderID)
"""

import re
import logging

logger = logging.getLogger(__name__)

# 敏感信息正则（隐私过滤）
# 注意：顺序很重要！更具体的模式必须放在前面，避免被宽泛模式误匹配
_PII_PATTERNS = [
    (re.compile(r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]'), '[身份证]'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[邮箱]'),
    (re.compile(r'1[3-9]\d{9}'), '[手机号]'),
    (re.compile(r'\d{3,4}-\d{7,8}'), '[电话号码]'),
]

# senderID → 昵称 替换正则
_SID_BRACKET = re.compile(r'\[(\d+)\]')   # [13]
_SID_HAO = re.compile(r'\b(\d+)号\b')      # 13号（中文语境常见）


def _resolve_all(text: str, name_map: dict[int, str]) -> str:
    """将文本中所有 [N]、N号 格式替换为昵称"""
    if not text or not name_map:
        return text

    def _by_bracket(match):
        sid = int(match.group(1))
        return name_map.get(sid, match.group(0))

    def _by_hao(match):
        sid = int(match.group(1))
        name = name_map.get(sid)
        return name if name else match.group(0)

    text = _SID_BRACKET.sub(_by_bracket, text)
    text = _SID_HAO.sub(_by_hao, text)
    return text


def filter_pii(content: str) -> str:
    """对单条消息内容做 PII 正则过滤"""
    if not content:
        return content
    for pattern, replacement in _PII_PATTERNS:
        content = pattern.sub(replacement, content)
    return content


def filter_pii_batch(messages: list[dict]) -> list[dict]:
    """批量过滤消息列表，原地修改 content 字段"""
    for m in messages:
        content = (m.get("content") or "").strip()
        if content:
            m["content"] = filter_pii(content)
    return messages


def build_sender_name_map(senders: list[dict]) -> dict[int, str]:
    """从 chat.senders 构建 {senderID: 显示名} 映射表

    降级优先级：displayName → nickname → str(senderID)
    """
    name_map = {}
    for s in senders:
        sid = s.get("senderID", 0)
        if sid:
            name = s.get("displayName", "") or s.get("nickname", "") or str(sid)
            name_map[sid] = name
    return name_map


def resolve_sender_ids(text: str, name_map: dict[int, str]) -> str:
    """将文本中的 [123]、123号 格式替换为对应昵称"""
    return _resolve_all(text, name_map)


def resolve_sender_ids_deep(data, name_map: dict[int, str]):
    """递归遍历 dict/list/str，将所有 senderID 引用替换为昵称

    用于 AI 输出的 JSON 结构（周报/月报/年报/事件分析）。
    同时处理 participant.name 中的裸数字。
    """
    if not name_map:
        return data
    if isinstance(data, str):
        return _resolve_all(data, name_map)
    if isinstance(data, dict):
        # 特殊处理：如果 key 是 "name" 且 value 是纯数字，直接映射
        if "name" in data and isinstance(data["name"], str):
            raw = data["name"].strip()
            # 纯数字如 "4"、"13"
            if raw.isdigit():
                sid = int(raw)
                data["name"] = name_map.get(sid, raw)
            else:
                data["name"] = _resolve_all(raw, name_map)
        return {k: resolve_sender_ids_deep(v, name_map) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_sender_ids_deep(item, name_map) for item in data]
    return data
