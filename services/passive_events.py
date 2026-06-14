"""
v1.16.1: 静默鱼塘被动事件引擎

定时触发随机事件：单体/群体/稀有事件 + 风味文本兜底
包含：金库进账、鱼之遗言、今日状态语生成
"""
import random
import logging
from datetime import datetime, timedelta

from services import d20 as d20lib
from models import database as db

logger = logging.getLogger(__name__)


# ==================== 事件池 ====================

# 单体事件：(event_type, 概率%, 名称, DC属性, DC值, 成功效果, 失败效果, 性格修正key)
SINGLE_EVENTS = [
    ("shark_attack", 10, "🦈 大白鲨来袭", "strength", 12,
     {"xp": 2, "coins": 5, "desc": "勇敢击退鲨鱼"},
     {"hp_loss": "2d4", "desc": "被鲨鱼咬伤"},
     {"勇敢": "advantage", "胆小": "disadvantage"}),
    ("treasure", 12, "💎 沉船宝藏", "wisdom", 10,
     {"coins": "2d10", "desc": "发现金币"},
     {"desc": "无功而返"},
     {"好奇": "advantage"}),
    ("mystic_kelp", 8, "🍄 神秘海藻", "constitution", 10,
     {"random_attr": 1, "desc": "属性+1"},
     {"hp_loss": "1d4", "energy_loss": 10, "desc": "吃坏肚子"},
     {}),
    ("fish_flu", 8, "🤒 鱼流感", "constitution", 12,
     {"desc": "免疫成功"},
     {"growth_loss": 10, "energy_loss": 15, "desc": "感染流感"},
     {}),
    ("siren", 7, "🧜 人鱼诱惑", "charisma", 12,
     {"happiness": 20, "desc": "被人鱼夸奖"},
     {"energy_loss": 20, "desc": "追太远了累坏了"},
     {"社牛": "advantage"}),
    ("fishhook", 8, "🎣 鱼钩陷阱", "dexterity", 10,
     {"coins": 5, "desc": "机智逃脱"},
     {"hp_loss": "1d6", "desc": "被鱼钩划伤"},
     {"谨慎": "advantage"}),
    ("wishing_star", 4, "🌟 流星许愿", "wisdom", 15,
     {"wishing_star": True, "desc": "愿望实现"},
     {"desc": "愿望落空"},
     {}),
]

# 群体事件：(event_type, 概率%, 名称, 有检定?, DC属性, DC值, 成功效果, 失败效果, 性格修正)
MULTI_EVENTS = [
    ("race", 10, "🏁 洋流竞速", "race", "dexterity", None,
     {"top3_reward": [(30, 5), (20, 3), (10, 1)], "desc": "竞速排名"},
     {},
     {}),
    ("storm", 10, "🌊 暴风雨", "check", "constitution", 10,
     {},
     {"hp_loss": "1d4", "energy_loss": 5, "desc": "被暴风雨刮伤"},
     {"沉稳": "advantage", "胆小": "disadvantage"}),
    ("warm_current", 8, "🌈 洋流送暖", None, None, None,
     {"growth": 5, "happiness": 5, "energy_restore": 10, "desc": "暖流拂过"},
     {},
     {}),
    ("beauty_contest", 6, "👑 鳞光选美", "beauty", "charisma", None,
     {"top3_reward": [(50, 0), (30, 0), (15, 0)], "desc": "选美排名"},
     {},
     {"社牛": "advantage", "傲娇": "advantage"}),
    ("acid_rain", 6, "⚡ 酸雨", "check", "constitution", 12,
     {},
     {"growth_loss": 5, "hp_loss": "1d6", "desc": "被酸雨腐蚀"},
     {}),
    ("food_ship", 7, "🍞 投食船经过", None, None, None,
     {"auto_feed": True, "energy_restore": 5, "happiness": 3, "desc": "天上掉鱼食"},
     {},
     {}),
]

