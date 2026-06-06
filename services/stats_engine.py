"""
Python 统计引擎：纯计算，不调 AI
负责活跃分析、语言特征、社交关系、情绪时间线
产出结构化数据摘要供 AI 做一句话总结
"""
import re
import logging
from collections import defaultdict, Counter
from typing import Callable

from models.database import get_daily_report, get_analyzed_dates

logger = logging.getLogger(__name__)

# 微信表情模式：匹配 [中文] 格式的内置表情（如 [微笑]、[捂脸]、[强]）
# 这是微信聊天中最主要的 emoji 形式，99%+ 的表情都是这种格式
# 不再匹配 Unicode emoji（😂👍 等），因为 Unicode emoji 范围太广，
# 容易误判：🪰🦟 等 obscure 字符常来自系统/贴纸元数据而非用户实际使用
WECHAT_EMOJI_PATTERN = re.compile(r'\[[一-鿿]{1,6}\]')

# 中文停用词（过滤高频无意义词）
STOP_WORDS = {
    "一个", "可以", "这个", "那个", "什么", "怎么", "为什么", "因为",
    "所以", "但是", "而且", "如果", "虽然", "不过", "就是", "还是",
    "或者", "没有", "不是", "不会", "不能", "知道", "觉得", "可能",
    "应该", "已经", "还有", "然后", "之后", "之前", "以后", "时候",
    "真的", "其实", "当然", "大家", "我们", "他们", "你们", "自己",
    "一下", "一点", "一些", "比较", "非常", "特别", "所有", "一起",
    "今天", "昨天", "明天", "现在", "正在", "过来", "出去", "回来",
    "哈哈哈", "笑死", "我去", "确实", "牛逼", "厉害",
}

# 微信消息元数据标记（出现在 content 中但非实际发言内容）
_META_TOKENS = {
    "图片", "视频", "语音", "文件", "链接", "位置", "名片",
    "聊天记录", "语音记录", "红包", "小程序", "引用",
    "表情", "消息", "记录",
}


