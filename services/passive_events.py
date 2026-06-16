"""
v1.16.3: 静默鱼塘被动事件引擎（分组概率制）

定时触发随机事件：6组概率 → 组内随机。
包含：熟练加值、性格修正、金库进账、遗言、状态语
"""
import random
import json as _json
import logging
from datetime import datetime, timedelta

from services import d20 as d20lib
from models import database as db

logger = logging.getLogger(__name__)


def _load_custom_texts(key: str) -> list:
    """从 app_settings 加载用户自定义文本（JSON 数组），与内置池合并"""
    try:
        from config import config as _cfg
        raw = getattr(_cfg, key.upper(), "[]")
        if isinstance(raw, str):
            parsed = _json.loads(raw) if raw.strip() else []
            return parsed if isinstance(parsed, list) else []
        return []
    except Exception:
        return []


def get_merged_flavor_events() -> list:
    """合并内置 + 用户自定义风味文本"""
    custom = _load_custom_texts("custom_flavor_texts")
    return FLAVOR_EVENTS + custom


def get_merged_last_words() -> list:
    """合并内置 + 用户自定义遗言"""
    custom = _load_custom_texts("custom_last_words")
    return FISH_LAST_WORDS + custom


def get_merged_bored_statuses() -> list:
    """合并内置 + 用户自定义状态语"""
    custom = _load_custom_texts("custom_daily_status")
    return BORED_STATUSES + custom


# ==================== v1.16.3: 分组事件池 ====================

# 危险事件（6 种）：高风险高回报
DANGER_EVENTS = [
    ("shark_attack", "🦈 大白鲨来袭", "strength", 12,
     {"xp": 10, "coins": 15, "desc": "勇敢击退鲨鱼"},
     {"hp_loss": "2d4", "desc": "被鲨鱼咬伤"},
     {"勇敢": "advantage", "胆小": "disadvantage"}),
    ("storm", "🌊 暴风雨", "constitution", 10,
     {"energy_restore": 10, "xp": 3, "desc": "风雨洗礼更坚强"},
     {"hp_loss": "1d3", "energy_loss": 5, "desc": "被暴风雨刮伤"},
     {"沉稳": "advantage", "胆小": "disadvantage"}),
    ("acid_rain", "⚡ 酸雨", "constitution", 12,
     {"random_attr": 1, "xp": 4, "desc": "酸雨淬炼变强"},
     {"growth_loss": 5, "hp_loss": "1d4", "desc": "被酸雨腐蚀"},
     {}),
    ("mystic_kelp", "🍄 神秘海藻", "constitution", 10,
     {"random_attr": 1, "xp": 2, "desc": "尝百草长见识"},
     {"hp_loss": "1d4", "energy_loss": 10, "desc": "吃坏肚子"},
     {}),
    ("fishhook", "🎣 鱼钩陷阱", "dexterity", 10,
     {"coins": 5, "xp": 3, "desc": "机智逃脱"},
     {"hp_loss": "1d6", "desc": "被鱼钩划伤"},
     {"谨慎": "advantage"}),
    ("ink_attack", "🦑 墨汁偷袭", "dexterity", 10,
     {"xp": 2, "desc": "敏捷躲开"},
     {"happiness": -5, "desc": "被喷一脸"},
     {"胆小": "disadvantage"}),
]

# 机遇事件（6 种）：低风险，主要给奖励
LUCKY_EVENTS = [
    ("treasure", "💎 沉船宝藏", "wisdom", 10,
     {"coins": "2d10", "xp": 3, "desc": "发现金币"},
     {"desc": "无功而返"},
     {"好奇": "advantage"}),
    ("siren", "🧜 人鱼诱惑", "charisma", 12,
     {"happiness": 20, "xp": 2, "desc": "被人鱼夸奖"},
     {"energy_loss": 20, "desc": "追太远了累坏了"},
     {"社牛": "advantage"}),
    ("wishing_star", "🌟 流星许愿", "wisdom", 15,
     {"wishing_star": True, "xp": 5, "desc": "愿望实现"},
     {"desc": "愿望落空"},
     {}),
    ("magnet", "🧲 磁石吸走了鳞币", "dexterity", 10,
     {"coins": "2d6", "xp": 3, "desc": "抢回鳞币"},
     {"coins": "-1d6", "desc": "损失鳞币"},
     {"谨慎": "advantage"}),
    ("drift_bottle", "📦 漂流瓶", "wisdom", 8,
     {"next_advantage": True, "xp": 3, "desc": "瓶中信带来好运"},
     {"desc": "瓶子里是垃圾邮件"},
     {"好奇": "advantage"}),
    ("coral_maze", "🪸 珊瑚迷宫", "intelligence", 12,
     {"coins": 10, "xp": 3, "desc": "找到出口"},
     {"energy_loss": 10, "desc": "在迷宫中迷路了"},
     {"机灵": "advantage"}),
]

