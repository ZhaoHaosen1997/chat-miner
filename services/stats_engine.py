"""
Python 统计引擎：纯计算，不调 AI
负责活跃分析、语言特征、社交关系、情绪时间线
产出结构化数据摘要供 AI 做一句话总结
"""
import re
import logging
from collections import defaultdict, Counter
from typing import Callable

import jieba

from models.database import get_daily_report, get_analyzed_dates, get_stopwords_text

logger = logging.getLogger(__name__)

# v1.19.0: jieba 自定义词典缓存（避免重复加载）
_jieba_dict_group_ids: set[int] = set()


def _load_jieba_userdict(group_id: int = 0):
    """从群梗百科词条构建 jieba 自定义词典，防止群内黑话被切碎"""
    if not group_id or group_id in _jieba_dict_group_ids:
        return
    try:
        from models.database import get_group_memes
        memes = get_group_memes(group_id, status="approved")
        for m in memes:
            term = (m.get("term") or "").strip()
            if len(term) >= 2:
                jieba.add_word(term, freq=100)
        _jieba_dict_group_ids.add(group_id)
        logger.info("jieba 自定义词典已加载: group=%d words=%d", group_id, len(memes))
    except Exception:
        pass


def _tokenize_chinese(text: str, group_id: int = 0) -> list[str]:
    """中文分词：jieba 精确模式，过滤单字和停用词后的 2 字以上词"""
    _load_jieba_userdict(group_id)
    words = jieba.lcut(text)
    return [w for w in words if len(w) >= 2 and re.search(r'[一-鿿]', w)]

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
    """v1.0.2: 从数据库加载用户自定义过滤词（替代 stopwords.txt 文件读取）"""
    try:
        from models.database import get_stopwords_text
        text = get_stopwords_text()
        words = set()
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.add(line)
        return words
    except Exception as e:
        logger.warning("加载用户停用词失败: %s", e)
        pass
    return set()


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

