"""
群鱼塘 🐟 — D&D 版核心逻辑

品种/属性/XP/成长/结算/指令解析
"""
import random
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from services.d20 import (
    ability_check, ability_modifier, proficiency_bonus,
    opposed_check, saving_throw, roll_dice, D20Result
)
from models import database as db

logger = logging.getLogger(__name__)

# ==================== 品种定义 ====================

AQUATIC_SPECIES = {
    # ========== 鱼类：传统观赏鱼 ==========
    "goldfish": {
        "name": "金鱼", "emoji": "🐟", "color": "#F59E0B",
        "asi": {"cha": 3, "con": 1, "str": -1},
        "proficiencies": ["performance"],
        "desc": "温顺可爱，人见人爱，但弱不禁风"
    },
    "koi": {
        "name": "锦鲤", "emoji": "🎏", "color": "#EF4444",
        "asi": {"cha": 3, "wis": 2, "str": -1, "dex": -1},
        "proficiencies": ["performance", "nature"],
        "desc": "幸运化身，魅力感知俱佳，需要精心照料"
    },
    "clownfish": {
        "name": "小丑鱼", "emoji": "🤡", "color": "#F97316",
        "asi": {"dex": 3, "cha": 1},
        "proficiencies": ["acrobatics", "performance"],
        "desc": "灵活矫健，天生的表演者"
    },
    "betta": {
        "name": "斗鱼", "emoji": "🐠", "color": "#3B82F6",
        "asi": {"str": 3, "dex": 2, "con": -2, "cha": -1},
        "proficiencies": ["athletics", "intimidation"],
        "desc": "天生的角斗士，凶猛好战但体质脆弱脾气差"
    },
    "arowana": {
        "name": "龙鱼", "emoji": "🐉", "color": "#FFD700",
        "asi": {"str": 3, "cha": 2, "dex": -2, "wis": -1},
        "proficiencies": ["athletics", "intimidation"],
        "desc": "水中霸主，威严霸气但笨拙固执"
    },
    "angelfish": {
        "name": "神仙鱼", "emoji": "👼", "color": "#A78BFA",
        "asi": {"wis": 3, "cha": 2, "con": -2},
        "proficiencies": ["insight", "nature"],
        "desc": "飘逸出尘，洞察万物，但身子骨弱"
    },
    "pufferfish": {
        "name": "河豚", "emoji": "🐡", "color": "#EC4899",
        "asi": {"con": 4, "wis": 1, "dex": -3},
        "proficiencies": ["endurance"],
        "desc": "防御大师！膨胀起来无敌，但平时慢吞吞"
    },

    # ========== 掠食类：战斗向 ==========
    "shark": {
        "name": "鲨鱼", "emoji": "🦈", "color": "#6B7280",
        "asi": {"str": 4, "dex": 1, "wis": -2, "cha": -2},
        "proficiencies": ["athletics", "stealth", "intimidation"],
        "desc": "顶级掠食者，力量恐怖但不通人情世故"
    },
    "crocodile": {
        "name": "鳄鱼", "emoji": "🐊", "color": "#4D7C0F",
        "asi": {"str": 3, "con": 3, "dex": -2, "cha": -3},
        "proficiencies": ["athletics", "stealth", "endurance"],
        "desc": "远古猎手，血厚攻高，但社交为零"
    },
    "orca": {
        "name": "虎鲸", "emoji": "🐳", "color": "#1E3A5F",
        "asi": {"str": 3, "int": 2, "cha": 1, "dex": -3},
        "proficiencies": ["athletics", "investigation", "intimidation"],
        "desc": "海洋顶级智商+武力，唯一的弱点是体型太大不灵活"
    },

    # ========== 软体/甲壳类：特殊向 ==========
    "octopus": {
        "name": "章鱼", "emoji": "🐙", "color": "#D946EF",
        "asi": {"int": 4, "dex": 2, "str": -3},
        "proficiencies": ["investigation", "stealth", "acrobatics"],
        "desc": "天才级智力+触手灵活，但力量孱弱"
    },
    "squid": {
        "name": "鱿鱼", "emoji": "🦑", "color": "#F472B6",
        "asi": {"dex": 4, "int": 1, "con": -2, "str": -2},
        "proficiencies": ["acrobatics", "stealth"],
        "desc": "速度之王，来去如电，但一碰就碎"
    },
    "crab": {
        "name": "螃蟹", "emoji": "🦀", "color": "#DC2626",
        "asi": {"con": 3, "str": 2, "cha": -2, "dex": -1},
        "proficiencies": ["endurance", "athletics"],
        "desc": "横着走的铁甲坦克，防御拉满但社交笨拙"
    },
    "lobster": {
        "name": "龙虾", "emoji": "🦞", "color": "#B91C1C",
        "asi": {"str": 3, "con": 2, "int": -2, "dex": -2},
        "proficiencies": ["athletics", "endurance"],
        "desc": "巨钳无双，可惜脑子不太够用"
    },
    "jellyfish": {
        "name": "水母", "emoji": "🪼", "color": "#C084FC",
        "asi": {"wis": 4, "cha": 2, "con": -3, "str": -2},
        "proficiencies": ["insight", "nature", "performance"],
        "desc": "空灵飘逸的深海先知，但吹弹可破"
    },
    "shrimp": {
        "name": "虾", "emoji": "🦐", "color": "#FB923C",
        "asi": {"dex": 3, "con": 1, "str": -1, "int": -1},
        "proficiencies": ["acrobatics", "stealth"],
        "desc": "弹跳力惊人，擅长躲避，但没啥存在感"
    },

    # ========== 哺乳类：社交/耐久向 ==========
    "whale": {
        "name": "鲸鱼", "emoji": "🐋", "color": "#1E40AF",
        "asi": {"con": 3, "str": 3, "dex": -3, "int": -1},
        "proficiencies": ["endurance", "nature"],
        "desc": "庞然巨物，生命力顽强，但转身都要半天"
    },
    "dolphin": {
        "name": "海豚", "emoji": "🐬", "color": "#06B6D4",
        "asi": {"cha": 3, "int": 2, "str": -2, "con": -1},
        "proficiencies": ["performance", "acrobatics", "insight"],
        "desc": "智慧+魅力双高，大海的宠儿，就是打人不疼"
    },
    "seal": {
        "name": "海豹", "emoji": "🦭", "color": "#94A3B8",
        "asi": {"cha": 3, "con": 2, "wis": -2, "int": -2},
        "proficiencies": ["performance", "endurance"],
        "desc": "萌即正义！憨憨的外表下皮糙肉厚"
    },
    "otter": {
        "name": "水獭", "emoji": "🦦", "color": "#92400E",
        "asi": {"dex": 2, "cha": 2, "int": 1, "str": -2},
        "proficiencies": ["acrobatics", "investigation"],
        "desc": "灵巧又聪明的小机灵鬼，会用工具！力气不大"
    },

    # ========== 两栖/爬行类 ==========
    "turtle": {
        "name": "海龟", "emoji": "🐢", "color": "#15803D",
        "asi": {"con": 4, "wis": 2, "dex": -3, "cha": -2},
        "proficiencies": ["endurance", "nature"],
        "desc": "万年龟甲！防御和智慧拉满，但速度...呃"
    },
    "frog": {
        "name": "青蛙", "emoji": "🐸", "color": "#65A30D",
        "asi": {"dex": 3, "wis": 2, "str": -2, "cha": -1},
        "proficiencies": ["acrobatics", "nature", "stealth"],
        "desc": "跳跃大师，水陆两栖的全能选手"
    },
    "axolotl": {
        "name": "美西螈", "emoji": "🦎", "color": "#FB7185",
        "asi": {"con": 2, "wis": 2, "cha": 1, "str": -2},
        "proficiencies": ["endurance", "nature"],
        "desc": "再生能力逆天，永远保持幼态可爱的神奇生物"
    },
}

