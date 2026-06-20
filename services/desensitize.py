"""共享脱敏模块 — PII 过滤 + 敏感信息清洗

所有模块（日报、周报、月报、年报、事件分析）在发给 AI 前统一调用。
发送者身份通过 senderID 数字表示（非实名），本模块仅处理消息内容的敏感信息。
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