def compute_activity_stats(messages: list[dict], wxid: str = "",
                           sender_msgs: list[dict] = None) -> dict:
    """计算成员的活跃统计

    Args:
        messages: 全部消息列表（sender_msgs 为空时使用）
        wxid: 目标成员的 wxid（sender_msgs 为空时用于过滤）
        sender_msgs: 预过滤的成员消息列表，提供则跳过过滤

    Returns:
        {total_days_active, avg_daily_msgs, peak_hour, hourly_heatmap, monthly_trend}
    """
    if sender_msgs is None:
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
                            member_names: set[str] = None,
                            sender_msgs: list[dict] = None,
                            group_id: int = 0) -> dict:
    """计算成员的语言特征

    Args:
        messages: 全部消息列表
        wxid: 目标成员 wxid
        member_names: 群成员名字集合（用于过滤 @mention）
        sender_msgs: 预过滤的成员消息列表，提供则跳过过滤
    """
    if sender_msgs is None:
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

        # v1.19.0: jieba 精确模式分词
        clean_content = WECHAT_EMOJI_PATTERN.sub(
            lambda m: '' if m.group(0)[1:-1] in _META_TOKENS else m.group(0)[1:-1],
            content
        )
        for word in _tokenize_chinese(clean_content, group_id):
            if word not in dynamic_stop_words:
                word_counter[word] += 1

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
                              get_sender_name, get_name_by_wxid=None,
                              member_names: dict[str, str] = None) -> list[dict]:
    """计算成员的社交关系

    互动定义：
    - 共现：两人在 5 分钟内先后发言
    - @提及：消息内容中包含对方名字（用正则一次匹配所有人）

    Args:
        messages: 全部消息列表
        wxid: 目标成员 wxid
        get_sender_name: 兼容旧代码
        get_name_by_wxid: wxid → 名字 的映射函数
        member_names: 预建的 {wxid: name} 字典（避免重复查询，批量分析时传入）

    Returns:
        [{wxid, name, co_msg_count, mention_count, total_interactions}]
        按 total_interactions 降序，Top 10
    """
    import bisect, re

    # 预建名字映射（wxid → name），批量分析时可复用
    if member_names is None:
        member_names = {}
        for m in messages:
            w = m.get("wxid", "")
            if w and w not in member_names and w != wxid:
                name = (get_name_by_wxid(w) if get_name_by_wxid else get_sender_name(0))
                if name:
                    member_names[w] = name

    # 1. 共现计数（O(m log n) — 对每个他人消息二分查找目标成员最近发言）
    co_counter = Counter()
    target_tss = sorted([m.get("createTime", 0) for m in messages
                          if m.get("wxid") == wxid and m.get("createTime", 0)])

    if target_tss:
        for m in messages:
            mwxid = m.get("wxid", "")
            if mwxid == wxid or mwxid not in member_names:
                continue
            ts = m.get("createTime", 0)
            if not ts:
                continue
            idx = bisect.bisect_left(target_tss, ts)
            if (idx > 0 and abs(ts - target_tss[idx - 1]) <= 300) or \
               (idx < len(target_tss) and abs(ts - target_tss[idx]) <= 300):
                co_counter[mwxid] += 1

    # 2. @提及检测（正则一次匹配所有人，替代 O(n×m) 嵌套循环）
    mention_counter = Counter()
    # 构建 name→wxid 反向索引和正则
    name_to_wxid: dict[str, str] = {}
    names_for_regex: list[str] = []
    for w, n in member_names.items():
        if w != wxid and len(n) >= 2:
            name_to_wxid[n] = w
            if n not in names_for_regex:  # 去重（可能有同名）
                names_for_regex.append(re.escape(n))
    if names_for_regex:
        # 按长度降序排列，确保长名先匹配（如 "unique pig" 优先于 "pig"）
        names_for_regex.sort(key=len, reverse=True)
        name_pattern = re.compile("|".join(names_for_regex))
        for m in (m for m in messages if m.get("wxid") == wxid):
            content = (m.get("content") or "").strip()
            if not content:
                continue
            for match in name_pattern.finditer(content):
                matched_name = match.group()
                matched_wxid = name_to_wxid.get(matched_name)
                if matched_wxid:
                    mention_counter[matched_wxid] += 1

    # 3. 合并
    all_interactors = set(co_counter) | set(mention_counter)
    relations = []
    for w in all_interactors:
        if w == wxid:
            continue
        co = co_counter.get(w, 0)
        mention = mention_counter.get(w, 0)
        relations.append({
            "wxid": w,
            "name": member_names.get(w, w),
            "co_msg_count": co,
            "mention_count": mention,
            "total_interactions": co + mention * 3,
        })

    relations.sort(key=lambda x: x["total_interactions"], reverse=True)
    return relations[:10]


def compute_all_social_relations(messages: list[dict],
                                  get_name_by_wxid=None) -> dict[str, list[dict]]:
    """批量计算所有成员的社交关系（一次扫描，复用索引）

    对批量画像分析显著提速：所有成员的共现矩阵只建一次。

    Returns:
        {wxid: [{wxid, name, ...}, ...]}  每个成员的 Top 10 关系
    """
    import bisect, re
    from collections import defaultdict

    # 1. 预建名字映射（一次扫描）
    member_names: dict[str, str] = {}
    member_tss: dict[str, list[int]] = defaultdict(list)
    for m in messages:
        w = m.get("wxid", "")
        if not w:
            continue
        ts = m.get("createTime", 0)
        if ts:
            member_tss[w].append(ts)
        if w not in member_names and get_name_by_wxid:
            name = get_name_by_wxid(w)
            if name:
                member_names[w] = name

    # 排序所有成员的时间戳
    for w in member_tss:
        member_tss[w].sort()

    # 2. 构建正则（一次）
    name_to_wxid = {}
    names_for_regex = []
    for w, n in member_names.items():
        if len(n) >= 2:
            name_to_wxid[n] = w
            if n not in names_for_regex:
                names_for_regex.append(re.escape(n))
    names_for_regex.sort(key=len, reverse=True)
    name_pattern = re.compile("|".join(names_for_regex)) if names_for_regex else None

    # 3. 对每个成员计算（复用所有索引）
    result: dict[str, list[dict]] = {}
    for wxid in member_names:
        co_counter = Counter()
        mention_counter = Counter()
        tss = member_tss.get(wxid, [])

        # 共现：对每个他人消息检查
        if tss:
            for m in messages:
                mwxid = m.get("wxid", "")
                if mwxid == wxid or mwxid not in member_names:
                    continue
                ts = m.get("createTime", 0)
                if not ts:
                    continue
                idx = bisect.bisect_left(tss, ts)
                if (idx > 0 and ts - tss[idx - 1] <= 300) or \
                   (idx < len(tss) and tss[idx] - ts <= 300):
                    co_counter[mwxid] += 1

        # @提及
        if name_pattern:
            for m in (m for m in messages if m.get("wxid") == wxid):
                content = (m.get("content") or "").strip()
                if not content:
                    continue
                for match in name_pattern.finditer(content):
                    mw = name_to_wxid.get(match.group())
                    if mw and mw != wxid:
                        mention_counter[mw] += 1

        # 合并
        relations = []
        for w in set(co_counter) | set(mention_counter):
            co = co_counter.get(w, 0)
            mention = mention_counter.get(w, 0)
            relations.append({
                "wxid": w, "name": member_names.get(w, w),
                "co_msg_count": co, "mention_count": mention,
                "total_interactions": co + mention * 3,
            })
        relations.sort(key=lambda x: x["total_interactions"], reverse=True)
        result[wxid] = relations[:10]

    return result


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
            logger.warning(f"情绪时间线: 日报 JSON 损坏 date={date}")
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