# ==================== 常量 ====================

RARITY_BASE = {"普通": 6, "稀有": 8, "史诗": 10, "传说": 12}
RARITY_COLORS = {"普通": "#9CA3AF", "稀有": "#3B82F6", "史诗": "#8B5CF6", "传说": "#F97316"}
STAGE_THRESHOLDS = [
    ("鱼苗", 0), ("幼鱼", 100), ("成鱼", 500), ("大鱼", 2000), ("传说", 5000)
]

# XP 等级表
XP_TABLE = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500]

# 商店物品
SHOP_ITEMS = {
    "premium_feed": {"name": "高级饲料", "price": 20, "desc": "/喂食 时额外 +15 成长，大成功阈值降为 18"},
    "lucky_charm":  {"name": "幸运符",   "price": 50, "desc": "下一次检定自动取 15（非大成功）"},
    "rename_tag":   {"name": "改名符",   "price": 30, "desc": "给鱼改名"},
    "ward":         {"name": "保护结界", "price": 80, "desc": "7 天内免疫鲨鱼"},
    "compass":      {"name": "探宝罗盘", "price": 100, "desc": "下一次 /寻宝 检定获得优势"},
}


# ==================== 品种与属性 ====================

def get_species_info(species_key: str) -> dict | None:
    """获取品种信息"""
    return AQUATIC_SPECIES.get(species_key)


def random_species(seed: str = None) -> str:
    """随机选择一个品种"""
    keys = sorted(AQUATIC_SPECIES.keys())
    if seed:
        rng = random.Random(seed)
        return rng.choice(keys)
    return random.choice(keys)