# 稀有事件：(event_type, 概率%, 名称, 效果)
RARE_EVENTS = [
    ("mutation", 1, "🧬 基因突变", {"mutation": True}),
    ("ghost_tide", 2, "👻 幽灵鱼潮", {"revive": True}),
    ("carnival", 3, "🎪 鱼群嘉年华", {"full_energy": True, "random_item": True}),
]

# 风味文本（35 条，不产生任何机制效果）
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
]

# 鱼之遗言（10 条）
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
]

# 今日状态语：无聊默认
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


# ==================== 核心逻辑 ====================

def trigger_passive_events(group_id: int) -> list[dict]:
    """主入口：触发一轮被动事件

    1. 恢复所有鱼精力 +5
    2. 检查冷却
    3. 判定并执行事件
    4. 金库进账
    返回本轮事件列表（含风味文本）
    """
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
            if (datetime.now() - last_at).total_seconds() < 900:  # 15 min
                return []
        except (ValueError, TypeError):
            pass

    events_log = []

    # 0. 每日结算（当天首次触发时执行一次，异常不影响后续事件）
    date_str = datetime.now().strftime("%Y-%m-%d")
    settle_key = f"pond_last_settle_date_{group_id}"
    settle_conn = db.get_conn()
    row = settle_conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (settle_key,)
    ).fetchone()
    need_settle = True
    if row and row["value"]:
        need_settle = row["value"] != date_str
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
                events_log.append({"type": "daily_settle", "weather": settle_result.get("weather")})
                logger.info(f"鱼塘每日结算完成 group={group_id} date={date_str} "
                           f"fish={settle_result.get('fish_count', 0)}")
        except Exception as e:
            logger.warning(f"鱼塘每日结算失败 group={group_id}: {e}")
    settle_conn.close()

    # 1. 精力恢复
    from config import config as cfg
    regen_amt = getattr(cfg, "POND_ENERGY_REGEN_AMOUNT", 5)
    for fish in alive:
        # 性格修正
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

    # 2. 事件判定
    date_str = datetime.now().strftime("%Y-%m-%d")
    seed_base = f"passive_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    rng = random.Random(seed_base)

    # 稀有事件（1% → 2% → 3%，顺序判定）
    for evt_type, chance, name, effect in RARE_EVENTS:
        if rng.randint(1, 100) <= chance:
            result = _execute_rare_event(group_id, evt_type, name, effect, alive)
            events_log.append(result)
            _record_last_event(group_id)
            _treasury_tick(group_id)
            return events_log

    # 群体事件（累计 ~47%，单个判定）
    total_chance = sum(ch for _, ch, _, _, _, _, _, _, _ in MULTI_EVENTS)
    if rng.randint(1, 100) <= total_chance:
        # 按权重随机选一个
        evt = _weighted_pick(MULTI_EVENTS, rng)
        if evt:
            result = _execute_multi_event(group_id, evt, alive, rng)
            events_log.append(result)
            _record_last_event(group_id)
            _treasury_tick(group_id)
            return events_log

    # 单体事件（累计 ~57%，随机选目标）
    total_single = sum(ch for _, ch, _, _, _, _, _, _ in SINGLE_EVENTS)
    if rng.randint(1, 100) <= total_single:
        evt = _weighted_pick(SINGLE_EVENTS, rng)
        if evt:
            target = rng.choice(alive)
            result = _execute_single_event(group_id, evt, target)
            events_log.append(result)
            _record_last_event(group_id)
            _treasury_tick(group_id)
            return events_log

    # 都没命中 → 风味文本（~30% 剩余概率）
    flavor = rng.choice(FLAVOR_EVENTS)
    events_log.append({"type": "flavor", "flavor_text": flavor})
    db.add_fish_event(group_id, "", "flavor", {"text": flavor})
    _record_last_event(group_id)
    # 风味文本不触发金库进账
    return events_log