# 挑战事件（4 种）：排名制
CHALLENGE_EVENTS = [
    ("race", "🏁 洋流竞速", "race", "dexterity",
     [(30, 5), (20, 3), (10, 1)]),
    ("beauty_contest", "👑 鳞光选美", "beauty", "charisma",
     [(50, 3), (30, 2), (15, 1)]),
    ("bubble_ring", "🫧 气泡环挑战", "race", "dexterity",
     [(15, 5), (10, 3), (5, 1)]),
    ("concert", "🎵 水下音乐会", "beauty", "charisma",
     [(0, 2), (0, 1), (0, 0)]),
]

# 福利事件（4 种）：无检定，纯增益
WELFARE_EVENTS = [
    ("warm_current", "🌈 洋流送暖",
     {"growth": 5, "happiness": 5, "energy_restore": 10, "desc": "暖流拂过"}),
    ("food_ship", "🍞 投食船经过",
     {"auto_feed": True, "energy_restore": 5, "happiness": 3, "desc": "天上掉鱼食"}),
    ("bubble_party", "🫧 泡泡派对",
     {"happiness": 10, "energy_restore": 5, "desc": "泡泡派对真开心"}),
    ("fish_flu", "🤒 鱼流感",
     {"desc": "免疫成功"},  # 特殊：群体检定，成功免疫
     ),
]

# 稀有事件（5 种）
RARE_EVENTS = [
    ("mutation", "🧬 基因突变", {"mutation": True}),
    ("ghost_tide", "👻 幽灵鱼潮", {"revive": True}),
    ("carnival", "🎪 鱼群嘉年华", {"full_energy": True}),
    ("hot_spring", "🌋 海底热泉", {"hot_spring": True}),
    ("cold_wave", "🧊 寒流来袭", {"cold_wave": True}),
]

# 分组概率
GROUP_PROBABILITIES = {
    "danger": 15,
    "lucky": 25,
    "challenge": 20,
    "welfare": 10,
    "rare": 6,
    # flavor: 24% 兜底
}

# 属性 → 熟练项映射
ATTR_TO_PROFICIENCIES = {
    "strength": ["athletics"],
    "dexterity": ["acrobatics", "stealth"],
    "constitution": ["endurance"],
    "intelligence": ["investigation"],
    "wisdom": ["insight", "nature"],
    "charisma": ["performance", "intimidation"],
}


# ==================== 风味文本（50 条）====================