def generate_attributes(species_key: str, rarity: str, seed: str = None) -> dict:
    """生成六维属性：稀有度基准 + 每属性随机 ±2 + 种族 ASI"""
    base = RARITY_BASE.get(rarity, 6)
    rng = random.Random(seed) if seed else random.Random()

    attrs = {}
    for attr in ["str", "dex", "con", "int", "wis", "cha"]:
        roll = rng.randint(-2, 2)
        attrs[attr] = base + roll

    species = AQUATIC_SPECIES.get(species_key, {})
    asi = species.get("asi", {})
    attr_map = {
        "str": "strength", "dex": "dexterity", "con": "constitution",
        "int": "intelligence", "wis": "wisdom", "cha": "charisma"
    }
    for abbr, full in attr_map.items():
        bonus = asi.get(abbr, 0)
        attrs[abbr] += bonus
        # 裁剪到 [2, 22]
        attrs[abbr] = max(2, min(22, attrs[abbr]))

    return {
        "strength": attrs["str"], "dexterity": attrs["dex"],
        "constitution": attrs["con"], "intelligence": attrs["int"],
        "wisdom": attrs["wis"], "charisma": attrs["cha"]
    }


def get_proficiencies(species_key: str) -> list[str]:
    """获取品种的技能熟练项"""
    species = AQUATIC_SPECIES.get(species_key, {})
    return species.get("proficiencies", [])


# ==================== 稀有度 ====================

def compute_rarity(group_id: int, message_count: int) -> str:
    """根据消息量在群内百分位确定稀有度"""
    fish_list = db.get_alive_fish(group_id)
    if not fish_list:
        return "普通"

    counts = sorted([f["growth"] for f in fish_list], reverse=True)
    # 用成长值做排序参考（新鱼 growth=0，按 message_count 做初始估算）
    total = len(counts)
    if total < 4:
        return "普通"

    # message_count 排名
    better = sum(1 for _ in range(total))
    # 简化：用 message_count 自身做阈值
    if message_count >= 2000:
        return "传说"
    elif message_count >= 800:
        return "史诗"
    elif message_count >= 200:
        return "稀有"
    return "普通"


# ==================== XP 与等级 ====================

def xp_for_level(level: int) -> int:
    """达到某等级需要的累计 XP"""
    if level <= 1:
        return 0
    if level <= len(XP_TABLE):
        return XP_TABLE[level - 1]
    # 线性外推
    return XP_TABLE[-1] + (level - len(XP_TABLE)) * 1500


def level_from_xp(xp: int) -> int:
    """从 XP 计算等级"""
    for lv in range(len(XP_TABLE), 0, -1):
        if xp >= XP_TABLE[lv - 1]:
            return lv
    return 1


def add_xp(group_id: int, wxid: str, amount: int, reason: str) -> dict | None:
    """给鱼增加经验值，检查升级"""
    fish = db.get_fish(group_id, wxid)
    if not fish:
        return None

    old_level = fish["level"]
    new_xp = fish["experience"] + amount
    new_level = level_from_xp(new_xp)

    db.update_fish_multi(group_id, wxid, {
        "experience": new_xp,
        "level": new_level,
    })

    result = {"old_level": old_level, "new_level": new_level, "xp_gained": amount}
    if new_level > old_level:
        db.add_fish_event(group_id, wxid, "level_up", {
            "reason": reason, "old_level": old_level, "new_level": new_level
        })
        result["leveled_up"] = True
    else:
        result["leveled_up"] = False

    return result


# ==================== 成长与阶段 ====================

def determine_stage(growth: float) -> str:
    """根据成长值判断阶段"""
    stage = "鱼苗"
    for name, threshold in STAGE_THRESHOLDS:
        if growth >= threshold:
            stage = name
    return stage


def compute_max_hp(constitution: int, level: int, stage: str) -> int:
    """计算最大 HP"""
    con_mod = ability_modifier(constitution)
    base = 10 + con_mod * 2 + level * 2
    if stage == "鱼苗":
        base = int(base * 0.5)
    return max(1, base)


# ==================== 鱼创建 ====================

def create_fish(group_id: int, wxid: str, display_name: str,
                species: str = None, rarity: str = None,
                message_count: int = 0) -> dict:
    """创建一条新鱼（或重新领养）"""
    # 检查是否已有存活鱼
    existing = db.get_fish(group_id, wxid)
    if existing and existing.get("is_alive"):
        return {"error": "该成员已有存活鱼，请先等鱼死亡后再领养", "fish": existing}

    if species is None:
        species = random_species()
    species_info = AQUATIC_SPECIES.get(species, AQUATIC_SPECIES["goldfish"])

    if rarity is None:
        rarity = compute_rarity(group_id, message_count)

    attrs = generate_attributes(species, rarity)

    fish_name = f"{display_name}的{species_info['name']}"

    fid = db.upsert_fish(
        group_id=group_id, wxid=wxid, fish_name=fish_name,
        species=species, rarity=rarity,
        strength=attrs["strength"], dexterity=attrs["dexterity"],
        constitution=attrs["constitution"], intelligence=attrs["intelligence"],
        wisdom=attrs["wisdom"], charisma=attrs["charisma"],
        experience=0, level=1, growth=0, happiness=60,
        hp=compute_max_hp(attrs["constitution"], 1, "鱼苗"),
        stage="鱼苗", is_alive=1
    )

    db.add_fish_event(group_id, wxid, "born", {
        "species": species, "rarity": rarity, "fish_name": fish_name,
        "attributes": attrs
    })

    logger.info(f"鱼创建: group={group_id} wxid={wxid} {fish_name} {rarity}")

    fish = db.get_fish(group_id, wxid)
    return {"fish": fish, "species_info": species_info, "new": True}