# ============================================================
# v0.6.4 新增统计函数
# ============================================================

# 情绪关键词/表情 → mood 映射（用于个人情绪识别）
_MEMBER_EMOTION_PATTERNS = [
    (["偷笑", "呲牙", "憨笑", "大笑", "坏笑", "捂脸", "机智", "耶", "庆祝",
      "哈哈", "笑死", "笑死我了", "哈哈哈哈哈", "xs", "xswl", "233", "乐"], "欢乐"),
    (["流泪", "大哭", "心碎", "裂开", "苦涩", "委屈", "难过",
      "哭了", "好难", "崩溃", "emo", "烦", "郁闷", "呜呜"], "伤感"),
    (["强", "抱拳", "OK", "好的", "赞", "鼓掌", "玫瑰", "爱心",
      "辛苦了", "谢谢", "感谢", "nice", "牛", "牛逼"], "温馨"),
    (["发怒", "炸弹", "刀", "鄙视", "弱", "便便",
      "tm", "特么", "妈的", "滚", "草", "操", "sb"], "吐槽"),
    (["吃瓜", "嗑瓜子", "前排", "围观"], "吃瓜"),
    (["裂开", "破防", "蚌埠住了", "绷不住", "麻了", "破防了"], "破防"),
    (["红包", "發", "恭喜发财", "手气", "运气王"], "热闹"),
    (["狗头", "机智", "斜眼", "坏笑", "阴险", "doge"], "沙雕"),
    (["咖啡", "困", "累", "加班", "摸鱼", "划水"], "摸鱼"),
    (["流汗", "无语", "汗", "离谱", "离谱他妈"], "离谱"),
]


def _detect_member_daily_mood(msgs: list[dict]) -> tuple[str, str]:
    """根据成员当天发言判断个人情绪（关键词+表情密度）

    Returns:
        (mood_label, mood_emoji) 如 ("欢乐", "😄")
    """
    from services.pipelines import MOOD_MAP
    if not msgs:
        return "平淡", "😐"

    mood_scores = {}
    for pattern_keywords, mood in _MEMBER_EMOTION_PATTERNS:
        score = 0
        for m in msgs:
            content = (m.get("content") or "").strip()
            for kw in pattern_keywords:
                if kw in content:
                    score += 1
        if score > 0:
            mood_scores[mood] = score

    if not mood_scores:
        return "平淡", "😐"

    top_mood = max(mood_scores, key=mood_scores.get)
    emoji = MOOD_MAP.get(top_mood, "😐")
    return top_mood, emoji


