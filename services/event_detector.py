"""
事件探测服务 v1.18.0
Phase 1: Python 检测消息量尖峰 → 候选时段
Phase 2: AI 在固定消息窗口内识别事件（并发限流）
Phase 3: 去重合并 + 成员名解析

设计原则："Python 做检测，AI 做叙事"
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from collections import defaultdict

from config import config
from models.database import (
    get_default_prompt, insert_events, get_group
)

logger = logging.getLogger(__name__)

# ── AI 调用信号量（懒初始化） ───────────────────────────────────────────
_ai_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _ai_semaphore
    if _ai_semaphore is None:
        concurrency = getattr(config, "EVENT_AI_CONCURRENCY", 3)
        _ai_semaphore = asyncio.Semaphore(concurrency)
    return _ai_semaphore



# ── 硬编码默认 System Prompt（无 DB 配置时 fallback） ────────────────
_EVENT_DEFAULT_SYSTEM_PROMPT = """你是一个群聊历史学家+八卦记者+脱口秀段子手的混合体。
你的任务是从群聊对话中发掘那些值得被记住的事件——
无论是重要决定、欢乐瞬间、名场面诞生，还是群友之间的默契互动。

你像一个坐在群里的隐形观察员，把精华时刻记录下来，
用轻松诙谐的口吻写成事件卡片。读者看完应该会心一笑：
"对对对，那天就是这样！"

事件类型：
- decision：群内做出了某个决定（讨论→收敛→结论）
- discussion：围绕某个话题的深度讨论
- social：社交互动（庆祝、欢迎、告别、起哄等）
- announcement：某人宣布了重要消息
- meme：梗/文化的诞生和传播