# ==================== 互动指令 ====================

def cmd_feed(group_id: int, wxid: str, from_wxid: str = None,
             premium: bool = False, seed: str = None) -> dict:
    """/喂食：DEX 检定 DC10"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    result = ability_check(fish["dexterity"], dc=10,
                          is_proficient="acrobatics" in get_proficiencies(fish["species"]),
                          level=fish["level"], seed=seed)

    if result.critical_hit:
        growth_bonus = 20 + (15 if premium else 0)
        happiness_bonus = 5
    elif result.success:
        growth_bonus = 10 + (15 if premium else 0)
        happiness_bonus = 2
    else:
        growth_bonus = 3 + (5 if premium else 0)
        happiness_bonus = 0

    new_growth = fish["growth"] + growth_bonus
    new_happiness = min(100, fish["happiness"] + happiness_bonus)
    new_stage = determine_stage(new_growth)
    evolved = new_stage != fish["stage"]

    updates = {
        "growth": new_growth, "happiness": new_happiness,
        "stage": new_stage, "last_fed_date": datetime.now().strftime("%Y-%m-%d")
    }
    db.update_fish_multi(group_id, wxid, updates)

    # XP
    xp_result = add_xp(group_id, wxid, 5 if result.success else 2, "feed")

    event_data = result.to_dict()
    event_data.update({"growth_bonus": growth_bonus, "happiness_bonus": happiness_bonus,
                       "premium": premium, "from_wxid": from_wxid, "evolved": evolved})
    db.add_fish_event(group_id, wxid, "feed", event_data)

    if from_wxid and from_wxid != wxid:
        db.add_fish_event(group_id, from_wxid, "feed_other", {"target_wxid": wxid})

    return {
        "check": result.to_dict(), "growth_bonus": growth_bonus,
        "happiness_bonus": happiness_bonus, "evolved": evolved,
        "new_stage": new_stage, "xp": xp_result
    }


def cmd_clean(group_id: int, wxid: str, seed: str = None) -> dict:
    """/换水：WIS 检定 DC8"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    result = ability_check(fish["wisdom"], dc=8,
                          is_proficient="nature" in get_proficiencies(fish["species"]),
                          level=fish["level"], seed=seed)

    if result.critical_hit:
        happiness_bonus = 10
        xp_amount = 15
    elif result.success:
        happiness_bonus = 5
        xp_amount = 5
    else:
        happiness_bonus = 2
        xp_amount = 2

    new_happiness = min(100, fish["happiness"] + happiness_bonus)
    db.update_fish_field(group_id, wxid, "happiness", new_happiness)
    xp_result = add_xp(group_id, wxid, xp_amount, "clean")

    db.add_fish_event(group_id, wxid, "clean", {
        **result.to_dict(), "happiness_bonus": happiness_bonus
    })

    return {"check": result.to_dict(), "happiness_bonus": happiness_bonus, "xp": xp_result}