FLAVOR_EVENTS = [
    # 外来访客
    "一只海龟慢悠悠地游过鱼塘上空，所有鱼抬头行注目礼。它只是路过。",
    "一只水黾在水面上滑行，斗鱼追了它三圈没追上。颜面尽失。",
    "一只蜻蜓在鱼塘上方盘旋。全体鱼屏住呼吸。蜻蜓飞走了。继续发呆。",
    "一条不知从哪来的泥鳅在沙子里钻来钻去，把大家都吵醒了。又走了。",
    "一只青蛙跳进了鱼塘。全体鱼紧张围观。青蛙泡了五分钟澡，走了。",
    "水面上落下一片羽毛。小丑鱼把它顶在头上当帽子。两分钟后漂走了。",
    "一只田螺慢吞吞地从鱼塘这头爬到那头。全程历时四小时。没有鱼关注。",
    # 人类迷惑行为
    "水面上飘来一片薯片包装袋。锦鲤顶了一下——烧烤味的。大家纷纷表示失望。",
    "有人往水里扔了一枚硬币。章鱼捡起来研究——是游戏币。一文不值。",
    "远处传来渔船引擎声，全体鱼紧急避险——结果是塘主在调试遥控船。",
    "塘主路过鱼塘撒了一把鱼食。所有鱼蜂拥而上——发现只是塘主在挥手。",
    "一个小孩趴在鱼塘边看了十分钟。选出了\"最喜欢的鱼\"。获奖者：河豚。理由是\"胖\"。",
    "塘主的朋友来参观，指着鲨鱼问\"这个能吃吗\"。鲨鱼听到了。气氛尴尬。",
    # 鱼之间互动
    "金鱼打了个哈欠，引起连锁反应——所有鱼都打了一遍哈欠。鱼类哈欠传染学说仍在论证中。",
    "斗鱼和龙鱼在石头后面开了个\"秘密会议\"。内容不详。塘主怀疑在密谋造反。",
    "小丑鱼和大鲨鱼开始比赛谁游得快。大鲨鱼赢了。但小丑鱼说它\"让着它\"。",
    "章鱼用触手给鱿鱼编了个辫子。鱿鱼不喜欢。跑去找塘主投诉。",
    "两条锦鲤在轮流吐泡泡圈。越吐越大。最大的那个飘到水面破了。大家鼓掌。",
    "神仙鱼试图和水草对话。水草没有回应。神仙鱼表示\"它今天心情不好\"。",
    "鳄鱼在假装浮木。没人被骗。但大家还是很配合地绕道走。",
    "河豚突然膨胀了。原因是斗鱼从背后吓了它一跳。河豚表示\"再这样我就一辈子不缩回去了\"。",
    # 奇怪现象
    "鱼塘水温突然升高了 0.5 度。龙鱼表示\"就这？\"。其他鱼已经热得吐泡泡。",
    "水底气泡突然冒出一串——是鱿鱼在练喷气加速。喷歪了，撞到石头。正在揉头。",
    "鱼塘角落的水草里传来可疑的咕噜声——河豚在打嗝。已经打了十分钟了。",
    "小丑鱼发现一块反光玻璃片，对着照了半小时镜子。得出结论：\"今天气色不错\"。",
    "一阵微风吹过，水面泛起涟漪。章鱼说这是\"蝴蝶效应\"。神仙鱼追问蝴蝶是什么。",
    "鱼塘的灯管闪了两下。全体鱼以为要开派对。结果是灯管老化了。很失望。",
    "金鱼说自己听到了远处海的声音。其他鱼认为它在吹牛。鱼塘离海几百公里。",
    # 塘主日常
    "塘主在鱼塘边吃泡面。全体鱼贴在玻璃上围观。塘主假装没看到。",
    "塘主在鱼塘边接了个电话。聊了二十分钟。神仙鱼听完了全程。表示\"他下周要出差\"。",
    "塘主给鱼塘装了新温度计。章鱼上去检测——用触手量了三遍。报告：温度计是准的。",
    "半夜鱼塘监控拍到一个黑影——是塘主穿着睡衣在数鱼。一条、两条、三条...他在笑。",
    # 内卷/摆烂
    "龙鱼凌晨四点开始训练。被其他鱼联名举报\"内卷\"。龙鱼表示\"我只是睡不着\"。",
    "懒惰的鱼们召开\"摆烂大会\"。会议决议：今日集体漂浮不动。参会鱼全员赞成。全员睡着。",
    "章鱼制定了一份《鱼塘效率提升方案》。被全体鱼否决。章鱼很伤心，去角落看书了。",
    "勤奋的鱼自发组织了晨练。参加者：1条。迟到者：0条。中途退场者：1条。活动圆满结束。",
    # v1.16.3: 鱼塘八卦
    "锦鲤和斗鱼被看到在同一片水草后面待了很久。双方均拒绝回应。",
    "小丑鱼今天换了三次窝。邻居怀疑它在躲谁。也可能是水草过敏。",
    "章鱼写了一封匿名情书。收到信的河豚表示\"字迹太明显了\"。",
    "龙鱼被认为和隔壁鱼塘的一条锦鲤有联系。消息来源：一只路过的大雁。",
    "海豹声称自己减肥成功。其他鱼表示看不出区别。海豹生气了。",
    "神仙鱼预言本周会下雨。被问及细节时表示\"天机不可泄露\"。本周已过半。",
    "水獭和海獭建立了\"獭獭联盟\"。目前唯一的成果是一起吃贝壳。",
    # v1.16.3: 深夜频道
    "凌晨两点，斗鱼独自在水面浮着。他说在看星星。鱼塘是室内的。",
    "章鱼半夜在写东西。用触手。同时写八行。没人看得懂。",
    "金鱼半夜惊醒。她说做了个噩梦。梦见鱼食吃完了。大家安慰了她。",
    "夜深了。鳄鱼假装浮木。这次比白天更像。可能是因为天黑的加成。",
    "半夜水草传来窸窣声。是海螺在梦游。他白天睡了十八个小时。",
    "凌晨四点。勤奋的鱼和熬夜的鱼在角落相遇。双方都很尴尬。",
    "深夜鱼塘很安静。只有气泡偶尔冒出的声音。和章鱼的键盘声。",
]