def _weighted_pick(events, rng):
    total = sum(ch for _, ch, *_ in events)
    roll = rng.randint(1, total)
    cumulative = 0
    for evt in events:
        cumulative += evt[1]
        if roll <= cumulative:
            return evt
    return events[-1] if events else None


def _execute_single_event(group_id: int, evt, fish: dict) -> dict:
    """执行单体事件"""
    evt_type, chance, name, attr_key, dc, success_eff, fail_eff, trait_mods = evt
    wxid = fish["wxid"]

    # 性格修正
    import json as _json
    traits_raw = fish.get("personality_traits", "[]")
    try:
        traits = _json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
    except (_json.JSONDecodeError, TypeError):
        traits = []

    advantage = False
    disadvantage = False
    for trait in traits:
        if trait in trait_mods:
            if trait_mods[trait] == "advantage":
                advantage = True
            elif trait_mods[trait] == "disadvantage":
                disadvantage = True
    if advantage and disadvantage:
        advantage = disadvantage = False

    # 检定
    score = fish.get(attr_key, 10)
    result = d20lib.ability_check(score, dc=dc, advantage=advantage, disadvantage=disadvantage)

    event_data = {"name": name, "dc": dc, "attr": attr_key, "check": result.to_dict()}
    status = {"type": evt_type, "name": name, "wxid": wxid, "fish_name": fish["fish_name"],
              "success": result.success}

    if result.success:
        _apply_effects(group_id, wxid, success_eff, fish)
        event_data.update(success_eff)
        status["result"] = success_eff.get("desc", "成功")
    else:
        _apply_effects(group_id, wxid, fail_eff, fish)
        event_data.update(fail_eff)
        status["result"] = fail_eff.get("desc", "失败")

    db.add_fish_event(group_id, wxid, evt_type, event_data)
    return status


def _execute_multi_event(group_id: int, evt, alive_fish: list, rng: random.Random) -> dict:
    """执行群体事件"""
    evt_type, chance, name, mode, attr_key, dc, success_eff, fail_eff, trait_mods = evt
    results = []

    if mode == "race":
        # 竞速：所有鱼 DEX 检定，前3获奖
        scores = []
        for fish in alive_fish:
            score = fish.get("dexterity", 10)
            check = d20lib.ability_check(score, dc=0, advantage=False, disadvantage=False)
            scores.append((fish, check.roll + check.modifier))
        scores.sort(key=lambda x: -x[1])
        rewards = success_eff.get("top3_reward", [])
        for i, (fish, total) in enumerate(scores[:3]):
            if i < len(rewards):
                coins, xp = rewards[i]
                if coins:
                    db.earn_coins(group_id, fish["wxid"], coins, "multi_event",
                                  f"{name}第{i+1}名")
                if xp:
                    from services.fish_pond import add_xp
                    add_xp(group_id, fish["wxid"], xp, "multi_event")
            results.append({"wxid": fish["wxid"], "rank": i + 1, "total": total})
        db.add_fish_event(group_id, "", evt_type, {"name": name, "race_results": results})
        return {"type": evt_type, "name": name, "results": results}

    elif mode == "beauty":
        # 选美：所有鱼 CHA 检定，前3获奖
        scores = []
        for fish in alive_fish:
            score = fish.get("charisma", 10)
            adv = False
            if "社牛" in (fish.get("personality_traits") or ""):
                adv = True
            check = d20lib.ability_check(score, dc=0, advantage=adv)
            scores.append((fish, check.roll + check.modifier))
        scores.sort(key=lambda x: -x[1])
        rewards = success_eff.get("top3_reward", [])
        for i, (fish, total) in enumerate(scores[:3]):
            if i < len(rewards):
                coins, _ = rewards[i]
                if coins:
                    db.earn_coins(group_id, fish["wxid"], coins, "beauty_contest",
                                  f"选美第{i+1}名")
            results.append({"wxid": fish["wxid"], "rank": i + 1, "total": total})
        db.add_fish_event(group_id, "", evt_type, {"name": name, "beauty_results": results})
        return {"type": evt_type, "name": name, "results": results}

    elif mode == "check":
        # 全体 DC 检定
        for fish in alive_fish:
            score = fish.get(attr_key, 10)
            import json as _json
            traits_raw = fish.get("personality_traits", "[]")
            try:
                traits = _json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
            except (_json.JSONDecodeError, TypeError):
                traits = []
            advantage = False
            disadvantage = False
            for trait in traits:
                mod = trait_mods.get(trait)
                if mod == "advantage":
                    advantage = True
                elif mod == "disadvantage":
                    disadvantage = True
            if advantage and disadvantage:
                advantage = disadvantage = False
            check = d20lib.ability_check(score, dc=dc, advantage=advantage, disadvantage=disadvantage)
            if not check.success:
                _apply_effects(group_id, fish["wxid"], fail_eff, fish)
                results.append({"wxid": fish["wxid"], "success": False, "check": check.to_dict()})
        db.add_fish_event(group_id, "", evt_type, {"name": name, "results": results})
        return {"type": evt_type, "name": name, "affected": len(results)}

    else:
        # 无检定群体事件（洋流送暖、投食船）
        for fish in alive_fish:
            _apply_effects(group_id, fish["wxid"], success_eff, fish)
        db.add_fish_event(group_id, "", evt_type, {"name": name, **success_eff})
        return {"type": evt_type, "name": name, "effect": success_eff.get("desc", "")}