def compute_member_emotion_timeline(messages: list[dict], wxid: str = "",
                                    sender_msgs: list[dict] = None) -> list[dict]:
    """计算成员个人的每日情绪时间线

    Args:
        messages: 全部消息列表
        wxid: 目标成员 wxid
        sender_msgs: 预过滤的成员消息列表，提供则跳过过滤

    Returns:
        [{date, mood, mood_emoji}] 按日期升序
    """
    from collections import defaultdict
    if sender_msgs is None:
        sender_msgs = [m for m in messages if m.get("wxid") == wxid]
    # 按天聚合成员消息
    day_msgs = defaultdict(list)
    for m in sender_msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 10:
            date = ft[:10]
            day_msgs[date].append(m)

    timeline = []
    for date in sorted(day_msgs.keys()):
        mood, emoji = _detect_member_daily_mood(day_msgs[date])
        timeline.append({"date": date, "mood": mood, "mood_emoji": emoji})

    return timeline


def compute_message_style(language: dict, activity: dict) -> dict:
    """纯 Python 计算消息风格标签（零 AI 成本）

    Returns:
        {avg_len, style_label, reply_style, emoji_style_label}
    """
    avg_len = language.get("avg_msg_len", 0)
    avg_daily = activity.get("avg_daily_msgs", 0)
    emoji_count = language.get("total_emoji_count", 0)
    text_count = language.get("total_text_msgs", 1)

    # 消息长度风格
    if avg_len <= 5:
        style_label = "短小精悍型"
    elif avg_len <= 15:
        style_label = "言简意赅型"
    elif avg_len <= 40:
        style_label = "娓娓道来型"
    else:
        style_label = "长篇大论型"

    # emoji 使用风格
    emoji_ratio = emoji_count / max(text_count, 1)
    if emoji_ratio >= 0.8:
        emoji_style_label = "表情包轰炸型"
    elif emoji_ratio >= 0.3:
        emoji_style_label = "表情活跃型"
    elif emoji_count <= 5 and text_count >= 50:
        emoji_style_label = "纯文字型"
    else:
        emoji_style_label = "适度表情型"

    # 活跃节奏标签
    if avg_daily >= 20:
        reply_style = "高频互动型"
    elif avg_daily >= 5:
        reply_style = "张弛有度型"
    elif avg_daily >= 1:
        reply_style = "随缘冒泡型"
    else:
        reply_style = "深海潜水型"

    return {
        "avg_len": avg_len,
        "style_label": style_label,
        "emoji_style_label": emoji_style_label,
        "reply_style": reply_style,
    }


