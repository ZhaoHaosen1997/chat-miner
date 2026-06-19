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
import statistics
from datetime import datetime, timedelta
from collections import defaultdict

from config import config
from models.database import (
    get_default_prompt, insert_events, get_group
)

logger = logging.getLogger(__name__)

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


def find_candidate_windows(chat, date_start: str, date_end: str) -> list[dict]:
    """Phase 1: 扫描消息量尖峰 → 自适应切分为事件组 → 提取摘要。纯 Python，不调 AI。

    Returns:
        list of dicts, each with keys:
        - messages: list of message dicts (the event group)
        - start_time: str, window start time
        - end_time: str, window end time
        - message_count: int
        - summary: dict (time_start, time_end, duration_minutes, message_count,
                         top_speakers, preview, hourly_distribution)
    """
    return _detect_peaks_and_split(chat, date_start, date_end)


# ── Phase 1: 尖峰检测 + 自适应切分 (v1.18.1) ──────────────────────────


def _classify_group_activity(chat, date_start: str = "", date_end: str = "") -> str:
    """判定群活跃度：返回 'active' 或 'quiet'。

    基于所选时间范围内的日均小时消息量 vs 配置阈值。
    """
    messages = chat.messages
    if not messages:
        return "quiet"

    # v1.18.1 fix: 按所选时间范围过滤
    if date_start and date_end:
        messages = [m for m in messages
                    if date_start <= m.get("formattedTime", "")[:10] <= date_end]
    if not messages:
        return "quiet"

    # 计算时间跨度（小时）
    all_times = [m.get("createTime", 0) for m in messages if m.get("createTime")]
    if len(all_times) < 2:
        return "quiet"

    min_ts, max_ts = min(all_times), max(all_times)
    hours_span = max((max_ts - min_ts) / 3600, 1)
    avg_hourly = len(messages) / hours_span
    threshold = getattr(config, "EVENT_ACTIVE_GROUP_THRESHOLD", 30)

    logger.debug("群活跃度: avg_hourly=%.1f, threshold=%d", avg_hourly, threshold)
    return "active" if avg_hourly >= threshold else "quiet"