def _execute_rare_event(group_id: int, evt_type: str, name: str,
                        effect: dict, alive_fish: list) -> dict:
    """执行稀有事件"""
    rng = random.Random(f"rare_{group_id}_{datetime.now().timestamp()}")
    result = {"type": evt_type, "name": name}

    if effect.get("mutation"):
        # 随机选一条鱼变物种
        from services.fish_pond import AQUATIC_SPECIES
        target = rng.choice(alive_fish)
        species_keys = list(AQUATIC_SPECIES.keys())
        new_species = rng.choice([s for s in species_keys if s != target["species"]])
        db.update_fish_field(group_id, target["wxid"], "species", new_species)
        db.add_fish_event(group_id, target["wxid"], "mutation",
                          {"old_species": target["species"], "new_species": new_species})
        result["mutation"] = {"wxid": target["wxid"], "from": target["species"], "to": new_species}

    elif effect.get("revive"):
        # 复活一只死 ≤7 天的鱼
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        conn = db.get_conn()
        dead = conn.execute(
            """SELECT * FROM fish_pond WHERE group_id=? AND is_alive=0
               AND updated_at >= ? ORDER BY updated_at DESC LIMIT 1""",
            (group_id, cutoff)
        ).fetchone()
        conn.close()
        if dead:
            db.update_fish_multi(group_id, dead["wxid"], {"is_alive": 1, "hp": 1})
            db.update_fish_energy(group_id, dead["wxid"], -20)  # restore 20 energy
            db.add_fish_event(group_id, dead["wxid"], "revived",
                              {"fish_name": dead["fish_name"]})
            result["revived"] = dead["fish_name"]
        else:
            result["revived"] = None

    elif effect.get("full_energy"):
        for fish in alive_fish:
            max_e = fish.get("max_energy", 100)
            current = fish.get("energy", 100)
            if current < max_e:
                db.update_fish_energy(group_id, fish["wxid"], -(max_e - current))
        db.add_fish_event(group_id, "", "carnival", {"desc": "全体精力全满"})
        result["carnival"] = True

    db.add_fish_event(group_id, "", evt_type, result)
    return result