# 鱼之遗言（20 条）
FISH_LAST_WORDS = [
    "告诉塘主...我柜子里还有三颗鱼食没吃...",
    "我这辈子最大的遗憾，就是没见过彩虹天气。",
    "别让斗鱼那小子继承我的鳞币！！",
    "其实...我一直知道自己不是锦鲤...别告诉我妈。",
    "水有点凉。帮我调高一度。算了来不及了。",
    "遗产：一块反光玻璃碎片，留给小丑鱼。它觊觎很久了。",
    "下一世我要当鲸鱼。",
    "记得把我的鳞币...捐给鱼塘...算了还是烧给我吧。",
    "我这短暂的一生，最骄傲的事就是那次选美第三名。虽然是并列的。",
    "再见了朋友们。尤其是斗鱼。我不是针对你。我是针对所有鱼。",
    # v1.16.3 新增
    "我走了以后...记得每天喂食。虽然你们从来不需要我提醒。",
    "其实我偷偷藏了三枚鳞币在石头下面。算了现在说出来也没关系了。",
    "下一世我要当海龟。壳厚。活得久。",
    "别难过。每条鱼都会游向大海。只是我稍微提前了一点。",
    "告诉章鱼，它的效率提升方案其实写得挺好的。",
    "我这辈子最大的成就：那次竞速第三名。虽然是倒数第三。",
    "水还是那么清。天还是那么蓝。只是我该走了。",
    "把我的海藻分给新来的鱼。它看起来饿了。",
    "如果有来生，我要当一条咸鱼。不用训练，不用内卷。",
    "再见鱼塘。再见塘主。再见...等等我忘了谁的名字...",
]


# ==================== 核心逻辑 ====================

def _has_proficiency(fish: dict, attr_key: str) -> bool:
    """检查鱼是否有某属性对应的熟练项"""
    from services.fish_pond import get_proficiencies
    profs = get_proficiencies(fish.get("species", ""))
    targets = ATTR_TO_PROFICIENCIES.get(attr_key, [])
    return any(p in profs for p in targets)


def _apply_traits_to_check(fish: dict, trait_mods: dict):
    """根据性格修正返回 advantage/disadvantage"""
    import json as _json
    traits_raw = fish.get("personality_traits", "[]")
    try:
        traits = _json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
    except (_json.JSONDecodeError, TypeError):
        traits = []

    advantage = False
    disadvantage = False
    for trait in traits:
        mod = trait_mods.get(trait, "")
        if mod == "advantage":
            advantage = True
        elif mod == "disadvantage":
            disadvantage = True

    if advantage and disadvantage:
        advantage = disadvantage = False
    return advantage, disadvantage


def _apply_effects(group_id: int, wxid: str, effects: dict, fish: dict):
    """应用事件效果到鱼"""
    if "xp" in effects:
        from services.fish_pond import add_xp
        add_xp(group_id, wxid, effects["xp"], "passive_event")

    if "coins" in effects:
        coins = effects["coins"]
        if isinstance(coins, str):
            coins = d20lib.coin_roll(coins)
        if coins < 0:
            db.spend_coins(group_id, wxid, -coins, "event_loss",
                           effects.get("desc", "事件损失"))
        elif coins > 0:
            db.earn_coins(group_id, wxid, coins, "event",
                          effects.get("desc", "事件获得"))

    if "growth" in effects:
        g = max(0, fish.get("growth", 0) + effects["growth"])
        db.update_fish_field(group_id, wxid, "growth", g)
    if "growth_loss" in effects:
        g = max(0, fish.get("growth", 0) - effects["growth_loss"])
        db.update_fish_field(group_id, wxid, "growth", g)
    if "happiness" in effects:
        h = max(0, min(100, fish.get("happiness", 50) + effects["happiness"]))
        db.update_fish_field(group_id, wxid, "happiness", h)
    if "hp_loss" in effects:
        loss = effects["hp_loss"]
        if isinstance(loss, str):
            loss = d20lib.coin_roll(loss)
        new_hp = max(0, fish.get("hp", 20) - loss)
        db.update_fish_field(group_id, wxid, "hp", new_hp)
        if new_hp <= 0:
            _kill_fish(group_id, wxid, fish, effects.get("desc", "事件致死"))
    if "hp_heal" in effects:
        new_hp = min(fish.get("max_hp", 20), fish.get("hp", 20) + effects["hp_heal"])
        db.update_fish_field(group_id, wxid, "hp", new_hp)
    if "energy_loss" in effects:
        db.update_fish_energy(group_id, wxid, effects["energy_loss"])
    if "energy_restore" in effects:
        db.update_fish_energy(group_id, wxid, -effects["energy_restore"])
    if "random_attr" in effects:
        attrs = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
        attr = random.choice(attrs)
        new_val = fish.get(attr, 10) + effects["random_attr"]
        db.update_fish_field(group_id, wxid, attr, new_val)
    if "auto_feed" in effects:
        from datetime import datetime as _dt
        db.update_fish_field(group_id, wxid, "growth", fish.get("growth", 0) + 5)
        db.update_fish_field(group_id, wxid, "last_fed_date",
                           _dt.now().strftime("%Y-%m-%d"))