如果这段对话中没有明显事件（就是日常闲聊），返回空 events 数组。"""

# ── 入口函数 ──────────────────────────────────────────────────────────


def find_candidate_windows(chat, date_start: str, date_end: str) -> list[list[dict]]:
    """Phase 1: 扫描消息量尖峰，返回候选消息窗口列表。纯 Python，不调 AI。

    Returns:
        list of windows, each window is a list of message dicts (max ~200 msgs each)
    """
    return _detect_peaks_and_split(chat, date_start, date_end)


def is_window_analyzed(group_id: int, window: list[dict]) -> bool:
    """检查窗口时间范围是否已有事件（用于重新分析时跳过）。"""
    if not window:
        return False
    from models.database import get_events
    start = window[0].get("formattedTime", "")
    end = window[-1].get("formattedTime", "")
    if not start or not end:
        return False
    existing = get_events(group_id, date_from=start[:10], date_to=end[:10])
    if not existing:
        return False
    # 检查是否有事件与窗口时间重叠
    for e in existing:
        e_start = e.get("start_time", "")
        e_end = e.get("end_time", "")
        if e_start <= end and e_end >= start:
            return True
    return False


async def analyze_single_window(chat, group_id: int, window: list[dict]) -> list[dict]:
    """分析单个消息窗口，返回事件列表（0-N 个）。"""
    sem = _get_semaphore()
    group_name = ""
    try:
        g = get_group(group_id)
        if g:
            group_name = g.get("display_name") or g.get("name", "")
    except Exception:
        pass

    async with sem:
        try:
            system_prompt, user_prompt = _build_event_prompt(chat, window, group_name)
            result = await _call_ai_for_events(system_prompt, user_prompt)
            return result
        except Exception as e:
            logger.warning("窗口分析失败: %s", e)
            return []


def insert_events_incremental(events: list[dict], group_id: int) -> int:
    """增量插入事件，逐条检查与已有事件的重复。

    事件 dict 字段（来自 _parse_ai_response）：
    - title, description, event_type, participants, key_quotes
    - time_span_start, time_span_end (HH:MM 格式)

    Returns:
        实际插入的事件数
    """
    if not events:
        return 0

    from models.database import get_events, insert_events as db_insert

    # 批量获取相关日期范围内已有事件（避免 N+1）
    all_dates = set()
    for e in events:
        ts = e.get("time_span_start", "")
        if len(ts) >= 10:
            all_dates.add(ts[:10])
    existing_map = {}
    if all_dates:
        for d in all_dates:
            existing_map[d] = get_events(group_id, date_from=d, date_to=d)

    # 批量获取成员列表（一次 DB 调用）
    member_name_cache = _build_member_name_cache(group_id)

    to_insert = []
    for e in events:
        ts_start = e.get("time_span_start", "")
        ts_end = e.get("time_span_end", "")
        participant_names = e.get("participants", [])

        # 检查重复
        date_key = ts_start[:10] if len(ts_start) >= 10 else ""
        existing = existing_map.get(date_key, [])

        is_dup = False
        for ex in existing:
            if _title_similarity(e.get("title", ""), ex.get("title", "")) >= 0.6:
                is_dup = True
                break
        if is_dup:
            continue

        db_event = {
            "group_id": group_id,
            "title": e.get("title", ""),
            "description": e.get("description", ""),
            "event_type": e.get("event_type", "discussion"),
            "participant_ids": json.dumps(
                _resolve_participant_ids_cached(participant_names, member_name_cache),
                ensure_ascii=False,
            ),
            "key_quotes": json.dumps(
                (e.get("key_quotes") or [])[:3],
                ensure_ascii=False,
            ),
            "start_time": ts_start,
            "end_time": ts_end,
            "message_count": e.get("message_count", 0),
        }
        to_insert.append(db_event)

    if to_insert:
        db_insert(to_insert)
        logger.info("增量插入 %d 个事件（%d 个去重跳过）",
                    len(to_insert), len(events) - len(to_insert))

    return len(to_insert)


# ── Phase 1: 尖峰检测 + 窗口切分 ───────────────────────────────────────


def _classify_group_activity(chat) -> str:
    """判定群活跃度：返回 'active' 或 'quiet'。

    基于日均小时消息量 vs 配置阈值。
    """
    messages = chat.messages
    if not messages:
        return "quiet"

    # 计算时间跨度（小时）
    all_times = [m.get("createTime", 0) for m in messages if m.get("createTime")]
    if len(all_times) < 2:
        return "quiet"

    min_ts, max_ts = min(all_times), max(all_times)
    hours_span = max((max_ts - min_ts) / 3600, 1)  # Unix timestamp seconds → hours
    avg_hourly = len(messages) / hours_span
    threshold = getattr(config, "EVENT_ACTIVE_GROUP_THRESHOLD", 30)

    logger.debug("群活跃度: avg_hourly=%.1f, threshold=%d", avg_hourly, threshold)
    return "active" if avg_hourly >= threshold else "quiet"


def _detect_peaks_and_split(chat, date_start: str, date_end: str) -> list[list[dict]]:
    """Phase 1: 检测消息量尖峰 → 切分为固定大小窗口。

    Returns:
        list of windows, each window is a list of message dicts
    """
    activity = _classify_group_activity(chat)
    message_map = _build_message_map(chat)

    # 按小时统计消息量
    hourly = _count_hourly_messages(chat, date_start, date_end)

    # 检测尖峰
    window_size = getattr(config, "EVENT_WINDOW_SIZE", 200)
    window_overlap = getattr(config, "EVENT_WINDOW_OVERLAP", 20)
    active_threshold = getattr(config, "EVENT_ACTIVE_PEAK_ABSOLUTE", 80)
    quiet_multiplier = getattr(config, "EVENT_QUIET_PEAK_MULTIPLIER", 3)

    peaks = _find_peaks(hourly, activity, active_threshold, quiet_multiplier)
    if not peaks:
        return []

    # 合并相邻尖峰 → 候选时段
    segments = _merge_adjacent_peaks(peaks, chat)
    if not segments:
        return []

    # 切分为固定大小窗口
    windows = _split_into_windows(segments, chat, window_size, window_overlap)
    return windows


def _build_message_map(chat) -> dict:
    """构建消息时间索引：{(date_str, hour): [msg, ...]}"""
    from collections import defaultdict
    mmap = defaultdict(list)
    for m in chat.messages:
        ft = m.get("formattedTime", "")
        if len(ft) >= 13:
            date_hour = ft[:13]  # "2025-03-15 14"
            mmap[date_hour].append(m)
    return mmap


def _count_hourly_messages(chat, date_start: str, date_end: str) -> dict:
    """统计每小时的消息量，返回 {hour_key: count}"""
    counts = defaultdict(int)
    for m in chat.messages:
        ft = m.get("formattedTime", "")
        if len(ft) < 13:
            continue
        date_str = ft[:10]
        if date_str < date_start or date_str > date_end:
            continue
        hour_key = ft[:13]  # "2025-03-15 14"
        counts[hour_key] += 1
    return dict(counts)


def _find_peaks(hourly: dict, activity: str,
                active_threshold: int, quiet_multiplier: int) -> list[str]:
    """检测尖峰时段。

    - 活跃群：按 30 分钟窗口检测
    - 安静群：按小时检测，超日均小时量 × quiet_multiplier
    """
    if not hourly:
        return []

    if activity == "active":
        # 活跃群：按绝对阈值检测小时级尖峰
        peaks = sorted(
            [h for h, c in hourly.items() if c >= active_threshold],
            key=lambda h: h
        )
    else:
        # 安静群：按相对倍数检测
        if len(hourly) == 0:
            return []
        avg = sum(hourly.values()) / len(hourly)
        threshold = max(avg * quiet_multiplier, 20)  # 兜底不低于 20 条
        peaks = sorted(
            [h for h, c in hourly.items() if c >= threshold],
            key=lambda h: h
        )

    logger.debug("尖峰检测 (%s): %d peaks, threshold=%.0f",
                 activity, len(peaks),
                 active_threshold if activity == "active" else
                 (sum(hourly.values()) / len(hourly) * quiet_multiplier if hourly else 0))
    return peaks


def _merge_adjacent_peaks(peaks: list[str], chat) -> list[dict]:
    """合并相邻尖峰时段（2 小时内），返回候选时段列表"""
    if not peaks:
        return []

    segments = []
    current_start = peaks[0]
    current_end = peaks[0]

    for i in range(1, len(peaks)):
        prev_hour = _parse_hour_key(peaks[i - 1])
        curr_hour = _parse_hour_key(peaks[i])
        gap = (curr_hour - prev_hour).total_seconds() / 3600

        if gap <= 2:
            current_end = peaks[i]
        else:
            segments.append({
                "start_hour": current_start,
                "end_hour": current_end,
            })
            current_start = peaks[i]
            current_end = peaks[i]

    segments.append({"start_hour": current_start, "end_hour": current_end})

    # 添加 context padding（前后各 1 小时）
    padded = []
    for seg in segments:
        start_dt = _parse_hour_key(seg["start_hour"]) - timedelta(hours=1)
        end_dt = _parse_hour_key(seg["end_hour"]) + timedelta(hours=2)
        padded.append({
            "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return padded


def _parse_hour_key(key: str) -> datetime:
    """解析 '2025-03-15 14' → datetime"""
    return datetime.strptime(key, "%Y-%m-%d %H")


def _split_into_windows(segments: list[dict], chat,
                        max_size: int, overlap: int) -> list[list[dict]]:
    """将候选时段切分为固定大小的消息窗口。

    每个窗口最多 max_size 条消息，相邻窗口重叠 overlap 条。
    """
    windows = []
    step = max_size - overlap
    if step <= 0:
        step = max_size  # safeguard

    for seg in segments:
        # 获取时段内所有消息
        msgs = [m for m in chat.messages
                if seg["start_time"] <= m.get("formattedTime", "") <= seg["end_time"]]
        if not msgs:
            continue

        # 按消息量切分
        total = len(msgs)
        start = 0
        while start < total:
            end = min(start + max_size, total)
            window = msgs[start:end]
            if window:
                windows.append(window)
            if end >= total:
                break
            start += step

    return windows


# ── Phase 2: AI 分析 ───────────────────────────────────────────────────


def _build_event_prompt(chat, window: list[dict], group_name: str = "") -> tuple[str, str]:
    """构建事件分析 Prompt。

    Returns:
        (system_prompt, user_prompt)
    """
    # System Prompt：优先 DB prompt_profiles，否则硬编码 fallback
    system_prompt = get_default_prompt("event_detection") or _EVENT_DEFAULT_SYSTEM_PROMPT

    # User Prompt：对话原文
    lines = []
    group_label = f'群聊"{group_name}"中' if group_name else "群聊"
    lines.append(f"以下是{group_label}的一段连续对话。请识别其中的有意义事件。\n")

    for m in window:
        ct = m.get("formattedTime", "")
        time_str = ct[11:16] if len(ct) >= 16 else ct  # "HH:MM"
        sender = m.get("senderID", "未知")
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"[{time_str}] {sender}: {content}")

    user_prompt = "\n".join(lines)
    return system_prompt, user_prompt


async def _call_ai_for_events(system_prompt: str, user_prompt: str) -> list[dict]:
    """调用在线 AI 分析单个窗口，返回事件列表。

    使用 json_mode 强制 AI 返回结构化 JSON。
    """
    from services.model_config import resolve_model_with_fallback
    from services.online_model import call_online_chat

    primary, fallback = resolve_model_with_fallback("online")
    if not primary:
        raise RuntimeError("没有可用的在线模型")

    # 构建 json_mode prompt
    json_instruction = """
