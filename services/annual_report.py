"""
年度报告 + 颁奖典礼 生成服务

v0.11.0：
- 利用 DeepSeek V4 Flash 1M 上下文，基于全年数据 + 月报摘要生成年度颁奖典礼
- 12 个奖项绑定群友，存储到 annual_awards 表
- 重新生成时旧奖项作废

数据流：
原始消息 → Python 统计 + 匿名化采样 → 月报摘要聚合 → DeepSeek → 脱敏还原 → 保存
"""
import json
import re
import logging
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from config import config
from models.database import (
    get_periodic_report, save_periodic_report,
    save_annual_awards, get_annual_awards, get_member_awards,
    get_members,
)
from services.online_model import call_deepseek_chat
from services.stats_engine import (
    compute_activity_stats, compute_language_stats,
    compute_message_style, compute_topic_role,
)
from services.weekly_report import (
    _build_alias_map, _de_anonymize_ai_output,
    _ai_generate,
)

logger = logging.getLogger(__name__)

# 年度最低数据要求
MIN_DAYS = 30
MIN_MESSAGES = 500

# ---- 年度颁奖典礼 System Prompt ----
ANNUAL_SYSTEM_PROMPT = """你是一位资深的年度颁奖典礼主持人，兼群聊人类学家。

你的任务：基于提供的全年聊天统计数据 + 月报摘要，为群聊撰写一份《年度颁奖典礼》。

## 你的角色
- 幽默风趣、洞察力强，能抓住群聊的精髓
- 颁奖词要有仪式感，同时不失群聊的沙雕气质
- 每个奖项都要有说服力——说明为什么这个人实至名归

## 输出格式（严格 JSON）
{
  "year_theme": "年度主题（6-12字，概括群聊这一年的精神气质）",
  "year_narrative": "年度叙事（200-350字，讲述群聊这一年的故事）",
  "group_evolution": "群聊一年变化（50-100字）",
  "annual_awards": [
    {
      "award_name": "奖项名（4-8字，纯奖项标题，不含人名）",
      "winner": "成员编号（如#1、#3，必须是成员列表中给出的编号）",
      "award_reason": "颁奖词（20-40字，说明获奖理由，可用别名描述）",
      "award_emoji": "emoji"
    }
  ],
  "meme_of_the_year": "年度热梗（30字以内）",
  "next_year_wish": "新年寄语（50-80字）"
}

## 奖项类别参考（从以下选取合适的，也可自创）
1. 年度金句王 — 发言质量最高、金句频出
2. 深夜守夜人 — 凌晨活跃度最高
3. 表情包大师 — emoji/表情使用最丰富
4. 最佳新人 — 今年入群且迅速融入
5. 潜水冠军 — 在线但极少发言
6. 年度CP — 互动最频繁的两人
7. 话题发动机 — 发起话题最多、推动群聊发展
8. 年度卷王 — 发言量增长最快
9. 社交达人 — @别人和被@最多
10. 深度思考者 — 消息最长、深夜有深度发言
11. 气氛组担当 — 活跃气氛、带动情绪
12. AI特别奖 — 值得特别表彰的独特贡献

## 重要规则
- winner 字段必须使用 #数字 格式，如 "#1"、#3"，对应成员列表中的编号
- award_name 是纯奖项标题（如"年度金句王"），不要在里面写人名
- 每个获奖者只能拿一个奖（一人一奖）
- 奖项数量 = {award_count} 个，严格按这个数量输出
- 语言风格：幽默、温暖、有仪式感"""