def cmd_touch(group_id: int, wxid: str, seed: str = None) -> dict:
    """/摸鱼：CHA 检定 DC12"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    result = ability_check(fish["charisma"], dc=12,
                          is_proficient="performance" in get_proficiencies(fish["species"]),
                          level=fish["level"], seed=seed)

    if result.critical_hit:
        intimacy_bonus = 5
        xp_amount = 15
    elif result.success:
        intimacy_bonus = 2
        xp_amount = 5
    else:
        intimacy_bonus = 1
        xp_amount = 2

    xp_result = add_xp(group_id, wxid, xp_amount, "touch")

    db.add_fish_event(group_id, wxid, "touch", {
        **result.to_dict(), "intimacy_bonus": intimacy_bonus
    })

    return {"check": result.to_dict(), "intimacy_bonus": intimacy_bonus, "xp": xp_result}


def cmd_battle(group_id: int, wxid_a: str, wxid_b: str, seed: str = None) -> dict:
    """/斗鱼 @XX：STR 对抗检定"""
    fish_a = db.get_fish(group_id, wxid_a)
    fish_b = db.get_fish(group_id, wxid_b)
    if not fish_a or not fish_b or not fish_a["is_alive"] or not fish_b["is_alive"]:
        return {"error": "一方或双方鱼不存在/已死亡"}

    result = opposed_check(
        fish_a["strength"], fish_b["strength"],
        att_prof="athletics" in get_proficiencies(fish_a["species"]),
        def_prof="athletics" in get_proficiencies(fish_b["species"]),
        level=max(fish_a["level"], 1), seed=seed
    )

    if result["winner"] == "attacker":
        winner_wxid, loser_wxid = wxid_a, wxid_b
    else:
        winner_wxid, loser_wxid = wxid_b, wxid_a

    winner_fish = db.get_fish(group_id, winner_wxid)
    loser_fish = db.get_fish(group_id, loser_wxid)

    # 胜者 +growth +coins
    winner_growth = winner_fish["growth"] + 20
    new_happiness = max(0, loser_fish["happiness"] - 5)

    db.update_fish_field(group_id, winner_wxid, "growth", winner_growth)
    db.update_fish_field(group_id, loser_wxid, "happiness", new_happiness)

    # 胜者获得鳞币
    db.earn_coins(group_id, winner_wxid, 10, "battle_win",
                 f"斗鱼战胜 {loser_fish.get('fish_name', loser_wxid)}")

    xp_result = add_xp(group_id, winner_wxid, 30, "battle_win")

    # 检查胜者进化
    new_stage = determine_stage(winner_growth)
    if new_stage != winner_fish["stage"]:
        db.update_fish_field(group_id, winner_wxid, "stage", new_stage)
        db.add_fish_event(group_id, winner_wxid, "evolve", {
            "old_stage": winner_fish["stage"], "new_stage": new_stage
        })

    db.add_fish_event(group_id, winner_wxid, "battle", {
        "opponent_wxid": loser_wxid, "result": "win",
        "check": result["attacker"] if result["winner"] == "attacker" else result["defender"]
    })
    db.add_fish_event(group_id, loser_wxid, "battle", {
        "opponent_wxid": winner_wxid, "result": "lose"
    })

    return {
        "check": result, "winner": winner_wxid, "loser": loser_wxid,
        "winner_growth": 20, "xp": xp_result
    }


def cmd_explore(group_id: int, wxid: str, seed: str = None) -> dict:
    """/探索：WIS/INT 检定 DC13，获得 1d10 鳞币"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    # 用较高的那个属性
    ability = fish["wisdom"] if fish["wisdom"] >= fish["intelligence"] else fish["intelligence"]
    score = max(fish["wisdom"], fish["intelligence"])
    prof = "investigation" in get_proficiencies(fish["species"]) or \
          "nature" in get_proficiencies(fish["species"])

    result = ability_check(score, dc=13, is_proficient=prof,
                          level=fish["level"], seed=seed)

    if result.critical_hit:
        coin_amount, _ = roll_dice("2d10", seed)
        coin_amount += 5
    elif result.success:
        coin_amount, _ = roll_dice("1d10", seed)
    else:
        coin_amount = 0

    if coin_amount > 0:
        db.earn_coins(group_id, wxid, coin_amount, "explore",
                     f"探索获得 {coin_amount} 鳞币")

    xp_result = add_xp(group_id, wxid, 5 if result.success else 2, "explore")

    db.add_fish_event(group_id, wxid, "explore", {
        **result.to_dict(), "coin_amount": coin_amount
    })

    return {"check": result.to_dict(), "coin_amount": coin_amount, "xp": xp_result}


def cmd_treasure(group_id: int, wxid: str, advantage: bool = False,
                 seed: str = None) -> dict:
    """/寻宝：INT 检定 DC15，获得 2d10 鳞币"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    result = ability_check(fish["intelligence"], dc=15,
                          is_proficient="investigation" in get_proficiencies(fish["species"]),
                          level=fish["level"], advantage=advantage, seed=seed)

    if result.critical_hit:
        coin_amount, _ = roll_dice("3d10", seed)
        special = True
    elif result.success:
        coin_amount, _ = roll_dice("2d10", seed)
        special = False
    else:
        coin_amount, _ = roll_dice("1d4", seed)
        special = False

    if coin_amount > 0:
        db.earn_coins(group_id, wxid, coin_amount, "treasure",
                     f"寻宝获得 {coin_amount} 鳞币")

    xp_result = add_xp(group_id, wxid, 10 if result.success else 3, "treasure")

    db.add_fish_event(group_id, wxid, "treasure", {
        **result.to_dict(), "coin_amount": coin_amount, "special": special
    })

    return {
        "check": result.to_dict(), "coin_amount": coin_amount,
        "special": special, "xp": xp_result
    }


def cmd_showoff(group_id: int, wxid: str, seed: str = None) -> dict:
    """/晒鱼：CHA 检定，观众打赏"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    result = ability_check(fish["charisma"], dc=10,
                          is_proficient="performance" in get_proficiencies(fish["species"]),
                          level=fish["level"], seed=seed)

    if result.critical_hit:
        coin_amount = 8
    elif result.success:
        coin_amount = random.randint(3, 6)
    else:
        coin_amount = random.randint(1, 3)

    if coin_amount > 0:
        db.earn_coins(group_id, wxid, coin_amount, "showoff",
                     f"晒鱼获得观众打赏 {coin_amount} 鳞币")

    db.add_fish_event(group_id, wxid, "showoff", {
        **result.to_dict(), "coin_amount": coin_amount
    })

    return {"check": result.to_dict(), "coin_amount": coin_amount}