def _apply_effects(group_id: int, wxid: str, effects: dict, fish: dict):
    """应用效果（growth/hp/happiness/coins/能量变动等）"""
    if "xp" in effects:
        from services.fish_pond import add_xp
        add_xp(group_id, wxid, effects["xp"], "passive_event")
    if "coins" in effects:
        amount = effects["coins"]
        if isinstance(amount, str):
            amount = d20lib.coin_roll(amount)
        if amount:
            db.earn_coins(group_id, wxid, amount, "passive_event",
                          effects.get("desc", ""))
    if "growth" in effects:
        new_g = fish["growth"] + effects["growth"]
        db.update_fish_field(group_id, wxid, "growth", new_g)
    if "growth_loss" in effects:
        new_g = max(0, fish["growth"] - effects["growth_loss"])
        db.update_fish_field(group_id, wxid, "growth", new_g)
    if "hp_loss" in effects:
        loss = effects["hp_loss"]
        if isinstance(loss, str):
            loss = d20lib.coin_roll(loss)
        new_hp = max(0, fish.get("hp", 20) - loss)
        db.update_fish_field(group_id, wxid, "hp", new_hp)
        if new_hp <= 0:
            _kill_fish(group_id, wxid, fish, effects.get("desc", "事件致死"))
    if "energy_loss" in effects:
        db.update_fish_energy(group_id, wxid, effects["energy_loss"])
    if "energy_restore" in effects:
        db.update_fish_energy(group_id, wxid, -effects["energy_restore"])
    if "happiness" in effects:
        new_h = max(0, min(100, fish.get("happiness", 50) + effects["happiness"]))
        db.update_fish_field(group_id, wxid, "happiness", new_h)
    if "random_attr" in effects:
        attrs = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
        attr = random.choice(attrs)
        val = fish.get(attr, 10) + effects["random_attr"]
        db.update_fish_field(group_id, wxid, attr, val)
    if "auto_feed" in effects:
        g = fish.get("growth", 0) + 5
        db.update_fish_field(group_id, wxid, "growth", g)
        db.update_fish_field(group_id, wxid, "last_fed_date", datetime.now().strftime("%Y-%m-%d"))


def _kill_fish(group_id: int, wxid: str, fish: dict, cause: str):
    """鱼死亡 + 遗言"""
    db.mark_fish_dead(group_id, wxid)
    last_words = random.choice(FISH_LAST_WORDS)
    db.add_fish_event(group_id, wxid, "death", {
        "fish_name": fish["fish_name"], "cause": cause,
        "last_words": last_words,
    })
    logger.info(f"鱼死亡: group={group_id} {fish['fish_name']} — {last_words}")


def _treasury_tick(group_id: int):
    """金库进账：全群鳞币总和 × 税率%"""
    from config import config as cfg
    tax_rate = getattr(cfg, "POND_TREASURY_TAX_RATE", 5)
    total_coins = db.get_total_coins_in_group(group_id)
    earn = max(3, int(total_coins * tax_rate / 100))
    db.add_treasury(group_id, earn, "event_income",
                    f"群鳞币总和 {total_coins} × {tax_rate}%")


def _record_last_event(group_id: int):
    """记录上次事件触发时间到 app_settings"""
    now = datetime.now().isoformat()
    conn = db.get_conn()
    conn.execute(
        """INSERT INTO app_settings (key, value, value_type, description)
           VALUES (?, ?, 'string', 'pond last event timestamp')
           ON CONFLICT(key) DO UPDATE SET value = ?""",
        (f"pond_last_event_at_{group_id}", now, now)
    )
    conn.commit()
    conn.close()


# ==================== 状态语生成 ====================

def generate_daily_status(wxid: str, today_events: list) -> str:
    """根据今日事件生成鱼的状态语（事件驱动拼接，不用 AI）"""
    if not today_events:
        return random.choice(BORED_STATUSES)

    # 优先级从高到低匹配
    for evt in today_events:
        evt_type = evt.get("event_type", evt.get("type", ""))

        if evt_type == "shark_attack":
            data = _parse_event_data(evt)
            if data.get("success"):
                return "今天从鲨鱼嘴里逃出来了！活着真好！！"
            else:
                return None  # 死鱼不说话

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

    # 无特别事件 → 无聊池
    return random.choice(BORED_STATUSES)


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