def _kill_fish(group_id: int, wxid: str, fish: dict, cause: str):
    """鱼死亡 + 遗言"""
    db.mark_fish_dead(group_id, wxid)
    last_words = random.choice(get_merged_last_words())
    db.add_fish_event(group_id, wxid, "death", {
        "fish_name": fish["fish_name"], "cause": cause,
        "last_words": last_words,
    })
    logger.info(f"鱼死亡: group={group_id} {fish['fish_name']} — {last_words}")


def _execute_single_event(group_id: int, event, fish: dict) -> dict:
    """执行单体事件（带熟练加值和性格修正）"""
    evt_type, name, attr_key, dc, success_eff, fail_eff, trait_mods = event
    wxid = fish["wxid"]

    advantage, disadvantage = _apply_traits_to_check(fish, trait_mods)
    score = fish.get(attr_key, 10)
    is_prof = _has_proficiency(fish, attr_key)
    level = fish.get("level", 1)

    result = d20lib.ability_check(score, dc=dc, is_proficient=is_prof,
                                  level=level, advantage=advantage,
                                  disadvantage=disadvantage)

    event_data = {"name": name, "dc": dc, "attr": attr_key,
                  "fish_name": fish["fish_name"],
                  "check": result.to_dict()}

    if result.success:
        _apply_effects(group_id, wxid, success_eff, fish)
        event_data.update({k: v for k, v in success_eff.items() if k != "desc"})
    else:
        _apply_effects(group_id, wxid, fail_eff, fish)
        event_data.update({k: v for k, v in fail_eff.items() if k != "desc"})

    db.add_fish_event(group_id, wxid, evt_type, event_data)
    return {"type": evt_type, "name": name, "wxid": wxid,
            "fish_name": fish["fish_name"], "success": result.success}


def _execute_multi_event(group_id: int, event, alive_fish: list,
                         rng: random.Random) -> dict:
    """执行群体事件"""
    evt_type, name, mode, attr_key, top3_rewards = event

    if mode == "race":
        scores = []
        for fish in alive_fish:
            score = fish.get(attr_key, 10)
            is_prof = _has_proficiency(fish, attr_key)
            level = fish.get("level", 1)
            check = d20lib.ability_check(score, dc=0, is_proficient=is_prof,
                                         level=level)
            scores.append((fish, check.roll + check.modifier))
        scores.sort(key=lambda x: -x[1])
        results = []
        for i, (f, total) in enumerate(scores):
            rank = i + 1
            entry = {"wxid": f["wxid"], "fish_name": f["fish_name"],
                     "total": total, "rank": rank}
            if rank <= 3:
                coins, xp = top3_rewards[rank - 1]
                if coins:
                    db.earn_coins(group_id, f["wxid"], coins, "race",
                                  f"竞速第{rank}名")
                if xp:
                    from services.fish_pond import add_xp
                    add_xp(group_id, f["wxid"], xp, "race")
                entry["coins"] = coins
                entry["xp"] = xp
            results.append(entry)
        db.add_fish_event(group_id, "", evt_type,
                          {"name": name, "race_results": results})
        return {"type": evt_type, "name": name, "race_results": results[:3]}

    if mode == "beauty":
        scores = []
        for fish in alive_fish:
            score = fish.get(attr_key, 10)
            is_prof = _has_proficiency(fish, attr_key)
            level = fish.get("level", 1)
            check = d20lib.ability_check(score, dc=0, is_proficient=is_prof,
                                         level=level)
            scores.append((fish, check.roll + check.modifier))
        scores.sort(key=lambda x: -x[1])
        results = []
        for i, (f, total) in enumerate(scores):
            rank = i + 1
            entry = {"wxid": f["wxid"], "fish_name": f["fish_name"],
                     "total": total, "rank": rank}
            if rank <= 3:
                coins, xp = top3_rewards[rank - 1]
                if coins:
                    db.earn_coins(group_id, f["wxid"], coins, "beauty",
                                  f"选美第{rank}名")
                if xp:
                    from services.fish_pond import add_xp
                    add_xp(group_id, f["wxid"], xp, "beauty")
                entry["coins"] = coins
                entry["xp"] = xp
            results.append(entry)
        db.add_fish_event(group_id, "", evt_type,
                          {"name": name, "beauty_results": results})
        return {"type": evt_type, "name": name, "beauty_results": results[:2]}

    return {"type": evt_type, "name": name}