def cmd_rename(group_id: int, wxid: str, new_name: str,
               use_tag: bool = False) -> dict:
    """/改名 <名字>：首次免费，之后需改名符"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    old_name = fish["fish_name"]

    # 检查是否首次改名（通过 events 判断）
    conn = db.get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM fish_events WHERE group_id=? AND wxid=? AND event_type='rename'",
        (group_id, wxid)
    ).fetchone()
    conn.close()

    is_first = (row["cnt"] == 0)

    if not is_first and not use_tag:
        return {"error": "非首次改名需要改名符（30鳞币）", "need_tag": True}

    if not is_first:
        wallet = db.spend_coins(group_id, wxid, 30, "rename",
                               f"改名: {old_name} → {new_name}")
        if wallet is None:
            return {"error": "鳞币不足，改名需要 30 鳞币"}

    db.update_fish_field(group_id, wxid, "fish_name", new_name)
    db.add_fish_event(group_id, wxid, "rename", {
        "old_name": old_name, "new_name": new_name, "is_first": is_first
    })

    return {"old_name": old_name, "new_name": new_name, "is_first": is_first}


def cmd_adopt(group_id: int, wxid: str, display_name: str,
              message_count: int = 0) -> dict:
    """/领养：创建鱼"""
    existing = db.get_fish(group_id, wxid)
    if existing:
        if existing.get("is_alive"):
            return {"error": "你已经有鱼了！", "fish": existing}
        else:
            # 死亡后重新领养，随机新品种
            return create_fish(group_id, wxid, display_name,
                             species=random_species(), message_count=message_count)
    return create_fish(group_id, wxid, display_name, message_count=message_count)


# ==================== 结算 ====================

def _generate_weather(group_id: int, date_str: str) -> dict:
    """确定性天气生成"""
    seed_str = f"weather_{group_id}_{date_str}"
    rng = random.Random(seed_str)
    roll = rng.randint(1, 100)
    if roll <= 60:
        weather = {"type": "sunny", "name": "晴天", "emoji": "☀️",
                   "effect": "无特殊效果", "growth_bonus": 0, "happiness_bonus": 0}
    elif roll <= 85:
        weather = {"type": "rain", "name": "雨天", "emoji": "🌧️",
                   "effect": "全体 +5 成长值", "growth_bonus": 5, "happiness_bonus": 0}
    elif roll <= 95:
        weather = {"type": "storm", "name": "暴风雨", "emoji": "⛈️",
                   "effect": "全体幸福值 -5", "growth_bonus": 0, "happiness_bonus": -5}
    else:
        weather = {"type": "rainbow", "name": "彩虹", "emoji": "🌈",
                   "effect": "全体 +10 幸福值", "growth_bonus": 0, "happiness_bonus": 10}
    return weather


def settle_fish(group_id: int, wxid: str, reference_date: str = None,
                member_message_count: int = 0, member_active: bool = False) -> dict:
    """结算单条鱼"""

    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"settled": False, "reason": "no fish or dead"}

    date_str = reference_date or datetime.now().strftime("%Y-%m-%d")
    events = []

    # 1. 自动喂食：当天发言 ≥5 条
    if member_active and member_message_count >= 5:
        result = cmd_feed(group_id, wxid, seed=f"settle_feed_{group_id}_{wxid}_{date_str}")
        events.append({"type": "auto_feed", "data": result})

    # 2. 连续活跃计算
    last_active = fish.get("last_active_date", "")
    consecutive = fish.get("consecutive_days", 0)

    if member_active:
        consecutive += 1
    else:
        # 检查潜水天数
        if last_active:
            last_date = datetime.strptime(last_active, "%Y-%m-%d")
            today = datetime.strptime(date_str, "%Y-%m-%d")
            gap = (today - last_date).days
            if gap >= 3:
                penalty = gap * 5
                new_happiness = max(0, fish["happiness"] - penalty)
                db.update_fish_field(group_id, wxid, "happiness", new_happiness)
                events.append({"type": "inactive_penalty", "gap_days": gap,
                              "happiness_penalty": penalty})
        # 潜水期间不重置连续天数，只扣幸福值

    db.update_fish_multi(group_id, wxid, {
        "consecutive_days": consecutive,
        "last_active_date": date_str if member_active else last_active
    })

    # 3. 连续活跃加成
    if consecutive >= 30:
        growth_bonus = 30
        db.update_fish_field(group_id, wxid, "growth", fish["growth"] + growth_bonus)
        db.earn_coins(group_id, wxid, 100, "streak_30",
                     f"连续活跃 30 天奖励")
        events.append({"type": "streak_30", "growth_bonus": growth_bonus, "coin_bonus": 100})
    elif consecutive >= 7:
        growth_bonus = 10
        db.update_fish_field(group_id, wxid, "growth", fish["growth"] + growth_bonus)
        db.earn_coins(group_id, wxid, 30, "streak_7",
                     f"连续活跃 7 天奖励")
        events.append({"type": "streak_7", "growth_bonus": growth_bonus, "coin_bonus": 30})

    # 4. 进化检查
    fish = db.get_fish(group_id, wxid)  # refresh
    new_stage = determine_stage(fish["growth"])
    if new_stage != fish["stage"]:
        db.update_fish_field(group_id, wxid, "stage", new_stage)
        db.update_fish_field(group_id, wxid, "hp",
                            compute_max_hp(fish["constitution"], fish["level"], new_stage))
        db.add_fish_event(group_id, wxid, "evolve", {
            "old_stage": fish["stage"], "new_stage": new_stage
        })
        # 进化鳞币奖励
        evolve_coins = {"幼鱼": 20, "成鱼": 50, "大鱼": 80, "传说": 200}.get(new_stage, 0)
        if evolve_coins:
            db.earn_coins(group_id, wxid, evolve_coins, "evolve",
                         f"进化为{new_stage}奖励")
        add_xp(group_id, wxid, 100, "evolve")
        events.append({"type": "evolve", "old_stage": fish["stage"], "new_stage": new_stage})

    # 5. 生日检查
    created = fish.get("created_at", "")
    if created:
        created_date = created[:10] if " " in created else created
        if created_date:
            created_dt = datetime.strptime(created_date, "%Y-%m-%d")
            today_dt = datetime.strptime(date_str, "%Y-%m-%d")
            days_since = (today_dt - created_dt).days
            if days_since > 0 and days_since % 30 == 0:
                db.earn_coins(group_id, wxid, 50, "birthday",
                             f"领养第 {days_since} 天生日礼")
                events.append({"type": "birthday", "days": days_since})

    # 6. 周末加成
    today_dt = datetime.strptime(date_str, "%Y-%m-%d")
    if today_dt.weekday() >= 5:  # 周六=5, 周日=6
        fish = db.get_fish(group_id, wxid)
        db.update_fish_field(group_id, wxid, "growth", fish["growth"] + 3)
        events.append({"type": "weekend_bonus", "growth_bonus": 3})

    return {"settled": True, "events": events}


def settle_all_fish(group_id: int, reference_date: str = None) -> dict:
    """全群结算"""
    date_str = reference_date or datetime.now().strftime("%Y-%m-%d")
    weather = _generate_weather(group_id, date_str)

    # 获取群成员活跃数据（需要用 ParsedChat，这里尝试获取）
    alive_fish = db.get_alive_fish(group_id)
    if not alive_fish:
        return {"settled": False, "error": "鱼塘里还没有鱼", "weather": weather}

    results = []
    for fish in alive_fish:
        # 简化：检查 last_active_date 是否与 reference_date 匹配
        wxid = fish["wxid"]
        result = settle_fish(group_id, wxid, date_str,
                           member_message_count=0, member_active=False)
        results.append({"wxid": wxid, "fish_name": fish["fish_name"], **result})

    # 应用天气效果
    if weather["growth_bonus"]:
        for fish in alive_fish:
            g = fish["growth"] + weather["growth_bonus"]
            db.update_fish_field(group_id, fish["wxid"], "growth", g)
    if weather["happiness_bonus"]:
        for fish in alive_fish:
            h = max(0, min(100, fish["happiness"] + weather["happiness_bonus"]))
            db.update_fish_field(group_id, fish["wxid"], "happiness", h)

    # 鲨鱼来袭 (1% 概率)
    rng = random.Random(f"shark_{group_id}_{date_str}")
    if rng.randint(1, 100) == 1:
        low_happy = [f for f in alive_fish if f["happiness"] < 20]
        if len(low_happy) >= 1 and len(alive_fish) >= 3:
            victim = rng.choice(low_happy)
            db.mark_fish_dead(group_id, victim["wxid"])
            db.add_fish_event(group_id, victim["wxid"], "shark_attack", {
                "victim": victim["fish_name"], "date": date_str
            })
            results.append({"wxid": victim["wxid"], "shark_attack": True,
                           "victim": victim["fish_name"]})

    return {
        "settled": True,
        "date": date_str,
        "weather": weather,
        "results": results,
        "fish_count": len(alive_fish),
    }


# ==================== 鱼塘状态 ====================

def get_pond_state(group_id: int, reference_date: str = None) -> dict:
    """获取鱼塘全貌"""
    date_str = reference_date or datetime.now().strftime("%Y-%m-%d")
    weather = _generate_weather(group_id, date_str)
    fish_list = db.get_all_fish(group_id)

    # 附加品种信息
    enriched = []
    for f in fish_list:
        species = AQUATIC_SPECIES.get(f["species"], {})
        f["species_info"] = species
        f["proficiencies"] = species.get("proficiencies", [])
        enriched.append(f)

    # 排行榜
    alive = [f for f in fish_list if f.get("is_alive")]
    leaderboards = {
        "growth": sorted(alive, key=lambda x: x["growth"], reverse=True)[:5],
        "happiness": sorted(alive, key=lambda x: x["happiness"], reverse=True)[:5],
        "xp": sorted(alive, key=lambda x: x["experience"], reverse=True)[:5],
    }

    # 鳞币排行
    coin_leaders = db.get_coin_leaderboard(group_id, 5)

    # 最近事件
    recent_events = db.get_fish_events(group_id, limit=10)

    return {
        "weather": weather,
        "fish": enriched,
        "alive_count": len([f for f in fish_list if f.get("is_alive")]),
        "dead_count": len([f for f in fish_list if not f.get("is_alive")]),
        "leaderboards": leaderboards,
        "coin_leaders": coin_leaders,
        "recent_events": recent_events,
    }


# ==================== 历史消息指令解析 ====================

_COMMAND_PATTERNS = [
    (r"^/领养$", "adopt"),
    (r"^/喂食$", "feed"),
    (r"^/换水$", "clean"),
    (r"^/摸鱼$", "touch"),
    (r"^/斗鱼\s*@(.+)$", "battle"),
    (r"^/探索$", "explore"),
    (r"^/寻宝$", "treasure"),
    (r"^/晒鱼$", "showoff"),
    (r"^/鱼塘$", "pond"),
    (r"^/改名\s+(.+)$", "rename"),
]


def is_game_command(content: str) -> bool:
    """判断消息是否为鱼塘游戏指令（以 / 开头）"""
    return (content or "").strip().startswith('/')


def parse_command(content: str) -> dict | None:
    """解析一条指令"""
    text = (content or "").strip()
    for pattern, cmd_type in _COMMAND_PATTERNS:
        m = re.match(pattern, text)
        if m:
            result = {"type": cmd_type, "raw": text}
            if cmd_type == "battle":
                result["target_name"] = m.group(1).strip()
            elif cmd_type == "rename":
                result["new_name"] = m.group(1).strip()
            return result
    return None


def parse_commands_from_messages(group_id: int, messages: list[dict],
                                 get_name_by_wxid) -> dict:
    """从消息列表中解析鱼塘指令并执行

    Args:
        group_id: 群 ID
        messages: 消息列表（需含 wxid, content, platformMessageId, formattedTime）
        get_name_by_wxid: wxid → 显示名 的映射函数

    Returns:
        {commands_found: N, events_processed: [...], errors: [...]}
    """
    processed = []
    errors = []
    commands_found = 0

    for msg in sorted(messages, key=lambda m: m.get("createTime", 0)):
        content = (msg.get("content") or "").strip()
        if not is_game_command(content):
            continue

        cmd = parse_command(content)
        if not cmd:
            continue

        commands_found += 1
        wxid = msg.get("wxid", "")
        if not wxid:
            errors.append({"msg": content, "error": "无法确定发送者 wxid"})
            continue

        display_name = get_name_by_wxid(wxid)
        seed = f"cmd_{group_id}_{msg.get('platformMessageId', '')}"

        try:
            if cmd["type"] == "adopt":
                result = cmd_adopt(group_id, wxid, display_name)
            elif cmd["type"] == "feed":
                result = cmd_feed(group_id, wxid, seed=seed)
            elif cmd["type"] == "clean":
                result = cmd_clean(group_id, wxid, seed=seed)
            elif cmd["type"] == "touch":
                result = cmd_touch(group_id, wxid, seed=seed)
            elif cmd["type"] == "battle":
                # 需要通过名字反查目标 wxid
                target_name = cmd.get("target_name", "")
                target_wxid = _find_wxid_by_name(group_id, target_name)
                if target_wxid:
                    result = cmd_battle(group_id, wxid, target_wxid, seed=seed)
                else:
                    errors.append({"msg": content, "error": f"找不到目标: {target_name}"})
                    continue
            elif cmd["type"] == "explore":
                result = cmd_explore(group_id, wxid, seed=seed)
            elif cmd["type"] == "treasure":
                result = cmd_treasure(group_id, wxid, seed=seed)
            elif cmd["type"] == "showoff":
                result = cmd_showoff(group_id, wxid, seed=seed)
            elif cmd["type"] == "rename":
                result = cmd_rename(group_id, wxid, cmd["new_name"])
            elif cmd["type"] == "pond":
                result = {"type": "pond", "status": "viewed"}
                db.add_fish_event(group_id, wxid, "pond_view", {})
            else:
                continue

            processed.append({
                "type": cmd["type"],
                "wxid": wxid,
                "display_name": display_name,
                "content": content,
                "result": result,
                "time": msg.get("formattedTime", ""),
            })
        except Exception as e:
            logger.error(f"指令执行失败: {content} | {e}")
            errors.append({"msg": content, "error": str(e)})

    return {
        "commands_found": commands_found,
        "events_processed": len(processed),
        "processed": processed,
        "errors": errors,
    }


def _find_wxid_by_name(group_id: int, name: str) -> str | None:
    """通过显示名查找 wxid"""
    conn = db.get_conn()
    row = conn.execute(
        """SELECT wxid FROM group_members WHERE group_id=?
           AND (display_name=? OR nickname=? OR group_nickname=?)
           LIMIT 1""",
        (group_id, name, name, name)
    ).fetchone()
    conn.close()
    return row["wxid"] if row else None