def compute_recent_status(messages: list[dict], wxid: str = "",
                          member_names: set[str] = None,
                          recent_days: int = 30,
                          group_id: int = 0,
                          sender_msgs: list[dict] = None) -> dict:
    """计算成员最近状态的快照（最近 N 天）

    Returns:
        {active_trend, recent_topics, recent_mood, recent_msg_count, recent_days_active}
    """
    from collections import defaultdict, Counter
    from datetime import datetime, timedelta

    now = datetime.now()
    cutoff_date = (now - timedelta(days=recent_days)).strftime("%Y-%m-%d")

    if sender_msgs is None:
        sender_msgs = [m for m in messages if m.get("wxid") == wxid]

    recent_msgs = []
    for m in sender_msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 10 and ft[:10] >= cutoff_date:
            recent_msgs.append(m)

    if not recent_msgs:
        return {
            "active_trend": "📴",
            "trend_label": "最近没有发言",
            "recent_topics": [],
            "recent_mood": "未知",
            "recent_mood_emoji": "😶",
            "recent_msg_count": 0,
            "recent_days_active": 0,
        }

    # 按天统计
    day_counts = defaultdict(int)
    for m in recent_msgs:
        ft = m.get("formattedTime", "")
        date = ft[:10]
        day_counts[date] += 1

    recent_days_active = len(day_counts)
    recent_msg_count = len(recent_msgs)

    # 活跃趋势：对比前半个月和后半个月
    mid_point = sorted(day_counts.keys())[len(day_counts) // 2] if len(day_counts) > 2 else ""
    if mid_point and len(day_counts) >= 6:
        first_half = sum(c for d, c in day_counts.items() if d < mid_point)
        second_half = sum(c for d, c in day_counts.items() if d >= mid_point)
        if second_half > first_half * 1.3:
            active_trend = "📈"
            trend_label = "近期越来越活跃"
        elif first_half > second_half * 1.3:
            active_trend = "📉"
            trend_label = "近期活跃度下降"
        else:
            active_trend = "📊"
            trend_label = "活跃度保持稳定"
    else:
        active_trend = "📊"
        trend_label = "最近开始活跃" if recent_days_active >= 3 else "偶尔冒泡"

    # 最近情绪
    recent_mood, recent_mood_emoji = _detect_member_daily_mood(recent_msgs)

    # 最近高频词（简单提取）
    if member_names is None:
        member_names = set()
    dynamic_stop = _build_dynamic_stop_words(member_names)
    word_counter = Counter()
    for m in recent_msgs:
        content = strip_mentions((m.get("content") or "").strip(), member_names)
        clean = WECHAT_EMOJI_PATTERN.sub(
            lambda m2: '' if m2.group(0)[1:-1] in _META_TOKENS else m2.group(0)[1:-1],
            content
        )
        for word in _tokenize_chinese(clean, group_id):
            if word not in dynamic_stop:
                word_counter[word] += 1

    recent_topics = [w for w, _ in word_counter.most_common(5)]

    return {
        "active_trend": active_trend,
        "trend_label": trend_label,
        "recent_topics": recent_topics,
        "recent_mood": recent_mood,
        "recent_mood_emoji": recent_mood_emoji,
        "recent_msg_count": recent_msg_count,
        "recent_days_active": recent_days_active,
    }


def compute_topic_role(messages: list[dict], wxid: str,
                       all_wxids: set[str]) -> dict:
    """计算成员的话题角色

    Returns:
        {role_label, topic_initiation_rate, avg_reply_count}
    """
    from collections import defaultdict

    # 按天分组，判断每天谁第一个发言（话题发起者）
    day_first_speaker = defaultdict(str)
    day_msg_count_by_member = defaultdict(lambda: defaultdict(int))

    for m in messages:
        ft = m.get("formattedTime", "")
        if len(ft) < 10:
            continue
        date = ft[:10]
        mwxid = m.get("wxid", "")
        if not mwxid:
            continue
        day_msg_count_by_member[date][mwxid] += 1
        if not day_first_speaker.get(date):
            # 不是系统消息才算
            if m.get("type") != "系统消息":
                day_first_speaker[date] = mwxid

    if not day_first_speaker:
        return {"role_label": "神秘群友", "topic_initiation_rate": 0, "avg_reply_count": 0}

    # 话题发起率
    total_days = len(day_first_speaker)
    initiated_days = sum(1 for d, w in day_first_speaker.items() if w == wxid)
    initiation_rate = round(initiated_days / total_days, 2) if total_days > 0 else 0

    # 被回复率估算：用已排序的全量消息二分查找，O(n log N) 替代 O(n×N)
    reply_count = 0
    msg_count = 0
    import bisect
    sender_msgs = [m for m in messages if m.get("wxid") == wxid]
    sender_msgs.sort(key=lambda x: x.get("createTime", 0))
    # 预建其他成员的时间戳索引（只建一次）
    other_ts = sorted(m.get("createTime", 0) for m in messages
                      if m.get("wxid") != wxid and m.get("wxid") and m.get("createTime", 0))
    for sm in sender_msgs:
        ts = sm.get("createTime", 0)
        if not ts:
            continue
        msg_count += 1
        # 二分查找第一个在 ts 之后的消息
        idx = bisect.bisect_right(other_ts, ts)
        if idx < len(other_ts) and other_ts[idx] - ts <= 300:
            reply_count += 1

    avg_reply = round(reply_count / max(msg_count, 1), 2)

    if initiation_rate >= 0.3:
        role_label = "话题发起者 🔥"
    elif avg_reply >= 0.4:
        role_label = "话题中心 💬"
    elif msg_count > 0 and reply_count < msg_count * 0.1:
        role_label = "话题终结者 🛑"
    elif initiation_rate >= 0.1:
        role_label = "跟风达人 🌊"
    else:
        role_label = "安静听众 👂"

    return {
        "role_label": role_label,
        "topic_initiation_rate": initiation_rate,
        "avg_reply_count": avg_reply,
    }


def compute_highlight_quotes(group_id: int, wxid: str, member_name: str,
                             messages: list[dict]) -> list[dict]:
    """从 daily_reports 的 funny_quotes 中提取该成员的精彩发言

    Returns:
        [{date, content, context}] 最多 3 条
    """
    import json
    from models.database import get_conn

    quotes = []
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT date, report_json FROM daily_reports WHERE group_id=? ORDER BY date DESC",
            (group_id,)
        ).fetchall()
        conn.close()

        for row in rows:
            date = row["date"]
            if not row["report_json"]:
                continue
            try:
                rj = json.loads(row["report_json"])
                funny_quotes = rj.get("funny_quotes", [])
                for q in funny_quotes:
                    speaker = q.get("speaker", "")
                    if speaker in member_name or member_name in speaker:
                        quotes.append({
                            "date": date,
                            "content": q.get("quote", "")[:100],
                            "comment": q.get("comment", ""),
                        })
                        if len(quotes) >= 3:
                            return quotes
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"成员精彩发言: 日报 JSON 损坏 date={date}")
                continue
    except Exception as e:
        logger.warning("查询成员精彩发言失败: %s", e)

    # 如果没有找到，从该成员的消息中挑最长的一条作为亮点
    if not quotes and messages:
        text_msgs = [m for m in messages
                     if m.get("wxid") == wxid
                     and m.get("type") == "文本消息"
                     and len((m.get("content") or "").strip()) >= 10]
        if text_msgs:
            longest = max(text_msgs, key=lambda m: len((m.get("content") or "").strip()))
            quotes.append({
                "date": longest.get("formattedTime", "")[:10],
                "content": (longest.get("content") or "").strip()[:100],
                "comment": "",
            })

    return quotes