def _execute_rare_event(group_id: int, evt_type: str, name: str,
                        effect: dict, alive_fish: list) -> dict:
    """执行稀有事件"""
    result = {"type": evt_type, "name": name}
    rng = random.Random(f"rare_{group_id}_{datetime.now().timestamp()}")

    if effect.get("mutation"):
        target = rng.choice(alive_fish)
        species_list = [k for k in AQUATIC_SPECIES if k != target.get("species")]
        new_species = rng.choice(species_list)
        db.update_fish_field(group_id, target["wxid"], "species", new_species)
        db.add_fish_event(group_id, target["wxid"], "mutation", {
            "fish_name": target["fish_name"],
            "new_species": AQUATIC_SPECIES[new_species]["name"],
            "success": True,
        })
        result["mutation"] = target["fish_name"]

    elif effect.get("revive"):
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        conn = db.get_conn()
        dead = conn.execute(
            """SELECT * FROM fish_pond WHERE group_id=? AND is_alive=0
               AND updated_at >= ? ORDER BY updated_at DESC LIMIT 1""",
            (group_id, cutoff)
        ).fetchone()
        conn.close()
        if dead:
            dead = dict(dead)
            db.update_fish_multi(group_id, dead["wxid"], {"is_alive": 1, "hp": 1})
            db.update_fish_energy(group_id, dead["wxid"], -20)
            db.add_fish_event(group_id, dead["wxid"], "revived",
                            {"fish_name": dead["fish_name"]})
            result["revived"] = dead["fish_name"]

    elif effect.get("full_energy"):
        for fish in alive_fish:
            max_e = fish.get("max_energy", 100)
            cur_e = fish.get("energy", max_e)
            if cur_e < max_e:
                db.update_fish_energy(group_id, fish["wxid"], -(max_e - cur_e))
        db.add_fish_event(group_id, "", "carnival",
                          {"desc": "全体精力全满"})
        result["desc"] = "全体精力全满"

    elif effect.get("hot_spring"):
        targets = rng.sample(alive_fish, min(3, len(alive_fish)))
        names = []
        for t in targets:
            names.append(t["fish_name"])
            db.add_fish_event(group_id, t["wxid"], "hot_spring_buff",
                            {"fish_name": t["fish_name"],
                             "desc": "热泉buff: 3天内成长×2"})
        result["hot_spring"] = names

    elif effect.get("cold_wave"):
        db.add_fish_event(group_id, "", "cold_wave",
                          {"desc": "寒流来袭，下轮事件跳过，宝藏概率翻倍"})
        result["cold_wave"] = True

    db.add_fish_event(group_id, "", evt_type, result)
    return result


def _record_last_event(group_id: int):
    """记录最后事件时间"""
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value, value_type) VALUES (?, ?, 'string') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (f"pond_last_event_at_{group_id}", datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def _treasury_tick(group_id: int):
    """金库进账"""
    try:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT SUM(balance) as total FROM scale_coin_wallet WHERE group_id = ?",
            (group_id,)
        ).fetchone()
        conn.close()
        total_coins = row["total"] if row and row["total"] else 0
        earn = max(3, int(total_coins * 0.05))
        db.add_treasury(group_id, earn, reason="event_tax",
                        desc=f"群鳞币总和 {total_coins} × 5%")
    except Exception as e:
        logger.warning(f"金库进账失败 group={group_id}: {e}")