async def generate_annual_report(group_id: int, year: int, chat,
                                  task=None, force: bool = False,
                                  model_config: dict | None = None) -> dict:
    """
    主入口：生成年度报告 + 颁奖典礼

    v0.12.0: 新增 model_config 参数。年报仅支持在线模型。

    Returns:
        {"success": bool, "data": dict, "error": str, "cached": bool, "model_used": str}
    """
    # 1. 缓存检查
    if not force:
        cached = get_periodic_report(group_id, "annual", str(year))
        if cached:
            try:
                cached["report_json"] = json.loads(cached["report_json"])
            except (json.JSONDecodeError, TypeError):
                pass
            return {"success": True, "data": cached, "cached": True}

    # 2. 收集全年日期
    all_dates = chat.all_dates()
    year_str = str(year)
    year_dates = sorted([d for d in all_dates if d.startswith(year_str)])

    if len(year_dates) < MIN_DAYS:
        return {"success": False, "error": f"数据不足：全年仅有 {len(year_dates)} 天有消息（需要 ≥{MIN_DAYS}天）"}

    # 3. 收集月报摘要作为上下文
    monthly_summaries = _collect_monthly_summaries(group_id, year)

    # 4. 提取年度原始数据（Python统计 + 匿名化采样）
    raw_data = _extract_annual_raw_data(chat, year_dates, group_id)
    if not raw_data:
        return {"success": False, "error": "无法提取年度数据"}

    if raw_data["stats"]["total_messages"] < MIN_MESSAGES:
        return {"success": False,
                "error": f"消息量不足：全年仅 {raw_data['stats']['total_messages']} 条文本消息（需要 ≥{MIN_MESSAGES}条）"}

    # 5. 计算奖项数量
    active_count = raw_data["stats"]["active_members"]
    award_count = max(3, min(15, active_count // 2))
    award_count = (award_count // 3) * 3

    # 6. 构建 prompt（v0.13.3: award_count 传参复用，避免 _build_annual_prompt 内重复计算）
    user_prompt = _build_annual_prompt(raw_data, monthly_summaries, year, award_count)

    # 7. 调用 AI
    if task:
        task.update(status="running", step="正在调用 DeepSeek 生成年度报告...")

    system_prompt = ANNUAL_SYSTEM_PROMPT.replace("{award_count}", str(award_count))
    ai_result = await _ai_generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=config.DEEPSEEK_MODEL,
        temperature=0.7,
        max_tokens=16384,
        json_mode=True,
        thinking=True,
        model_config=model_config,
    )

    if not ai_result["success"]:
        return {"success": False, "error": f"AI 生成失败: {ai_result.get('error', '未知错误')}"}

    # 7. 解析 AI 输出（复用 weekly_report 的 _parse_ai_json，它安全处理 dict/str）

    from services.weekly_report import _parse_ai_json
    ai_data = _parse_ai_json(ai_result["data"])
    if not ai_data:
        return {"success": False, "error": "AI 返回格式异常，无法解析 JSON"}

    # 8. 解析奖项（用 #N 编号映射成员，避免名字替换污染）
    member_index = raw_data["member_index"]  # [{wxid, alias, detail}, ...]
    member_map = raw_data["member_map"]  # {wxid: member_id}
    reverse_map = raw_data["reverse_map"]  # {alias: real_name}
    member_names_map = {}
    for s in chat.senders:
        member_names_map[s["wxid"]] = s.get("displayName") or s.get("nickname") or s["wxid"]

    awards = ai_data.get("annual_awards", [])
    saved_awards = []
    skipped_awards = 0
    for award in awards:
        winner_raw = str(award.get("winner", "")).strip()
        # 解析 #N 格式
        match = re.match(r'#(\d+)', winner_raw)
        idx = int(match.group(1)) - 1 if match else -1

        if 0 <= idx < len(member_index):
            wxid = member_index[idx]["wxid"]
            member_id = member_map.get(wxid, 0)
            display_name = member_names_map.get(wxid, member_index[idx]["alias"])
        else:
            member_id = 0
            display_name = winner_raw
            logger.warning("无法解析获奖者: winner=%s (期望 #N 格式，N=1~%d)", winner_raw, len(member_index))

        # 只脱敏颁奖词（奖项名是纯标题，不需要脱敏）
        reason = award.get("award_reason", "")
        if reason:
            reason = _de_anonymize_ai_output(reason, reverse_map)

        # 验证奖项名（过滤被污染的）
        award_name = award.get("award_name", "").strip()
        if not award_name or len(award_name) < 3 or award_name in ("null", "None", ""):
            logger.warning("跳过无效奖项名: award_name=%r, winner=%s", award_name, winner_raw)
            skipped_awards += 1
            continue

        if member_id:
            saved_awards.append({
                "member_id": member_id,
                "winner_name": display_name,
                "award_name": award_name,
                "award_reason": reason,
                "award_emoji": award.get("award_emoji", "🏆"),
            })

    if saved_awards:
        save_annual_awards(group_id, year, saved_awards)
        logger.info("年度奖项已保存: group=%d year=%d total=%d saved=%d skipped=%d",
                    group_id, year, len(awards), len(saved_awards), skipped_awards)
    else:
        logger.warning("年度奖项全部被过滤: group=%d year=%d total=%d skipped=%d",
                       group_id, year, len(awards), skipped_awards)

    # 脱敏叙事内容（不含奖项名）
    for key in ("year_narrative", "group_evolution", "meme_of_the_year", "next_year_wish"):
        if key in ai_data:
            ai_data[key] = _de_anonymize_ai_output(ai_data[key], reverse_map)

    # 10. 组装年度报告
    date_start = year_dates[0]
    date_end = year_dates[-1]
    day_count = len(year_dates)

    report = {
        "_version": "0.11.1",
        "year": year,
        "date_start": date_start,
        "date_end": date_end,
        "day_count": day_count,
        "total_messages": raw_data["stats"]["total_messages"],
        "active_members": raw_data["stats"]["active_members"],
        "year_theme": ai_data.get("year_theme", ""),
        "year_narrative": ai_data.get("year_narrative", ""),
        "group_evolution": ai_data.get("group_evolution", ""),
        "meme_of_the_year": ai_data.get("meme_of_the_year", ""),
        "next_year_wish": ai_data.get("next_year_wish", ""),
        "annual_awards": saved_awards,
        # Python 统计
        "top_speakers": raw_data["stats"].get("top_speakers", []),
        "night_owls": raw_data["stats"].get("night_owls", []),
        "lurkers": raw_data["stats"].get("lurkers", []),
        "emoji_kings": raw_data["stats"].get("emoji_kings", []),
        "monthly_trend": raw_data["stats"].get("monthly_trend", []),
    }

    # 11. 保存到 periodic_reports
    save_periodic_report(
        group_id=group_id,
        report_type="annual",
        period_key=str(year),
        date_start=date_start,
        date_end=date_end,
        day_count=day_count,
        total_messages=raw_data["stats"]["total_messages"],
        active_members=raw_data["stats"]["active_members"],
        report_json=json.dumps(report, ensure_ascii=False),
        model_used=ai_result.get("model", ""),
    )

    return {"success": True, "data": report, "model_used": ai_result.get("model", "")}


def _collect_monthly_summaries(group_id: int, year: int) -> list[dict]:
    """收集全年12个月的月报摘要"""
    summaries = []
    for month in range(1, 13):
        period_key = f"{year}-{month:02d}"
        report = get_periodic_report(group_id, "monthly", period_key)
        if report:
            try:
                rj = json.loads(report["report_json"])
            except (json.JSONDecodeError, TypeError):
                rj = {}
            summaries.append({
                "month": month,
                "period_key": period_key,
                "headline": rj.get("dominant_mood", "") or rj.get("overview", "")[:100],
                "group_personality": rj.get("group_personality", {}).get("type_label", ""),
                "meme": rj.get("meme_archaeology", "")[:150],
                "topic": rj.get("topic_evolution", "")[:150],
                "member_spotlight": rj.get("member_spotlight", "")[:150],
                "day_count": report.get("day_count", 0),
            })
    return summaries


def _extract_annual_raw_data(chat, dates: list[str], group_id: int) -> dict | None:
    """
    从原始消息中提取年度统计数据 + 匿名化采样
    返回: {stats, sampled_msgs, member_summary, alias_map, reverse_map, member_map, name_to_wxid}
    """
    # 1. 收集全年文本消息（使用 chunk_by_date 避免 O(D×M) 全量扫描）
    by_date_msgs = {}
    total_text = 0
    chunked = chat.chunk_by_date()

    for date_str in dates:
        day_msgs = chunked.get(date_str, [])
        msgs = [m for m in day_msgs
                if m.get("type") in ("文本消息", "引用消息")
                and (m.get("content") or "").strip()]
        if msgs:
            by_date_msgs[date_str] = msgs
            total_text += len(msgs)

    if not by_date_msgs:
        return None

    # 2. 构建成员名称映射
    member_names = {}
    member_map = {}  # wxid → member_id (数据库id)
    for s in chat.senders:
        name = s.get("displayName") or s.get("nickname") or s.get("wxid", "")
        member_names[s["wxid"]] = name

    # 获取数据库 member_id
    db_members = get_members(group_id)
    for m in db_members:
        member_map[m["wxid"]] = m["id"]

    name_to_wxid = {v: k for k, v in member_names.items()}

    # 3. 匿名化
    alias_map = _build_alias_map(member_names)
    reverse_map = {v: k for k, v in alias_map.items()}

    # 4. 计算每成员 Python 统计
    member_stats = {}
    all_member_msgs = defaultdict(list)

    for date_str, msgs in by_date_msgs.items():
        for m in msgs:
            wxid = m.get("wxid", "")
            if wxid:
                all_member_msgs[wxid].append(m)

    all_wxids = set(all_member_msgs.keys())
    member_name_set = set(member_names.values())
    # 构建全部消息列表，供 compute_topic_role 正确计算 initiation_rate 和 reply_count
    all_msgs_flat = [m for msgs_list in all_member_msgs.values() for m in msgs_list]

    for wxid, msgs in all_member_msgs.items():
        activity = compute_activity_stats(msgs, wxid)
        language = compute_language_stats(msgs, wxid, member_names=member_name_set)
        style = compute_message_style(language, activity)
        role = compute_topic_role(all_msgs_flat, wxid, all_wxids)
        member_stats[wxid] = {
            "msg_count": activity["total_messages"],
            "days_active": activity["total_days_active"],
            "peak_hour": activity["peak_hour"],
            "avg_msg_len": language["avg_msg_len"],
            "top_emojis": language.get("top_emojis", [])[:3],
            "style_label": style.get("style_label", ""),
            "emoji_style": style.get("emoji_style_label", ""),
            "role_label": role.get("role_label", ""),
        }

    # 5. 整体统计
    sorted_by_msg = sorted(member_stats.items(), key=lambda x: x[1]["msg_count"], reverse=True)
    top_speakers = [{"alias": alias_map.get(wxid, member_names.get(wxid, wxid)),
                     "count": s["msg_count"]} for wxid, s in sorted_by_msg[:10]]

    night_owls = sorted(
        [(wxid, s) for wxid, s in member_stats.items() if s["peak_hour"] >= 23 or s["peak_hour"] <= 5],
        key=lambda x: x[1]["msg_count"], reverse=True
    )[:5]
    night_owls = [{"alias": alias_map.get(wxid, member_names.get(wxid, wxid)),
                   "peak_hour": s["peak_hour"]} for wxid, s in night_owls]

    lurkers = sorted(
        [(wxid, s) for wxid, s in member_stats.items()
         if s["days_active"] >= 10 and s["msg_count"] <= s["days_active"] * 2],
        key=lambda x: x[1]["msg_count"]
    )[:5]
    lurkers = [{"alias": alias_map.get(wxid, member_names.get(wxid, wxid)),
                "msg_count": s["msg_count"], "days_active": s["days_active"]}
               for wxid, s in lurkers]

    emoji_kings = sorted(member_stats.items(),
                         key=lambda x: sum(e.get("count", 0) for e in x[1].get("top_emojis", [])),
                         reverse=True)[:5]
    emoji_kings = [{"alias": alias_map.get(wxid, member_names.get(wxid, wxid)),
                    "emoji_count": sum(e.get("count", 0) for e in s.get("top_emojis", []))}
                   for wxid, s in emoji_kings]

    # 月度趋势
    monthly_msg_counts = defaultdict(int)
    for date_str, msgs in by_date_msgs.items():
        month_key = date_str[:7]
        monthly_msg_counts[month_key] += len(msgs)
    monthly_trend = [{"month": k, "count": v} for k, v in sorted(monthly_msg_counts.items())]

    # 6. 采样消息（每天最多3条，减少 token 消耗）
    sampled_msgs = []
    for date_str in sorted(by_date_msgs.keys()):
        msgs = by_date_msgs[date_str]
        # 优先选长消息
        scored = sorted(msgs, key=lambda m: len((m.get("content") or "").strip()), reverse=True)
        highlights = []
        for m in scored[:3]:
            content = (m.get("content") or "").strip()
            if len(content) > 10:
                highlights.append({
                    "speaker": alias_map.get(m.get("wxid", ""), member_names.get(m.get("wxid", ""), "?")),
                    "content": content[:120],
                    "time": m.get("formattedTime", "")[11:16],
                })
        if highlights:
            sampled_msgs.append({"date": date_str, "count": len(msgs), "highlights": highlights})

    # 控制总采样量（全年最多365天*3条=1095条，太多了；限制到150天）
    if len(sampled_msgs) > 150:
        step = len(sampled_msgs) / 150
        sampled_msgs = [sampled_msgs[int(i * step)] for i in range(150)]

    # 7. 匿名化消息内容
    for day in sampled_msgs:
        for h in day["highlights"]:
            h["content"] = _anonymize_content(h["content"], alias_map)

    stats = {
        "total_messages": total_text,
        "active_days": len(by_date_msgs),
        "active_members": len(member_stats),
        "top_speakers": top_speakers,
        "night_owls": night_owls,
        "lurkers": lurkers,
        "emoji_kings": emoji_kings,
        "monthly_trend": monthly_trend,
        "member_details": {alias_map.get(wxid, member_names.get(wxid, wxid)): s
                          for wxid, s in member_stats.items()},
    }

    # 构建编号索引（按发言量降序排列，供 prompt 中 #N 引用）
    member_index = [
        {"wxid": wxid, "alias": alias_map.get(wxid, member_names.get(wxid, wxid)),
         "detail": member_stats[wxid]}
        for wxid, _ in sorted_by_msg
    ]

    return {
        "stats": stats,
        "sampled_msgs": sampled_msgs,
        "alias_map": alias_map,
        "reverse_map": reverse_map,
        "member_map": member_map,
        "name_to_wxid": name_to_wxid,
        "member_index": member_index,
    }


def _anonymize_content(content: str, alias_map: dict[str, str]) -> str:
    """匿名化单条消息内容"""
    sorted_names = sorted(alias_map.items(), key=lambda x: len(x[0]), reverse=True)
    for real_name, alias in sorted_names:
        if real_name and len(real_name) > 1:
            content = content.replace(real_name, alias)
    # 注意：模式顺序很重要！更具体的必须放前面
    for pattern, replacement in [
        (re.compile(r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]'), '[身份证]'),
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[邮箱]'),
        (re.compile(r'1[3-9]\d{9}'), '[手机号]'),
        (re.compile(r'\d{3,4}-\d{7,8}'), '[电话号码]'),              # 座机号码
    ]:
        content = pattern.sub(replacement, content)
    return content


# _de_anonymize_ai_output 已从 services.weekly_report 导入，直接使用，不重复定义


def _build_annual_prompt(raw_data: dict, monthly_summaries: list[dict], year: int,
                          award_count: int = 0) -> str:
    """构建年度报告的用户提示词（v0.13.3: award_count 由调用方传入，避免重复计算）"""
    stats = raw_data["stats"]
    sampled = raw_data["sampled_msgs"]
    member_index = raw_data.get("member_index", [])  # [{wxid, alias, detail}]

    # award_count 由调用方预先计算传入；若未传入则动态计算
    if award_count <= 0:
        active_count = stats["active_members"]
        award_count = max(3, min(15, active_count // 2))
        award_count = (award_count // 3) * 3

    # 月报摘要
    monthly_text_parts = []
    for ms in monthly_summaries:
        parts = [f"### {ms['month']}月"]
        if ms.get("headline"):
            parts.append(f"氛围：{ms['headline']}")
        if ms.get("meme"):
            parts.append(f"热梗：{ms['meme']}")
        monthly_text_parts.append("\n".join(parts))
    monthly_text = "\n\n".join(monthly_text_parts) if monthly_text_parts else "（暂无月报数据）"

    # 成员索引列表（带编号）
    member_index_lines = []
    for i, m in enumerate(member_index[:20]):
        d = m["detail"]
        member_index_lines.append(
            f"[#{i+1}] {m['alias']} — {d['msg_count']}条消息，活跃{d['days_active']}天，"
            f"高峰{d['peak_hour']}点，{d['style_label']}，{d['role_label']}"
        )

    # 消息采样
    sample_parts = []
    for day in sampled[:80]:
        lines = [f"[{day['date']}，{day['count']}条]"]
        for h in day["highlights"]:
            lines.append(f"  {h['speaker']} ({h['time']}): {h['content']}")
        sample_parts.append("\n".join(lines))
    sample_text = "\n\n".join(sample_parts)

    prompt = f"""# {year}年 群聊年度颁奖典礼

## 年度基础统计
- 全年消息：{stats['total_messages']} 条 · 活跃 {stats['active_days']} 天 · {stats['active_members']} 人参与

### 发言排行
{chr(10).join(f"{i+1}. {s['alias']} — {s['count']}条" for i, s in enumerate(stats['top_speakers'][:10]))}

### 月度趋势
{chr(10).join(f"- {t['month']}：{t['count']}条" for t in stats['monthly_trend'])}

## 成员索引（用 #编号 引用获奖者）
{chr(10).join(member_index_lines)}

## 月度报告
{monthly_text}

## 消息采样
{sample_text}

---
请为这个群撰写 {year}年度颁奖典礼。生成 {award_count} 个奖项，winner 字段使用 #编号。严格 JSON 格式输出。"""

    return prompt