def detect_bursting_keywords(messages: list[dict],
                              prev_messages: list[dict],
                              member_names: set[str] = None,
                              group_id: int = 0,
                              min_growth: float = 2.0,
                              min_count: int = 10) -> list[dict]:
    """检测词频突变（新梗发现）

    对比本月与上月的词频，找出增长显著的词。

    Args:
        messages: 本月消息列表
        prev_messages: 上月消息列表
        member_names: 群成员名字集合（用于构建停用词）
        min_growth: 最小增长率（默认 2.0 = 200%）
        min_count: 本月最少出现次数（避免低频噪音）

    Returns:
        [{word, this_count, prev_count, growth_rate}] 按增长率降序，最多 15 个
    """
    from collections import Counter

    if member_names is None:
        member_names = set()
    dynamic_stop = _build_dynamic_stop_words(member_names)

    def _extract_words(msgs: list[dict]) -> Counter:
        counter = Counter()
        for m in msgs:
            content = strip_mentions((m.get("content") or "").strip(), member_names)
            clean = WECHAT_EMOJI_PATTERN.sub(
                lambda m2: '' if m2.group(0)[1:-1] in _META_TOKENS else m2.group(0)[1:-1],
                content
            )
            for word in _tokenize_chinese(clean, group_id):
                if word not in dynamic_stop:
                    counter[word] += 1
        return counter

    this_words = _extract_words(messages)
    prev_words = _extract_words(prev_messages)

    bursting = []
    for word, this_count in this_words.items():
        if this_count < min_count:
            continue
        prev_count = prev_words.get(word, 0)
        if prev_count == 0:
            if this_count >= min_count * 2:
                growth = float('inf')
                bursting.append({
                    "word": word, "this_count": this_count,
                    "prev_count": 0, "growth_rate": growth,
                })
        else:
            growth = this_count / prev_count
            if growth >= min_growth:
                bursting.append({
                    "word": word, "this_count": this_count,
                    "prev_count": prev_count, "growth_rate": round(growth, 1),
                })

    bursting.sort(key=lambda x: x["growth_rate"], reverse=True)
    return bursting[:15]