def generate_daily_status(wxid: str, today_events: list) -> str:
    """根据今日事件生成鱼的状态语（事件驱动拼接，不用 AI）"""
    if not today_events:
        return random.choice(get_merged_bored_statuses())

    for evt in today_events:
        evt_type = evt.get("event_type", evt.get("type", ""))

        if evt_type == "shark_attack":
            data = _parse_event_data(evt)
            if data.get("success"):
                return "今天从鲨鱼嘴里逃出来了！活着真好！！"
            else:
                return None

        if evt_type == "treasure":
            data = _parse_event_data(evt)
            if data.get("success") or data.get("coins"):
                return "捡到金币了！今天运气不错~"

        if evt_type == "evolve" or evt_type == "mutation":
            return "进化了！感觉自己更强了 💪"

        if evt_type == "race":
            data = _parse_event_data(evt)
            race_results = data.get("race_results", [])
            for r in race_results:
                if r.get("wxid") == wxid and r.get("rank") == 1:
                    return "竞速冠军！！我就是鱼塘最快的鱼！"
                if r.get("wxid") == wxid and r.get("rank", 99) > 3:
                    return "竞速没拿名次...下次一定。"

        if evt_type == "revived":
            return "刚从鬼门关回来了...要珍惜每一天。"

    return random.choice(get_merged_bored_statuses())


def _parse_event_data(evt: dict) -> dict:
    """兼容 event_data JSON 字符串"""
    data = evt.get("event_data", {})
    if isinstance(data, str):
        import json
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return {}
    return data or {}


# ==================== 主入口 ====================

# 需要从 fish_pond 导入的延迟引用
AQUATIC_SPECIES = {}
BORED_STATUSES = []


def _init_species_ref():
    """延迟加载物种引用（避免循环导入）"""
    global AQUATIC_SPECIES
    if not AQUATIC_SPECIES:
        from services.fish_pond import AQUATIC_SPECIES as _s
        AQUATIC_SPECIES = _s


BORED_STATUSES = [
    "今天什么都没发生。无聊。但很安全。",
    "又是和平的一天。水很清，心情还行。",
    "平平无奇的一天。至少还活着。",
    "今天没人来看我。有点寂寞。",
    "水温刚好，食物充足。满足。",
    "晒了会儿太阳，鳞片闪闪发光。",
    "看到一只小虾从身边游过，打了个招呼。",
    "今天水草特别嫩，吃得很开心。",
    "在水底打了个盹，做了个关于大海的梦。",
    "和隔壁的鱼互相瞪了一会儿眼。",
    "今天的水流特别舒服，随波逐流了一整天。",
    "听到远处有海豚的声音。",
    "有片叶子落在水面上，看了半天。",
    "今天格外想跳龙门。但懒得动。",
    "感觉今天自己特别好看，在玻璃前照了很久。",
    "有条陌生的鱼从远处游过，没看清是什么品种。",
    "今天的水温正合适，想唱歌。",
    "数了数缸里的石头，还是昨天那几颗。",
    "主人今天好像很忙，没怎么来看我。",
    "感觉最近胖了，明天开始减肥。",
]


