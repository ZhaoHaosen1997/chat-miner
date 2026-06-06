"""
消息解析模块：JSON 文件解析 + 按天分块 + 数据合并
处理微信聊天记录导出的 JSON 格式
"""
import json
import logging
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# 有文本内容的消息类型
TEXT_TYPES = {"文本消息", "引用消息", "视频消息"}
# 无文本但可统计的类型
STAT_TYPES = {"图片消息", "表情消息", "语音消息", "文件消息", "位置消息",
              "视频消息", "名片消息", "小程序消息", "系统消息", "聊天记录",
              "语音记录", "红包消息"}


class ParsedChat:
    """解析后的群聊数据"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.raw: dict = {}
        self.session: dict = {}
        self.senders: list[dict] = []
        self.messages: list[dict] = []
        self._by_date: Optional[dict[str, list[dict]]] = None

    def load(self):
        """加载并解析 JSON 文件"""
        logger.info(f"加载文件: {self.file_path} ({self.file_path.stat().st_size / 1024 / 1024:.1f} MB)")
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.raw = json.load(f)

        self.session = self.raw.get("session", {})
        self.senders = self.raw.get("senders", [])
        self.messages = self.raw.get("messages", [])

        # 按时间排序（确保顺序）
        self.messages.sort(key=lambda m: m.get("createTime", 0))

        logger.info(f"解析完成: 群={self.group_name}, 消息={len(self.messages)}, 成员={len(self.senders)}")
        return self

    @property
    def group_name(self) -> str:
        return self.session.get("nickname", "") or self.session.get("displayName", "")

    @property
    def group_wxid(self) -> str:
        return self.session.get("wxid", "")

    @property
    def message_count(self) -> int:
        return self.session.get("messageCount", len(self.messages))

    def get_date_range(self) -> tuple[str, str]:
        """返回数据的日期范围 (start, end)"""
        dates = [m.get("formattedTime", "")[:10] for m in self.messages if m.get("formattedTime")]
        if not dates:
            return ("", "")
        return (min(dates), max(dates))

    def chunk_by_date(self) -> dict[str, list[dict]]:
        """按天分块：将消息按 formattedTime 的日期分组"""
        if self._by_date is not None:
            return self._by_date

        chunks: dict[str, list[dict]] = defaultdict(list)
        for msg in self.messages:
            ft = msg.get("formattedTime", "")
            if ft:
                date = ft[:10]  # "2025-09-01"
                chunks[date].append(msg)

        self._by_date = dict(sorted(chunks.items()))
        return self._by_date

    def get_text_messages_for_date(self, date: str) -> list[dict]:
        """获取某天的文本消息（用于 AI 分析）"""
        day_msgs = self.chunk_by_date().get(date, [])
        return [m for m in day_msgs if m.get("type") in TEXT_TYPES and (m.get("content") or "").strip()]

    def get_sender_name(self, sender_id: int) -> str:
        """通过 senderID 获取显示名"""
        for s in self.senders:
            if s.get("senderID") == sender_id:
                return s.get("displayName", "") or s.get("nickname", "") or str(sender_id)
        return str(sender_id)

    def all_dates(self) -> list[str]:
        """返回所有有消息的日期，降序"""
        return sorted(self.chunk_by_date().keys(), reverse=True)

    def stats_for_date(self, date: str) -> dict:
        """某天的基本统计（纯 Python，不调 AI）"""
        day_msgs = self.chunk_by_date().get(date, [])
        text_msgs = [m for m in day_msgs if m.get("type") in TEXT_TYPES and (m.get("content") or "").strip()]
        senders_set = {m.get("senderID") for m in day_msgs}

        # 消息类型分布
        type_counts = defaultdict(int)
        for m in day_msgs:
            type_counts[m.get("type", "未知")] += 1

        # 活跃时段
        hour_counts = defaultdict(int)
        for m in day_msgs:
            ft = m.get("formattedTime", "")
            if len(ft) >= 13:
                hour = ft[11:13]
                hour_counts[hour] += 1

        return {
            "date": date,
            "total_messages": len(day_msgs),
            "text_messages": len(text_msgs),
            "active_members": len(senders_set),
            "type_distribution": dict(type_counts),
            "hourly_distribution": {h: hour_counts.get(h, 0) for h in
                                    [f"{i:02d}" for i in range(24)]},
        }

    def sender_message_counts(self) -> dict[int, int]:
        """每个发送者的消息总数"""
        from collections import Counter
        return Counter(m.get("senderID") for m in self.messages)

    def sender_text_counts(self) -> dict[int, int]:
        """每个发送者的文本消息数"""
        from collections import Counter
        return Counter(
            m.get("senderID") for m in self.messages
            if m.get("type") in TEXT_TYPES and (m.get("content") or "").strip()
        )


def load_and_parse(file_path: Path) -> ParsedChat:
    """便捷函数：加载并解析文件"""
    return ParsedChat(file_path).load()


def merge_chat_data(existing_messages: list[dict],
                     new_messages: list[dict]) -> dict:
    """合并新导入的消息到已有数据中

    按 platformMessageId 去重，只保留新增的消息。
    如果消息没有 platformMessageId（老格式），则按 (createTime, senderID, content) 去重。

    Args:
        existing_messages: 已有的消息列表
        new_messages: 新导入的消息列表

    Returns:
        {
            "added": [新消息列表],
            "skipped": 跳过的重复消息数,
            "total_new": 新 JSON 中的消息总数
        }
    """
    # 构建已有消息的去重索引
    seen_ids = set()
    seen_fingerprints = set()
    for m in existing_messages:
        pid = m.get("platformMessageId", "")
        if pid:
            seen_ids.add(pid)
        else:
            # 老格式：用 (createTime, senderID, content[:50]) 作为指纹
            fp = (m.get("createTime", 0), m.get("senderID", 0),
                  (m.get("content") or "")[:50])
            seen_fingerprints.add(fp)

    added = []
    skipped = 0
    for m in new_messages:
        pid = m.get("platformMessageId", "")
        if pid and pid in seen_ids:
            skipped += 1
            continue
        if not pid:
            fp = (m.get("createTime", 0), m.get("senderID", 0),
                  (m.get("content") or "")[:50])
            if fp in seen_fingerprints:
                skipped += 1
                continue
            seen_fingerprints.add(fp)
        else:
            seen_ids.add(pid)
        added.append(m)

    logger.info(f"合并结果: {len(new_messages)} 条新消息中, 新增 {len(added)} 条, 跳过 {skipped} 条重复")
    return {
        "added": added,
        "skipped": skipped,
        "total_new": len(new_messages),
    }


def format_messages_for_prompt(messages: list[dict],
                                get_sender_name,
                                max_chars: int = 50000) -> str:
    """将消息列表格式化为 AI prompt 的聊天记录文本

    Args:
        messages: 消息列表
        get_sender_name: 获取发言人名称的函数
        max_chars: 最大字符数限制（超过则截断并加提示）
    """
    lines = []
    total = 0
    truncated = False

    for msg in messages:
        time_str = msg.get("formattedTime", "")[11:16]  # "HH:MM"
        sender = get_sender_name(msg.get("senderID", 0))
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        line = f"[{time_str}] {sender}: {content}"
        total += len(line)
        if total > max_chars:
            truncated = True
            break
        lines.append(line)

    result = "\n".join(lines)
    if truncated:
        result += f"\n\n... (消息过多，已截断至 {len(lines)} 条)"
    return result


def format_sender_messages_for_portrait(messages: list[dict],
                                          sender_name: str,
                                          max_chars: int = 8000) -> str:
    """将某个成员的发言格式化为画像分析的 prompt"""
    lines = [f"{sender_name} 的发言记录：", "---"]
    total = 0
    truncated = False

    for msg in messages:
        time_str = msg.get("formattedTime", "")[:16]  # "2025-09-01 14:30"
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        line = f"[{time_str}] {content}"
        total += len(line)
        if total > max_chars:
            truncated = True
            break
        lines.append(line)

    result = "\n".join(lines)
    if truncated:
        result += f"\n\n... (发言过多，已截断至 {len(lines) - 2} 条)"
    return result