def _load_user_stopwords() -> set[str]:
    """从项目根目录 stopwords.txt 加载用户自定义过滤词"""
    from pathlib import Path
    stopwords_file = Path(__file__).resolve().parent.parent / "stopwords.txt"
    words = set()
    if stopwords_file.exists():
        try:
            with open(stopwords_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释
                    if line and not line.startswith("#"):
                        words.add(line)
        except Exception:
            pass
    return words


def _build_dynamic_stop_words(member_names: set[str] = None) -> set[str]:
    """构建动态停用词：用户自定义 + 基础停用词 + 元数据标记 + 成员名字"""
    result = _load_user_stopwords()  # 用户自定义，每次重新加载
    result.update(STOP_WORDS)
    result.update(_META_TOKENS)
    if member_names:
        for name in member_names:
            result.add(name)
            # 长名字的子串也可能是污染源（如 "傻里傻气" 触发 "傻里" "傻气"）
            # 只对 >= 4 字的名字拆分 2-gram，因为短名拆分误伤率太高
            if len(name) >= 4:
                for i in range(len(name) - 1):
                    chunk = name[i:i+2]
                    if chunk not in STOP_WORDS:
                        result.add(chunk)
    return result


def strip_mentions(content: str, member_names: set[str]) -> str:
    """从消息内容中移除 @mention 文本

    处理两种情况：
    1. 显式 @：如 "@张三 你好" → "你好"
    2. 回复式提及：消息开头直接出现群友名字（WeChat 导出格式中回复的表现）
    """
    if not content or not member_names:
        return content

    text = content.strip()

    # 1. 移除 "@名字" 模式（含全角＠）
    text = re.sub(r'[@＠]\s*([^\s]{2,10})', '', text)

    # 2. 移除消息开头的群友名字（回复/mention 格式："张三 你说的对" → "你说的对"）
    #    只处理开头，防止误删正常对话中的名字
    for name in sorted(member_names, key=len, reverse=True):  # 长名优先
        if text.startswith(name) and len(name) >= 3:
            # 确保名字后面跟着空格或标点
            rest = text[len(name):]
            if not rest or rest[0] in ' 　，。！？、：；""''）)】」':
                text = rest.lstrip(' 　，。！？、：；""''）)】」')
                break

    return text.strip()


# ---- 统计函数 ----

def compute_activity_stats(messages: list[dict], wxid: str) -> dict:
    """计算成员的活跃统计

    Args:
        messages: 全部消息列表
        wxid: 目标成员的 wxid

    Returns:
        {total_days_active, avg_daily_msgs, peak_hour, hourly_heatmap, monthly_trend}
    """
    sender_msgs = [m for m in messages if m.get("wxid") == wxid]

    # 按天 + 按小时统计
    day_hours = defaultdict(lambda: defaultdict(int))
    day_set = set()
    for m in sender_msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 13:
            date = ft[:10]
            hour = ft[11:13]
            day_hours[date][hour] += 1
            day_set.add(date)

    total_days = len(day_set)
    total_msgs = len(sender_msgs)

    # 24 小时热力图
    hourly_heatmap = {f"{h:02d}": 0 for h in range(24)}
    for date_hours in day_hours.values():
        for h, c in date_hours.items():
            hourly_heatmap[h] += c

    # 峰值小时
    peak_hour = max(hourly_heatmap, key=hourly_heatmap.get) if total_msgs > 0 else "00"

    # 按月趋势
    monthly = defaultdict(lambda: {"count": 0, "days": set()})
    for m in sender_msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 7:
            month = ft[:7]  # "2025-01"
            monthly[month]["count"] += 1
            if len(ft) >= 10:
                monthly[month]["days"].add(ft[:10])

    monthly_trend = sorted(
        [{"month": k, "count": v["count"], "days_active": len(v["days"])}
         for k, v in monthly.items()],
        key=lambda x: x["month"]
    )

    return {
        "total_days_active": total_days,
        "total_messages": total_msgs,
        "avg_daily_msgs": round(total_msgs / total_days, 1) if total_days > 0 else 0,
        "peak_hour": int(peak_hour),
        "hourly_heatmap": hourly_heatmap,
        "monthly_trend": monthly_trend,
    }


def compute_language_stats(messages: list[dict], wxid: str,
                            member_names: set[str] = None) -> dict:
    """计算成员的语言特征

    Args:
        messages: 全部消息列表
        wxid: 目标成员 wxid
        member_names: 群成员名字集合（用于过滤 @mention）
    """
    sender_msgs = [m for m in messages if m.get("wxid") == wxid]
    # 只用纯文本消息，排除引用（引用内容是别人的话）
    text_msgs = [m for m in sender_msgs
                 if (m.get("content") or "").strip() and m.get("type") in ("文本消息",)]

    if member_names is None:
        member_names = set()

    # 动态停用词：基础 + 元数据 + 成员名
    dynamic_stop_words = _build_dynamic_stop_words(member_names)

    total_len = 0
    length_bins = {"1-5": 0, "6-15": 0, "16-30": 0, "31-80": 0, "81+": 0}
    emoji_counter = Counter()
    word_counter = Counter()

    for m in text_msgs:
        raw_content = (m.get("content") or "").strip()
        # 长度用原始内容计算（包含@mention），不受剥离影响
        msg_len = len(raw_content)
        total_len += msg_len

        # 长度分布
        if msg_len <= 5:
            length_bins["1-5"] += 1
        elif msg_len <= 15:
            length_bins["6-15"] += 1
        elif msg_len <= 30:
            length_bins["16-30"] += 1
        elif msg_len <= 80:
            length_bins["31-80"] += 1
        else:
            length_bins["81+"] += 1

        # 剥离 @mention 后再做词分析和 emoji 提取
        content = strip_mentions(raw_content, member_names)

        # Emoji 提取：仅匹配微信 [表情] 格式，排除元数据占位符
        wechat_emojis = WECHAT_EMOJI_PATTERN.findall(content)
        for e in wechat_emojis:
            inner = e[1:-1]  # 去掉括号
            if inner not in _META_TOKENS:  # [图片][视频][链接] 不算表情
                emoji_counter[e] += 1

        # 中文分词（简单 2-gram）
        # [捂脸] → 保留 "捂脸"（有语义）；[图片][视频] → 整体删除（元数据噪音）
        clean_content = WECHAT_EMOJI_PATTERN.sub(
            lambda m: '' if m.group(0)[1:-1] in _META_TOKENS else m.group(0)[1:-1],
            content
        )
        # 提取连续中文字符作为词
        chinese_chunks = re.findall(r'[一-鿿]{2,4}', clean_content)
        for chunk in chinese_chunks:
            if chunk not in dynamic_stop_words:
                word_counter[chunk] += 1

    msg_count = len(text_msgs)

    return {
        "avg_msg_len": round(total_len / msg_count, 1) if msg_count > 0 else 0,
        "total_text_msgs": msg_count,
        "msg_length_distribution": length_bins,
        "top_emojis": [{"emoji": e, "count": c} for e, c in emoji_counter.most_common(10)],
        "top_words": [{"word": w, "count": c} for w, c in word_counter.most_common(15)],
        "total_emoji_count": sum(emoji_counter.values()),
    }


def compute_social_relations(messages: list[dict], wxid: str,
                              get_sender_name, get_name_by_wxid=None) -> list[dict]:
    """计算成员的社交关系

    互动定义：
    - 共现：两人在 5 分钟内先后发言
    - @提及：消息内容中包含对方名字

    Returns:
        [{wxid, name, co_msg_count, mention_count, total_interactions}]
        按 total_interactions 降序，Top 10
    """
    # 预建名字缓存（wxid → name）
    wxid_name_cache: dict[str, str] = {}

    def get_name(w):
        if w not in wxid_name_cache:
            wxid_name_cache[w] = (get_name_by_wxid(w) if get_name_by_wxid
                                   else get_sender_name(0)) if w != wxid else ""
        return wxid_name_cache[w]

    # 1. 共现计数
    import bisect
    co_counter = Counter()
    target_tss = sorted([m.get("createTime", 0) for m in messages
                          if m.get("wxid") == wxid and m.get("createTime", 0)])

    if target_tss:
        for m in messages:
            mwxid = m.get("wxid", "")
            if mwxid == wxid:
                continue
            ts = m.get("createTime", 0)
            if not ts:
                continue
            idx = bisect.bisect_left(target_tss, ts)
            if (idx > 0 and abs(ts - target_tss[idx - 1]) <= 300) or \
               (idx < len(target_tss) and abs(ts - target_tss[idx]) <= 300):
                co_counter[mwxid] += 1
                # 顺便缓存名字
                if mwxid not in wxid_name_cache:
                    wxid_name_cache[mwxid] = get_name_by_wxid(mwxid) if get_name_by_wxid else mwxid

    # 2. @提及检测
    sender_msgs = [m for m in messages if m.get("wxid") == wxid]
    mention_counter = Counter()
    all_wxids = set(wxid_name_cache.keys()) | {m.get("wxid", "") for m in messages if m.get("wxid")}

    for m in sender_msgs:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        for other_wxid in all_wxids:
            if other_wxid == wxid or not other_wxid:
                continue
            name = wxid_name_cache.get(other_wxid) or (get_name_by_wxid(other_wxid) if get_name_by_wxid else "")
            if not name:
                name = other_wxid
                wxid_name_cache[other_wxid] = name
            if name and len(name) >= 2 and name in content:
                mention_counter[other_wxid] += 1

    # 3. 合并
    all_interactors = set(list(co_counter.keys()) + list(mention_counter.keys()))
    relations = []
    for w in all_interactors:
        if w == wxid:
            continue
        co = co_counter.get(w, 0)
        mention = mention_counter.get(w, 0)
        total = co + mention * 3
        name = wxid_name_cache.get(w, w)
        relations.append({
            "wxid": w,
            "name": name,
            "co_msg_count": co,
            "mention_count": mention,
            "total_interactions": total,
        })

    relations.sort(key=lambda x: x["total_interactions"], reverse=True)
    return relations[:10]


def compute_emotion_timeline(group_id: int) -> list[dict]:
    """从已有每日报告中提取情绪变化时间线

    Returns:
        [{date, mood, mood_emoji}] 按日期升序
    """
    import json
    dates = get_analyzed_dates(group_id)
    timeline = []
    for date in sorted(dates):
        report = get_daily_report(group_id, date)
        if not report or not report.get("report_json"):
            continue
        try:
            rj = json.loads(report["report_json"])
            mood = rj.get("mood", "")
            emoji = rj.get("mood_emoji", "")
            if mood:
                timeline.append({"date": date, "mood": mood, "mood_emoji": emoji})
        except (json.JSONDecodeError, TypeError):
            continue
    return timeline


def format_stats_for_ai(activity: dict, language: dict, relations: list[dict],
                         emotion: list[dict]) -> dict:
    """将统计数据格式化为 AI prompt 可用的简短摘要

    返回结构化短文本，每个字段 ≤ 200 字，适合直接拼入 AI prompt
    """
    # 活跃摘要
    peak_h = activity.get("peak_hour", 0)
    activity_lines = [
        f"总活跃{activity.get('total_days_active',0)}天，共{activity.get('total_messages',0)}条消息",
        f"日均{activity.get('avg_daily_msgs',0)}条，最活跃时段{peak_h}:00",
    ]
    monthly = activity.get("monthly_trend", [])
    if monthly:
        trend_desc = " → ".join(
            f"{m['month'][-2:]}月{m['count']}条" for m in monthly[-6:]
        )
        activity_lines.append(f"月度趋势：{trend_desc}")
    activity_summary = "。".join(activity_lines)

    # 语言摘要
    lang_lines = [f"平均消息长度{language.get('avg_msg_len',0)}字"]
    top_emojis = language.get("top_emojis", [])[:5]
    if top_emojis:
        lang_lines.append(f"常用emoji：{' '.join(e['emoji'] for e in top_emojis)}")
    top_words = language.get("top_words", [])[:8]
    if top_words:
        lang_lines.append(f"高频词：{'、'.join(w['word'] for w in top_words)}")
    lang_summary = "。".join(lang_lines)

    # 关系摘要
    rel_lines = []
    for r in relations[:5]:
        rel_lines.append(f"{r['name']}(互动{r['total_interactions']}次)")
    rel_summary = "互动Top5：" + "、".join(rel_lines) if rel_lines else "暂无互动数据"

    # 情绪摘要
    mood_counter = Counter(e["mood"] for e in emotion)
    mood_lines = [f"{m}({c}天)" for m, c in mood_counter.most_common(5)]
    emo_summary = "情绪分布：" + "、".join(mood_lines) if mood_lines else "暂无情绪数据"

    return {
        "activity_summary": activity_summary,
        "language_summary": lang_summary,
        "relation_summary": rel_summary,
        "emotion_summary": emo_summary,
    }


def compute_fun_title_basis(activity: dict, language: dict,
                             relations: list[dict], emoji_stats: list[dict]) -> dict:
    """根据统计数据生成趣味称号的依据，供 AI 起名

    Returns:
        {category: str, data_bullets: [str]} — 最适合的称号类别 + 数据支撑
    """
    candidates = []

    # 深夜活跃
    peak_h = activity.get("peak_hour", 12)
    if peak_h >= 23 or peak_h <= 2:
        candidates.append(("夜猫子", f"最活跃时段{peak_h}:00"))
    elif peak_h >= 22:
        candidates.append(("深夜选手", f"最活跃时段{peak_h}:00"))
    if 0 <= peak_h <= 5:
        candidates.append(("修仙大佬", f"凌晨{peak_h}点还在线"))

    # 早起鸟
    if 5 <= peak_h <= 8:
        candidates.append(("早起冠军", f"最活跃时段{peak_h}:00"))

    # 话痨/潜水/摸鱼
    avg = activity.get("avg_daily_msgs", 0)
    if avg >= 30:
        candidates.append(("话痨担当", f"日均发言{avg}条"))
    elif avg <= 3 and activity.get("total_days_active", 0) >= 10:
        candidates.append(("潜水冠军", f"日均发言仅{avg}条"))
    if 3 < avg <= 8 and activity.get("total_days_active", 0) >= 10:
        candidates.append(("摸鱼选手", f"日均{avg}条，张弛有度"))

    # 表情包大户
    total_emoji = language.get("total_emoji_count", 0)
    if total_emoji >= 100:
        candidates.append(("表情包大户", f"使用了{total_emoji}次表情"))

    # 惜字如金 / 长篇大论
    avg_len = language.get("avg_msg_len", 0)
    if avg_len <= 5 and language.get("total_text_msgs", 0) >= 50:
        candidates.append(("惜字如金", f"平均每条仅{avg_len}字"))
    elif avg_len >= 40:
        candidates.append(("小作文选手", f"平均每条{avg_len}字"))

    # 社交达人
    if len(relations) >= 3 and relations[0].get("total_interactions", 0) >= 200:
        candidates.append(("社交达人", f"与{relations[0]['name']}等{len(relations)}人频繁互动"))

    # 气氛组
    top_emoji = emoji_stats[0]["emoji"] if emoji_stats else ""
    if top_emoji and any(e in top_emoji for e in ["偷笑", "捂脸", "呲牙", "憨笑"]):
        candidates.append(("气氛组担当", f"最爱发{top_emoji}"))
    if top_emoji and any(e in top_emoji for e in ["强", "抱拳", "OK"]):
        candidates.append(("捧场王", f"最爱发{top_emoji}"))

    # 真香/打脸
    if avg_len <= 10 and avg >= 10:
        candidates.append(("短句战神", "短小精悍，句句暴击"))

    if not candidates:
        candidates.append(("神秘群友", "数据不足以判断"))

    # 挑第一个匹配的（按优先级）
    chosen = candidates[0]
    data_lines = [chosen[1]]
    # 补充更多数据
    if activity.get("total_days_active", 0) > 0:
        data_lines.append(f"活跃{activity['total_days_active']}天，共{activity.get('total_messages',0)}条消息")
    if relations:
        data_lines.append(f"互动最多：{relations[0]['name']}")

    return {
        "category": chosen[0],
        "data_summary": "；".join(data_lines),
    }