def trigger_passive_events(group_id: int) -> list[dict]:
    """主入口：触发一轮被动事件（分组概率制）

    1. 每日结算检查
    2. 恢复精力 +5
    3. 按分组概率骰组 → 组内随机选事件
    4. 风味文本兜底
    5. 金库进账
    """
    _init_species_ref()
    alive = db.get_alive_fish(group_id)
    if not alive:
        return []

    # 检查冷却（同群 15 分钟内不重复触发）
    last_key = f"pond_last_event_at_{group_id}"
    conn = db.get_conn()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (last_key,)
    ).fetchone()
    conn.close()
    if row and row["value"]:
        try:
            last_at = datetime.fromisoformat(row["value"])
            if (datetime.now() - last_at).total_seconds() < 900:
                return []
        except (ValueError, TypeError):
            pass

    events_log = []

    # 0. 每日结算（当天首次触发）
    date_str = datetime.now().strftime("%Y-%m-%d")
    settle_key = f"pond_last_settle_date_{group_id}"
    settle_conn = db.get_conn()
    row = settle_conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (settle_key,)
    ).fetchone()
    need_settle = not (row and row["value"] == date_str)
    if need_settle:
        try:
            from services.fish_pond import settle_all_fish
            settle_result = settle_all_fish(group_id, date_str)
            if settle_result.get("settled"):
                settle_conn.execute(
                    "INSERT INTO app_settings (key, value, value_type) VALUES (?, ?, 'string') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (settle_key, date_str)
                )
                settle_conn.commit()
                events_log.append({"type": "daily_settle",
                                   "weather": settle_result.get("weather")})
                logger.info(f"鱼塘每日结算完成 group={group_id} date={date_str}")
        except Exception as e:
            logger.warning(f"鱼塘每日结算失败 group={group_id}: {e}")
    settle_conn.close()

    # 1. 精力恢复
    from config import config as cfg
    regen_amt = getattr(cfg, "POND_ENERGY_REGEN_AMOUNT", 5)
    for fish in alive:
        import json as _json
        traits_raw = fish.get("personality_traits", "[]")
        try:
            traits = _json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
        except (_json.JSONDecodeError, TypeError):
            traits = []
        amount = regen_amt
        if "懒惰" in traits:
            amount = int(amount * 1.5)
        db.update_fish_energy(group_id, fish["wxid"], -amount)

    # 2. 分组概率判定
    seed_base = f"passive_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    rng = random.Random(seed_base)

    # 攒出总概率条
    groups = ["rare", "danger", "challenge", "lucky", "welfare"]
    roll = rng.randint(1, 100)
    cumulative = 0
    hit_group = None
    for g in groups:
        cumulative += GROUP_PROBABILITIES.get(g, 0)
        if roll <= cumulative:
            hit_group = g
            break

    # 3. 执行命中分组
    if hit_group == "rare":
        evt = rng.choice(RARE_EVENTS)
        evt_type, name, effect = evt
        result = _execute_rare_event(group_id, evt_type, name, effect, alive)
        events_log.append(result)
        _record_last_event(group_id)
        _treasury_tick(group_id)
        return events_log

    elif hit_group == "danger":
        evt = rng.choice(DANGER_EVENTS)
        target = rng.choice(alive)
        result = _execute_single_event(group_id, evt, target)
        events_log.append(result)
        _record_last_event(group_id)
        _treasury_tick(group_id)
        return events_log

    elif hit_group == "lucky":
        evt = rng.choice(LUCKY_EVENTS)
        target = rng.choice(alive)
        result = _execute_single_event(group_id, evt, target)
        events_log.append(result)
        _record_last_event(group_id)
        _treasury_tick(group_id)
        return events_log

    elif hit_group == "challenge":
        evt = rng.choice(CHALLENGE_EVENTS)
        result = _execute_multi_event(group_id, evt, alive, rng)
        events_log.append(result)
        _record_last_event(group_id)
        _treasury_tick(group_id)
        return events_log

    elif hit_group == "welfare":
        evt = rng.choice(WELFARE_EVENTS)
        evt_type = evt[0]
        name = evt[1]

        if evt_type == "fish_flu":
            # 鱼流感：群体 CON 检定
            success_count = 0
            for fish in alive:
                score = fish.get("constitution", 10)
                is_prof = _has_proficiency(fish, "constitution")
                level = fish.get("level", 1)
                check = d20lib.ability_check(score, dc=12, is_proficient=is_prof,
                                             level=level)
                if check.success:
                    success_count += 1
                    from services.fish_pond import add_xp
                    add_xp(group_id, fish["wxid"], 3, "immune")
                else:
                    g = max(0, fish.get("growth", 0) - 10)
                    db.update_fish_field(group_id, fish["wxid"], "growth", g)
                    db.update_fish_energy(group_id, fish["wxid"], 15)
            db.add_fish_event(group_id, "", "fish_flu",
                            {"name": name, "immune_count": success_count})
            events_log.append({"type": "fish_flu", "name": name,
                              "immune": success_count,
                              "total": len(alive)})
        else:
            # 纯福利事件：全体生效
            effects = evt[2]
            for fish in alive:
                _apply_effects(group_id, fish["wxid"], effects, fish)
            db.add_fish_event(group_id, "", evt_type,
                            {"name": name, **effects})
            events_log.append({"type": evt_type, "name": name,
                              "effects": effects})

        _record_last_event(group_id)
        _treasury_tick(group_id)
        return events_log

    # 4. 风味文本兜底
    flavor = rng.choice(get_merged_flavor_events())
    events_log.append({"type": "flavor", "flavor_text": flavor})
    db.add_fish_event(group_id, "", "flavor", {"text": flavor})
    _record_last_event(group_id)
    return events_log