def _detect_peaks_and_split(chat, date_start: str, date_end: str) -> list[dict]:
    """Phase 1: 检测消息量尖峰 → 自适应切分为事件组 → 提取摘要。

    Returns:
        list of dicts, each with: messages, start_time, end_time,
        message_count, summary
    """
    activity = _classify_group_activity(chat, date_start, date_end)
    hourly = _count_hourly_messages(chat, date_start, date_end)

    # 检测尖峰
    active_threshold = getattr(config, "EVENT_ACTIVE_PEAK_ABSOLUTE", 80)
    quiet_multiplier = getattr(config, "EVENT_QUIET_PEAK_MULTIPLIER", 3)

    peaks = _find_peaks(hourly, activity, active_threshold, quiet_multiplier)
    if not peaks:
        return []

    # 合并相邻尖峰 → 候选时段
    segments = _merge_adjacent_peaks(peaks, chat)
    if not segments:
        return []

    # v1.18.1: 自适应切分替换固定窗口
    result = []
    for seg in segments:
        # 获取时段内所有消息
        msgs = [m for m in chat.messages
                if seg["start_time"] <= m.get("formattedTime", "") <= seg["end_time"]]
        if not msgs:
            continue

        # 自适应切分
        groups = _segment_by_time_gaps(msgs)
        groups = _post_process_groups(groups)

        min_size = getattr(config, "EVENT_MIN_GROUP_SIZE", 10)
        for g in groups:
            if not g or len(g) < min_size:
                continue
            start_t = g[0].get("formattedTime", "")
            end_t = g[-1].get("formattedTime", "")
            summary = _extract_group_summary(g)
            result.append({
                "messages": g,
                "start_time": start_t,
                "end_time": end_t,
                "message_count": len(g),
                "summary": summary,
            })

    logger.info("自适应切分完成: %d 个时段 → %d 个事件组", len(segments), len(result))
    return result


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

    # 添加 context padding（前 30min / 后 1h，提供上下文但不过度拉入边缘噪声）
    padded = []
    for seg in segments:
        start_dt = _parse_hour_key(seg["start_hour"]) - timedelta(minutes=30)
        end_dt = _parse_hour_key(seg["end_hour"]) + timedelta(hours=1)
        padded.append({
            "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return padded


def _parse_hour_key(key: str) -> datetime:
    """解析 '2025-03-15 14' → datetime"""
    return datetime.strptime(key, "%Y-%m-%d %H")


# ── v1.18.1 自适应事件组切分 ────────────────────────────────────────

def _parse_msg_time(msg: dict) -> datetime | None:
    """解析消息的 formattedTime 为 datetime"""
    ft = msg.get("formattedTime", "")
    if len(ft) >= 16:
        try:
            return datetime.strptime(ft[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return None


def _segment_by_time_gaps(msgs: list[dict]) -> list[list[dict]]:
    """基于时间间隙自适应切分消息流。

    算法：
    1. 计算相邻消息的时间间隙（分钟）
    2. 动态阈值 = max(15min, min(P75 × 1.5, 60min))
    3. 在 gap ≥ threshold 处切分
    """
    if len(msgs) <= 1:
        return [msgs] if msgs else []

    min_gap = getattr(config, "EVENT_MIN_GAP_MINUTES", 15)

    # 计算间隙
    gaps = []
    for i in range(1, len(msgs)):
        t1 = _parse_msg_time(msgs[i - 1])
        t2 = _parse_msg_time(msgs[i])
        if t1 and t2:
            gap = (t2 - t1).total_seconds() / 60.0
            gaps.append(max(gap, 0))
        else:
            gaps.append(0)

    if not gaps:
        return [msgs]

    # 动态阈值
    try:
        p75 = statistics.quantiles(gaps, n=4)[2]  # 75th percentile
        threshold = max(min_gap, min(p75 * 1.5, 60))
    except (statistics.StatisticsError, IndexError):
        threshold = min_gap

    logger.debug("自适应切分: %d 条消息, threshold=%.1fmin, gaps range=[%.1f, %.1f]",
                 len(msgs), threshold, min(gaps), max(gaps))

    # 切分
    groups = []
    current = [msgs[0]]
    for i in range(1, len(msgs)):
        if gaps[i - 1] >= threshold:
            if current:
                groups.append(current)
            current = [msgs[i]]
        else:
            current.append(msgs[i])
    if current:
        groups.append(current)

    return groups


def _post_process_groups(groups: list[list[dict]]) -> list[list[dict]]:
    """后处理事件组：迭代合并过小组、切分过大组、丢弃孤立微小段。

    算法：反复扫描直到没有微小段可合并，然后切分过大组。
    """
    min_size = getattr(config, "EVENT_MIN_GROUP_SIZE", 10)
    max_size = getattr(config, "EVENT_MAX_GROUP_SIZE", 500)

    if not groups:
        return []

    # ── 迭代合并微小段 ──
    # 每轮扫描：左→右合并（小→大邻居），右→左合并（小→前邻居）
    # 重复直到稳定
    merged = [list(g) for g in groups]  # 浅拷贝，避免修改原数据
    changed = True
    max_iterations = 10  # 安全上限

    while changed and max_iterations > 0:
        changed = False
        max_iterations -= 1

        # Scan 1: 左→右，合并到下一个（更近的邻居）
        i = 0
        while i < len(merged):
            if len(merged[i]) < min_size:
                if i + 1 < len(merged):
                    # 合并到右边
                    merged[i + 1] = merged[i] + merged[i + 1]
                    merged.pop(i)
                    changed = True
                    continue  # 不递增 i，新 merged[i] 需要重新检查
            i += 1

        # Scan 2: 右→左，合并到前一个
        i = len(merged) - 1
        while i >= 1:
            if len(merged[i]) < min_size:
                merged[i - 1].extend(merged[i])
                merged.pop(i)
                changed = True
            i -= 1

        # Scan 3: 如果只剩 1 个且太小 → 丢弃
        if len(merged) == 1 and len(merged[0]) < min_size:
            logger.debug("丢弃孤立微小段 (%d 条消息)", len(merged[0]))
            return []

    # ── 最终检查：丢弃残留的孤立微小段 ──
    merged = [g for g in merged if len(g) >= min_size]
    if not merged:
        return []

    # ── 切分过大组 ──
    result = []
    for g in merged:
        if len(g) > max_size:
            sub_groups = _split_oversized_group(g, max_size)
            result.extend(sub_groups)
        else:
            result.append(g)

    return result


def _split_oversized_group(msgs: list[dict], max_size: int) -> list[list[dict]]:
    """在超大组内部找次优间隙切分，确保每段至少 50 条"""
    min_segment = 50
    if len(msgs) <= max_size:
        return [msgs]

    # 计算内部间隙
    gaps = []
    for i in range(1, len(msgs)):
        t1 = _parse_msg_time(msgs[i - 1])
        t2 = _parse_msg_time(msgs[i])
        if t1 and t2:
            gap = (t2 - t1).total_seconds() / 60.0
            gaps.append((i, max(gap, 0)))
        else:
            gaps.append((i, 0))

    if not gaps:
        return [msgs]

    # 按间隙降序排列，在满足 min_segment 约束的最佳位置切分
    gaps.sort(key=lambda x: -x[1])

    cut_points = []
    occupied = set()
    for idx, gap_val in gaps:
        if gap_val < 5:  # 间隙太小不切
            continue
        # 检查该切分点前后是否满足最小段约束
        too_close = False
        for cp in cut_points:
            if abs(idx - cp) < min_segment:
                too_close = True
                break
        if too_close:
            continue
        cut_points.append(idx)
        if len(cut_points) >= 3:  # 最多切 3 刀
            break

    if not cut_points:
        # 找不到合适切点，强制均匀切分
        return _force_split_evenly(msgs, max_size)

    cut_points.sort()
    result = []
    prev = 0
    for cp in cut_points:
        result.append(msgs[prev:cp])
        prev = cp
    result.append(msgs[prev:])
    return result


def _force_split_evenly(msgs: list[dict], max_size: int) -> list[list[dict]]:
    """无法找自然间隙时，按 max_size 均匀切分"""
    result = []
    for i in range(0, len(msgs), max_size):
        result.append(msgs[i:i + max_size])
    return result


def _extract_group_summary(window_msgs: list[dict]) -> dict:
    """Python 提取事件组摘要（不调 AI）。

    Returns:
        JSON-serializable dict with: time_start, time_end, duration_minutes,
        message_count, top_speakers, preview, hourly_distribution
    """
    if not window_msgs:
        return {}

    times = []
    senders = defaultdict(int)
    preview = []
    hourly = defaultdict(int)

    for m in window_msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 16:
            times.append(ft[:16])
            hourly[ft[:13]] += 1  # "2025-03-15 14"
        sender = (m.get("senderID") or "").strip()
        if sender:
            senders[sender] += 1
        if len(preview) < 5:
            content = (m.get("content") or "").strip()
            if content:
                preview.append({
                    "time": ft[11:16] if len(ft) >= 16 else ft,
                    "sender": sender,
                    "content": content[:80],
                })

    time_start = times[0] if times else ""
    time_end = times[-1] if times else ""

    # 计算持续时长（分钟）
    duration = 0
    if time_start and time_end:
        try:
            ts = datetime.strptime(time_start, "%Y-%m-%d %H:%M")
            te = datetime.strptime(time_end, "%Y-%m-%d %H:%M")
            duration = int((te - ts).total_seconds() / 60)
        except ValueError:
            pass

    # Top 发言者
    top_speakers = sorted(senders.items(), key=lambda x: -x[1])[:5]
    top_speakers_list = [{"name": name, "count": cnt} for name, cnt in top_speakers]

    text_count = sum(1 for m in window_msgs if (m.get("content") or "").strip())

    return {
        "time_start": time_start,
        "time_end": time_end,
        "duration_minutes": duration,
        "message_count": len(window_msgs),
        "text_message_count": text_count,
        "top_speakers": top_speakers_list,
        "preview": preview[:3],  # 只保留前 3 条
        "hourly_distribution": dict(hourly),
    }


# ── Phase 2: AI 分析 (v1.18.1) ──────────────────────────────────────────


def _build_event_prompt(chat, window: list[dict], group_name: str = "") -> tuple[str, str]:
    """构建事件分析 Prompt（v1.18.1: 单事件输出）。

    Returns:
        (system_prompt, user_prompt)
    """
    # System Prompt：优先 DB prompt_profiles，否则硬编码 fallback
    system_prompt = get_default_prompt("event_detection") or _EVENT_DEFAULT_SYSTEM_PROMPT

    # User Prompt：对话原文
    lines = []
    group_label = f'群聊"{group_name}"中' if group_name else "群聊"
    lines.append(f"以下是{group_label}的一段连续对话。请判断它是否构成一个值得记录的事件。\n")

    for m in window:
        ct = m.get("formattedTime", "")
        time_str = ct[11:16] if len(ct) >= 16 else ct  # "HH:MM"
        sender = m.get("senderID", "未知")
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"[{time_str}] {sender}: {content}")

    user_prompt = "\n".join(lines)
    return system_prompt, user_prompt


async def _call_ai_for_events(system_prompt: str, user_prompt: str) -> dict | None:
    """调用在线 AI 分析单个窗口，返回单个事件 dict 或 None。

    v1.18.1: 一个事件组 = 一个 AI 调用 = 一个事件或空。
    """
    from services.model_config import resolve_model_with_fallback
    from services.online_model import call_online_chat

    primary, fallback = resolve_model_with_fallback("online")
    if not primary:
        raise RuntimeError("没有可用的在线模型")

    # v1.18.1: 单事件输出格式
    json_instruction = """
请严格按以下 JSON 格式返回（不要包含 markdown 代码块标记）。

如果这段对话构成了一个值得记录的事件：
{
  "title": "一句话标题",
  "description": "2-3句话描述发生了什么",
  "event_type": "decision|discussion|social|announcement|meme",
  "participants": ["成员A", "成员B"],
  "key_quotes": ["关键原话1", "关键原话2"],
  "time_span": {"start": "HH:MM", "end": "HH:MM"}
}

如果这段对话只是日常闲聊，不构成事件，返回：
null"""

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
        return None
    return _parse_ai_response(response_text)


def _parse_ai_response(result: str) -> dict | None:
    """解析 AI 返回的 JSON，提取单个事件或 null。

    v1.18.1: 新格式 — 单个事件对象或 null。
    向后兼容：也支持旧格式 {"events": [...]} 取第一个。
    """
    if not result:
        return None

    text = result.strip()

    # null 直接返回
    if text.lower() == "null":
        return None

    # 尝试去掉 markdown 代码块
    if text.startswith("```"):
        lines_ = text.split("\n")
        if lines_[0].startswith("```"):
            lines_ = lines_[1:]
        if lines_ and lines_[-1].strip() == "```":
            lines_ = lines_[:-1]
        text = "\n".join(lines_)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 用花括号计数提取最外层 JSON 对象（支持嵌套）
        data = _extract_json_object(text)
        if data is None:
            logger.warning("AI 返回 JSON 解析失败: %s...", text[:200])
            return None

    # ... continue with data parsing below
            return None

    # 如果 data 是 null
    if data is None:
        return None

    # 向后兼容：旧格式 {"events": [...]}
    if "events" in data:
        events = data.get("events", [])
        if isinstance(events, list) and events:
            data = events[0]  # 取第一个事件
        else:
            return None

    # 提取事件字段
    title = (data.get("title") or "").strip()
    if not title:
        return None

    ts = data.get("time_span", {}) or {}
    return {
        "title": title,
        "description": (data.get("description") or "").strip(),
        "event_type": _normalize_event_type(data.get("event_type", "")),
        "participants": data.get("participants", []),
        "key_quotes": data.get("key_quotes", []),
        "time_span_start": ts.get("start", ""),
        "time_span_end": ts.get("end", ""),
    }


def _extract_json_object(text: str) -> dict | None:
    """用花括号计数提取最外层 JSON 对象，支持嵌套花括号。

    相比正则 \\{[^{}]*\\} 无法处理嵌套对象，此方法逐字符计数，
    找到第一个 '{' 后追踪花括号深度直到归零。
    """
    # 找到第一个 '{'
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # 这个候选无效，继续找下一个 '{'
                    start = text.find('{', start + 1)
                    if start == -1:
                        return None
                    depth = 0
                    i = start - 1  # 循环会 +1
    return None


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