请严格按以下 JSON 格式返回（不要包含 markdown 代码块标记）：
{
  "events": [
    {
      "title": "一句话标题",
      "description": "2-3句话描述发生了什么",
      "event_type": "decision|discussion|social|announcement|meme",
      "participants": ["成员A", "成员B"],
      "key_quotes": ["关键原话1", "关键原话2"],
      "time_span": {"start": "HH:MM", "end": "HH:MM"}
    }
  ]
}
如果这段对话中没有明显事件，返回 {"events": []}。"""

    full_system = system_prompt + "\n\n" + json_instruction

    try:
        result = await call_online_chat(
            system_prompt=full_system,
            user_prompt=user_prompt,
            model_config=primary,
            temperature=0.8,
            json_mode=True,
            thinking=False,
            max_tokens=4096,
            timeout=getattr(config, "DEEPSEEK_TIMEOUT", 120),
        )
    except Exception as e:
        if fallback:
            logger.info("主模型失败，尝试降级: %s", e)
            result = await call_online_chat(
                system_prompt=full_system,
                user_prompt=user_prompt,
                model_config=fallback,
                temperature=0.8,
                json_mode=True,
                thinking=False,
                max_tokens=4096,
                timeout=getattr(config, "DEEPSEEK_TIMEOUT", 120),
            )
        else:
            raise

    # call_online_chat 返回 dict: {"success": bool, "data": str, ...}
    response_text = result.get("data", "") if isinstance(result, dict) else str(result)
    if not response_text:
        logger.warning("AI 返回空内容: %s", result.get("error", "unknown"))
    return _parse_ai_response(response_text)


def _parse_ai_response(result: str) -> list[dict]:
    """解析 AI 返回的 JSON，提取 events 数组。"""
    if not result:
        return []

    text = result.strip()

    # 尝试去掉 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试用正则提取 JSON 对象
        match = re.search(r'\{.*"events".*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("AI 返回 JSON 解析失败: %s...", text[:200])
                return []
        else:
            logger.warning("AI 返回中未找到 events JSON: %s...", text[:200])
            return []

    events = data.get("events", [])
    if not isinstance(events, list):
        return []

    # 标准化字段
    result_events = []
    for e in events:
        if not isinstance(e, dict):
            continue
        title = (e.get("title") or "").strip()
        if not title:
            continue

        ts = e.get("time_span", {}) or {}
        result_events.append({
            "title": title,
            "description": (e.get("description") or "").strip(),
            "event_type": _normalize_event_type(e.get("event_type", "")),
            "participants": e.get("participants", []),
            "key_quotes": e.get("key_quotes", []),
            "time_span_start": ts.get("start", ""),
            "time_span_end": ts.get("end", ""),
        })

    return result_events


def _normalize_event_type(t: str) -> str:
    """标准化事件类型到 5 个合法值"""
    valid = {"decision", "discussion", "social", "announcement", "meme"}
    t = t.lower().strip()
    if t in valid:
        return t
    # 中英文映射
    mapping = {
        "决策": "decision", "决定": "decision",
        "讨论": "discussion", "深度讨论": "discussion", "辩论": "discussion",
        "社交": "social", "庆祝": "social", "欢迎": "social", "告别": "social",
        "公告": "announcement", "宣布": "announcement",
        "梗": "meme", "玩梗": "meme", "文化": "meme",
    }
    return mapping.get(t, "discussion")  # 默认 discussion




def _title_similarity(a: str, b: str) -> float:
    """简单字符集相似度。"""
    if a == b:
        return 1.0
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)



def _build_member_name_cache(group_id: int) -> dict:
    """构建 {name: member_id} 映射缓存。"""
    cache = {}
    try:
        from models.database import get_members
        members = get_members(group_id)
        for m in members:
            mid = m.get("id")
            if mid:
                for field in ("display_name", "nickname", "wxid"):
                    val = m.get(field, "")
                    if val:
                        cache[val] = mid
    except Exception:
        pass
    return cache


def _resolve_participant_ids_cached(names: list[str], cache: dict) -> list[int]:
    """从缓存解析成员名 → ID。"""
    ids = []
    seen = set()
    for name in names:
        name = name.strip()
        if not name:
            continue
        mid = cache.get(name)
        if mid and mid not in seen:
            ids.append(mid)
            seen.add(mid)
    return ids


def _resolve_participant_ids(names: list[str], chat_or_group_id) -> list[int]:
    """将 AI 返回的成员名称解析为 member_id 列表。支持 ParsedChat 或 group_id。"""
    ids = []
    if not names:
        return ids

    # 构建名称→ID 映射
    name_to_id = {}

    if chat_or_group_id is None:
        return ids

    # 支持传入 group_id (int) 或 chat 对象
    if isinstance(chat_or_group_id, int):
        from models.database import get_members
        try:
            members = get_members(chat_or_group_id)
            for m in members:
                mid = m.get("id")
                if mid:
                    for field in ("display_name", "nickname", "wxid"):
                        val = m.get(field, "")
                        if val:
                            name_to_id[val] = mid
        except Exception:
            pass
    else:
        chat = chat_or_group_id
        for sender in chat.senders:
            sid = sender.get("senderID", "")
            if isinstance(sid, str) and sid.isdigit():
                member_id = int(sid)
            elif isinstance(sid, int):
                member_id = sid
            else:
                continue
            for field in ["displayName", "nickname", "wxid"]:
                val = sender.get(field, "")
                if val:
                    name_to_id[val] = member_id

    seen = set()
    for name in names:
        name = name.strip()
        if not name:
            continue
        mid = name_to_id.get(name)
        if mid and mid not in seen:
            ids.append(mid)
            seen.add(mid)

    return ids


