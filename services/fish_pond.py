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
# v1.16.0: 导入性格修正检定
from services.d20 import check_with_traits
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
    # ========== v1.16.0: 新物种（iconify emoji）==========
    "seahorse": {
        "name": "海马", "emoji": "🐟", "color": "#F9A8D4",
        "asi": {"dex": 2, "cha": 3, "str": -2, "con": -1},
        "proficiencies": ["acrobatics", "performance"],
        "desc": "优雅的舞者，独特的外形下藏着敏捷的身手"
    },
    "manta": {
        "name": "蝠鲼", "emoji": "🐟", "color": "#1C1F33",
        "asi": {"dex": 3, "wis": 2, "str": -1, "cha": -1},
        "proficiencies": ["acrobatics", "stealth"],
        "desc": "水中滑翔机，悄无声息地巡游深海"
    },
    "urchin": {
        "name": "海胆", "emoji": "🐟", "color": "#4B0082",
        "asi": {"con": 4, "str": 1, "dex": -2, "cha": -2},
        "proficiencies": ["endurance"],
        "desc": "浑身是刺的防御大师，谁碰谁后悔"
    },
    "starfish": {
        "name": "海星", "emoji": "⭐", "color": "#FF6347",
        "asi": {"con": 3, "wis": 2, "dex": -2, "int": -1},
        "proficiencies": ["endurance", "nature"],
        "desc": "断肢重生能力逆天，慢悠悠但生命力顽强"
    },
    "mantis_shrimp": {
        "name": "螳螂虾", "emoji": "🦐", "color": "#DC143C",
        "asi": {"str": 3, "con": 2, "dex": -1, "int": -2},
        "proficiencies": ["athletics", "endurance"],
        "desc": "大钳子威猛无比，出拳速度堪比子弹"
    },
    "conch": {
        "name": "海螺", "emoji": "🐚", "color": "#F5DEB3",
        "asi": {"wis": 4, "cha": 2, "dex": -3, "str": -2},
        "proficiencies": ["insight", "nature", "performance"],
        "desc": "能听到大海声音的智者，行动虽慢但洞察一切"
    },
    "otter2": {
        "name": "海獭", "emoji": "🦦", "color": "#8B4513",
        "asi": {"dex": 2, "int": 2, "cha": 2, "str": -2},
        "proficiencies": ["acrobatics", "investigation", "performance"],
        "desc": "会用工具的小机灵鬼，萌到犯规的海洋精灵"
    },
    "walrus": {
        "name": "海象", "emoji": "🦭", "color": "#A0522D",
        "asi": {"str": 3, "con": 3, "dex": -2, "int": -1},
        "proficiencies": ["athletics", "endurance"],
        "desc": "吨位即是正义，长牙之下众生平等"
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

# 商店物品（旧版兼容，后续合并到 ITEMS）
SHOP_ITEMS = {
    "premium_feed": {"name": "高级饲料", "price": 20, "desc": "/喂食 时额外 +15 成长，大成功阈值降为 18"},
    "lucky_charm":  {"name": "幸运符",   "price": 50, "desc": "下一次检定自动取 15（非大成功）"},
    "rename_tag":   {"name": "改名符",   "price": 30, "desc": "给鱼改名"},
    "ward":         {"name": "保护结界", "price": 80, "desc": "7 天内免疫鲨鱼"},
}

# ==================== 道具系统 v0.9.3 ====================

ITEMS = {
    # ---- 饲料类 ----
    "normal_feed":  {"name": "普通饲料",   "category": "feed",  "rarity": "普通", "buy": 10,  "desc": "喂食额外 +5 成长"},
    "shrimp_feed":  {"name": "磷虾饲料",   "category": "feed",  "rarity": "稀有", "buy": 50,  "desc": "喂食额外 +15 成长，幸福 +3"},
    "deep_shrimp":  {"name": "深海磷虾",   "category": "feed",  "rarity": "史诗", "buy": 150, "desc": "喂食额外 +30 成长，幸福 +5，大成功阈值-2"},
    "takoyaki":     {"name": "章鱼烧",     "category": "feed",  "rarity": "传说", "buy": 350, "desc": "喂食额外 +50 成长，必定大成功"},

    # ---- 训练类 ----
    "dumbbell":     {"name": "轻哑铃",     "category": "train", "rarity": "普通", "buy": 20,  "desc": "训练 DC -2"},
    "protein":      {"name": "蛋白粉",     "category": "train", "rarity": "稀有", "buy": 80,  "desc": "训练 DC -5"},
    "sea_essence":  {"name": "海神精华",   "category": "train", "rarity": "史诗", "buy": 180, "desc": "训练 DC -8，失败不扣属性"},
    "dragon_elixir":{"name": "龙宫秘药",   "category": "train", "rarity": "传说", "buy": 400, "desc": "训练必定成功"},

    # ---- 装备-武器 ----
    "bone_dagger":  {"name": "鱼骨短剑",   "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "力量 +2", "stat": "strength", "bonus": 2},
    "coral_sword":  {"name": "珊瑚长剑",   "category": "equip", "rarity": "史诗", "buy": 150, "desc": "力量 +3", "stat": "strength", "bonus": 3},
    "trident":      {"name": "海神三叉戟", "category": "equip", "rarity": "传说", "buy": 350, "desc": "力量 +4，斗鱼胜率+10%", "stat": "strength", "bonus": 4, "special": "battle_boost"},
    "squid_bow":    {"name": "鱿鱼骨弓",   "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "敏捷 +2", "stat": "dexterity", "bonus": 2},
    "swift_fin":    {"name": "激流之鳍",   "category": "equip", "rarity": "史诗", "buy": 150, "desc": "敏捷 +3", "stat": "dexterity", "bonus": 3},
    "eel_whip":     {"name": "电鳗尾鞭",   "category": "equip", "rarity": "传说", "buy": 350, "desc": "敏捷 +4，探索鳞币+20%", "stat": "dexterity", "bonus": 4, "special": "explore_boost"},

    # ---- 装备-防具 ----
    "turtle_shield":{"name": "龟甲盾",     "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "体质 +2", "stat": "constitution", "bonus": 2},
    "crab_armor":   {"name": "巨蟹钳甲",   "category": "equip", "rarity": "史诗", "buy": 150, "desc": "体质 +3", "stat": "constitution", "bonus": 3},
    "dragon_armor": {"name": "龙王鳞甲",   "category": "equip", "rarity": "传说", "buy": 350, "desc": "体质 +4，免疫鲨鱼", "stat": "constitution", "bonus": 4, "special": "shark_immune"},
    "coral_charm":  {"name": "珊瑚护符",   "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "体质 +1，幸福值下限+10", "stat": "constitution", "bonus": 1, "special": "happy_floor"},

    # ---- 装备-饰品 ----
    "pearl_ring":   {"name": "珍珠指环",   "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "魅力 +2", "stat": "charisma", "bonus": 2},
    "mermaid_crown":{"name": "人鱼之冠",   "category": "equip", "rarity": "史诗", "buy": 150, "desc": "魅力 +3", "stat": "charisma", "bonus": 3},
    "siren_harp":   {"name": "海妖竖琴",   "category": "equip", "rarity": "传说", "buy": 350, "desc": "魅力 +4，晒鱼鳞币+30%", "stat": "charisma", "bonus": 4, "special": "showoff_boost"},
    "deep_beads":   {"name": "深海念珠",   "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "感知 +2", "stat": "wisdom", "bonus": 2},
    "crystal_ball": {"name": "先知水晶球", "category": "equip", "rarity": "史诗", "buy": 150, "desc": "感知 +3", "stat": "wisdom", "bonus": 3},
    "abyss_eye":    {"name": "深渊之瞳",   "category": "equip", "rarity": "传说", "buy": 350, "desc": "感知 +4，探索成功率+15%", "stat": "wisdom", "bonus": 4, "special": "explore_success"},
    "sea_chart":    {"name": "海图残卷",   "category": "equip", "rarity": "稀有", "buy": 70,  "desc": "智力 +2", "stat": "intelligence", "bonus": 2},
    "alchemy_bladder":{"name":"炼金鱼鳔",  "category": "equip", "rarity": "史诗", "buy": 150, "desc": "智力 +3", "stat": "intelligence", "bonus": 3},
    "ancient_core": {"name": "远古智慧之核","category":"equip","rarity": "传说", "buy": 350, "desc": "智力 +4，训练 DC -3", "stat": "intelligence", "bonus": 4, "special": "train_boost"},

    # ---- 装备-全能 ----
    "star_shell":   {"name": "星辉贝壳",   "category": "equip", "rarity": "史诗", "buy": 200, "desc": "全属性 +1", "stat": "all", "bonus": 1},
    "dragon_soul":  {"name": "龙鱼之魂",   "category": "equip", "rarity": "传说", "buy": 500, "desc": "全属性 +2", "stat": "all", "bonus": 2},

    # ---- 幸运类 ----
    "clover_weed":  {"name": "四叶海草",   "category": "luck",  "rarity": "普通", "buy": 25,  "desc": "下次检定获得优势（掷两次取高）"},
    "lucky_dice":   {"name": "幸运骰子",   "category": "luck",  "rarity": "稀有", "buy": 60,  "desc": "下次检定自动取15（非大成功）"},
    "wishing_star": {"name": "流星许愿瓶", "category": "luck",  "rarity": "史诗", "buy": 150, "desc": "下次检定自动取19（非大成功）"},
    "fate_pearl":   {"name": "命运重置珠", "category": "luck",  "rarity": "传说", "buy": 300, "desc": "重掷一次失败的检定（保留新结果）"},

    # ---- 特殊类 ----
    "ward":         {"name": "保护结界",   "category": "special","rarity":"稀有", "buy": 80,  "desc": "7天内免疫鲨鱼"},
    "rename_tag":   {"name": "改名符",     "category": "special","rarity":"普通", "buy": 30,  "desc": "给鱼改名"},
    "hourglass":    {"name": "时光沙漏",   "category": "special","rarity":"史诗", "buy": 120, "desc": "重置今日所有指令次数限制"},
    "rebirth_seed": {"name": "轮回之种",   "category": "special","rarity":"传说", "buy": 300, "desc": "鱼死亡后使用，重生时保留一半属性"},

    # ---- 收藏类 ----
    "red_coral":    {"name": "红珊瑚",     "category": "collect","rarity":"稀有", "buy": 100, "desc": "稀有的海底珍宝"},
    "deep_pearl":   {"name": "深海珍珠",   "category": "collect","rarity":"史诗", "buy": 250, "desc": "据说能听到大海的声音"},
    "dragon_scale": {"name": "龙鳞碎片",   "category": "collect","rarity":"传说", "buy": 500, "desc": "远古龙鱼褪下的鳞片"},
}

def get_equip_bonus(group_id: int, wxid: str) -> dict:
    """获取装备带来的属性加成 {attr_key: bonus}"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish.get("equipped_item"):
        return {}
    item_key = fish["equipped_item"]
    item = ITEMS.get(item_key, {})
    if item.get("category") != "equip":
        return {}
    stat = item.get("stat", "")
    bonus = item.get("bonus", 0)
    if stat == "all":
        return {k: bonus for k in ["strength","dexterity","constitution","intelligence","wisdom","charisma"]}
    if stat:
        return {stat: bonus}
    return {}

def get_fish_with_equip(group_id: int, wxid: str) -> dict | None:
    """获取鱼信息，属性已包含装备加成"""
    fish = db.get_fish(group_id, wxid)
    if not fish:
        return None
    bonuses = get_equip_bonus(group_id, wxid)
    for attr, b in bonuses.items():
        fish[attr] = fish.get(attr, 0) + b
    return fish

# ==================== 黑市系统 ====================

def generate_black_market(group_id: int, date_str: str) -> list[dict]:
    """每天随机生成 3-5 件黑市商品"""
    rng = random.Random(f"blackmarket_{group_id}_{date_str}")
    count = rng.randint(3, 5)

    # 按稀有度加权选品：普通40% 稀有30% 史诗20% 传说10%
    pool = []
    for key, item in ITEMS.items():
        if item.get("category") == "collect":
            continue  # 收藏品不进入黑市
        w = {"普通": 40, "稀有": 30, "史诗": 20, "传说": 10}.get(item["rarity"], 10)
        pool.extend([key] * w)

    chosen = []
    seen = set()
    for _ in range(count * 3):  # 多试几次确保够
        if len(chosen) >= count:
            break
        k = rng.choice(pool)
        if k in seen:
            continue
        seen.add(k)
        item = ITEMS[k]
        base_price = item.get("buy", 50)
        # 价格浮动 ±30%
        price = max(5, int(base_price * rng.uniform(0.7, 1.3)))
        price = (price // 5) * 5  # 取整到5的倍数
        stock = rng.randint(1, 3)
        chosen.append({"key": k, "price": price, "stock": stock})

    # 存库
    db.set_black_market(group_id, date_str, chosen)
    return chosen


def get_black_market_items(group_id: int, date_str: str) -> list[dict]:
    """获取黑市商品（附带道具详情）"""
    items = db.get_black_market(group_id, date_str)
    result = []
    for i in items:
        info = ITEMS.get(i["item_key"], {})
        result.append({**i, "name": info.get("name", ""),
                       "rarity": info.get("rarity", ""),
                       "desc": info.get("desc", ""),
                       "category": info.get("category", "")})
    return result


def cmd_buy(group_id: int, wxid: str, item_key: str,
            date_str: str = None) -> dict:
    """/购买 <商品名>：从今日黑市购买"""
    from datetime import datetime as dt
    today = date_str or dt.now().strftime("%Y-%m-%d")

    # 查黑市
    market_item = db.buy_from_market(group_id, wxid, today, item_key)
    if not market_item:
        # 尝试模糊匹配
        all_items = get_black_market_items(group_id, today)
        for mi in all_items:
            if mi["name"] == item_key:
                market_item = mi
                break
        if not market_item:
            available = ", ".join(f"{i['name']}({i['price']}币)" for i in all_items)
            return {"error": f"今日黑市没有 '{item_key}'。当前: {available or '无'}"}

    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    price = market_item["price"]
    wallet = db.spend_coins(group_id, wxid, price, "buy_market",
                           f"黑市购买 {item_key}")
    if wallet is None:
        return {"error": f"鳞币不足，需要 {price} 鳞币"}

    db.add_item(group_id, wxid, item_key)
    item_info = ITEMS.get(item_key, {})
    db.add_fish_event(group_id, wxid, "market_buy",
                      {"item": item_key, "price": price, "date": today})
    return {"action": "buy", "item": item_info.get("name", item_key),
            "price": price, "rarity": item_info.get("rarity", "")}


def cmd_gift(group_id: int, wxid_from: str, target_name: str,
             item_key: str) -> dict:
    """/赠予 @XX <道具名>：把道具送给别人"""
    # 找目标
    target_wxid = _find_wxid_by_name(group_id, target_name)
    if not target_wxid:
        return {"error": f"找不到目标: {target_name}"}
    if target_wxid == wxid_from:
        return {"error": "不能赠予自己"}

    target_fish = db.get_fish(group_id, target_wxid)
    if not target_fish or not target_fish["is_alive"]:
        return {"error": f"{target_name} 没有鱼"}

    item = ITEMS.get(item_key)
    item_name = item["name"] if item else item_key

    if not db.remove_item(group_id, wxid_from, item_key):
        return {"error": f"你没有 {item_name}"}

    db.add_item(group_id, target_wxid, item_key)
    db.add_fish_event(group_id, wxid_from, "gift_send",
                      {"item": item_key, "to_wxid": target_wxid,
                       "to_name": target_name})
    db.add_fish_event(group_id, target_wxid, "gift_receive",
                      {"item": item_key, "from_wxid": wxid_from})
    return {"action": "gift", "item": item_name, "to": target_name}


def cmd_item(group_id: int, wxid: str, action: str,
             item_key: str = "", qty: int = 1) -> dict:
    """/道具 [商店|购买|卖出|装备|卸下|使用] [道具名]"""
    if action == "库存":
        inventory = db.get_inventory(group_id, wxid)
        enriched = []
        for inv in inventory:
            item = ITEMS.get(inv["item_key"], {})
            enriched.append({
                **inv, "name": item.get("name", inv["item_key"]),
                "rarity": item.get("rarity", ""),
                "category": item.get("category", ""),
                "desc": item.get("desc", ""),
                "buy_price": item.get("buy", 0),
                "sell_price": item.get("buy", 0) // 2,
            })
        fish = db.get_fish(group_id, wxid)
        equipped = fish.get("equipped_item", "") if fish else ""
        equipped_info = None
        if equipped:
            ei = ITEMS.get(equipped, {})
            equipped_info = {"key": equipped, "name": ei.get("name", ""), "desc": ei.get("desc", "")}
        return {"action": "inventory", "inventory": enriched,
                "equipped": equipped_info}

    if action == "装备":
        item = ITEMS.get(item_key)
        if not item or item.get("category") != "equip":
            return {"error": f"{item_key} 不是装备类道具"}
        fish = db.get_fish(group_id, wxid)
        if not fish or not fish["is_alive"]:
            return {"error": "鱼不存在或已死亡"}
        # 检查库存
        inv = db.get_inventory(group_id, wxid)
        has = any(i["item_key"] == item_key and i["quantity"] > 0 for i in inv)
        if not has:
            return {"error": f"你没有 {item['name']}"}
        old_equip = fish.get("equipped_item", "")
        db.update_fish_field(group_id, wxid, "equipped_item", item_key)
        db.add_fish_event(group_id, wxid, "equip", {"item": item_key, "old": old_equip})
        return {"action": "equip", "item": item["name"], "bonus": item.get("bonus", 0),
                "stat": item.get("stat", ""), "old_equip": old_equip}

    if action == "卸下":
        fish = db.get_fish(group_id, wxid)
        if not fish or not fish["is_alive"]:
            return {"error": "鱼不存在或已死亡"}
        old = fish.get("equipped_item", "")
        if not old:
            return {"error": "没有装备任何道具"}
        db.update_fish_field(group_id, wxid, "equipped_item", "")
        db.add_fish_event(group_id, wxid, "unequip", {"item": old})
        return {"action": "unequip", "old_item": old}

    if action == "使用":
        item = ITEMS.get(item_key)
        if not item:
            return {"error": f"未知道具: {item_key}"}
        cat = item.get("category", "")
        if cat in ("equip", "collect"):
            return {"error": f"{item['name']} 是{'装备' if cat == 'equip' else '收藏'}类，不能直接使用。请用 /道具 装备"}

        if not db.remove_item(group_id, wxid, item_key, 1):
            return {"error": f"没有 {item['name']}"}

        # 饲料/训练/幸运类 → 存储到 active_consumable，下次对应指令自动触发
        db.update_fish_field(group_id, wxid, "active_consumable", item_key)
        db.add_fish_event(group_id, wxid, "item_use", {"item": item_key})
        return {"action": "use", "item": item["name"], "desc": item["desc"],
                "hint": "已激活，下次对应指令时自动生效"}

    return {"error": f"未知操作: {action}。可用: 库存 装备 卸下 使用"}


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
                message_count: int = 0,
                portrait_traits: list = None) -> dict:  # v1.16.0
    """创建一条新鱼（或重新领养）"""
    import json as _json
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

    # v1.16.0: 分配 3 个性格标签（1 从画像映射 + 2 随机）
    selected_traits = []
    implemented_traits = [k for k, v in FISH_TRAITS.items() if v]  # 排除占位
    if portrait_traits:
        for pt in portrait_traits:
            mapped = PORTRAIT_TO_FISH_TRAIT.get(pt)
            if mapped and mapped in implemented_traits and mapped not in selected_traits:
                selected_traits.append(mapped)
                break
    available = [t for t in implemented_traits if t not in selected_traits]
    rng = random.Random(f"traits_{group_id}_{wxid}")
    while len(selected_traits) < 3 and available:
        pick = rng.choice(available)
        selected_traits.append(pick)
        available.remove(pick)

    # v1.16.0: 随机选择 emoji 变体
    variants = EMOJI_VARIANTS.get(species, [species_info.get("emoji", "🐟")])
    emoji_variant = random.choice(variants) if variants else species_info.get("emoji", "🐟")

    max_hp_val = compute_max_hp(attrs["constitution"], 1, "鱼苗")
    fid = db.upsert_fish(
        group_id=group_id, wxid=wxid, fish_name=fish_name,
        species=species, rarity=rarity,
        strength=attrs["strength"], dexterity=attrs["dexterity"],
        constitution=attrs["constitution"], intelligence=attrs["intelligence"],
        wisdom=attrs["wisdom"], charisma=attrs["charisma"],
        experience=0, level=1, growth=0, happiness=60,
        hp=max_hp_val,
        stage="鱼苗", is_alive=1,
        energy=100, max_energy=100,  # v1.16.0
        personality_traits=_json.dumps(selected_traits, ensure_ascii=False),  # v1.16.0
        emoji_variant=emoji_variant,  # v1.16.0
        max_hp=max_hp_val,  # v1.16.3
    )

    db.add_fish_event(group_id, wxid, "born", {
        "species": species, "rarity": rarity, "fish_name": fish_name,
        "attributes": attrs,
        "personality_traits": selected_traits,  # v1.16.0
        "emoji_variant": emoji_variant,  # v1.16.0
    })

    logger.info(f"鱼创建: group={group_id} wxid={wxid} {fish_name} {rarity} traits={selected_traits}")

    fish = db.get_fish(group_id, wxid)
    return {"fish": fish, "species_info": species_info, "new": True}


# ==================== v1.16.0: 精力系统 + 性格系统 + Emoji多态 ====================

# 精力消耗表（正值=消耗，负值=恢复）
ACTION_ENERGY_COST = {
    "feed": 15, "touch": -20, "explore": 20,
    "showoff": 10, "battle": 25, "train": 30,
}

# 性格特性池（16 个已实现，6 个占位）
FISH_TRAITS = {
    "勇敢": {"desc": "面对掠食者有优势", "icon": "🦁"},
    "好奇": {"desc": "探索收益×1.5", "icon": "🔍"},
    "活泼": {"desc": "晒鱼/斗鱼精力消耗-5", "icon": "🤸"},
    "勤奋": {"desc": "精力消耗×0.8", "icon": "💪"},
    "谨慎": {"desc": "面对陷阱有优势", "icon": "🛡️"},
    "乐天": {"desc": "幸福值不低于10", "icon": "😊"},
    "傲娇": {"desc": "晒鱼CHA+2，训练效果×0.8", "icon": "💅"},
    "贪吃": {"desc": "喂食效果翻倍", "icon": "🍔"},
    "社牛": {"desc": "群体事件检定+2", "icon": "🎤"},
    "胆小": {"desc": "掠食者劣势，躲藏自动成功", "icon": "😨"},
    "懒惰": {"desc": "精力恢复+50%，成长×0.9", "icon": "😴"},
    "暴躁": {"desc": "战斗STR+2，社交CHA-2", "icon": "💢"},
    "沉稳": {"desc": "面对暴风雨有优势", "icon": "🧘"},
    "机灵": {"desc": "宝藏事件WIS+2", "icon": "🧠"},
    "粘人": {"desc": "主人当天发言≥5条→+5幸福", "icon": "🥰"},
    "孤僻": {"desc": "群体事件不参与", "icon": "🏚️"},
    # 占位
    "贪睡": {}, "迷糊": {}, "浪漫": {},
    "倔强": {}, "戏精": {}, "冒险家": {},
}

# 画像 → 性格映射（18 条）
PORTRAIT_TO_FISH_TRAIT = {
    "社牛": "社牛", "话痨": "活泼", "乐子人": "好奇",
    "潜水员": "胆小", "摸鱼大师": "懒惰", "理论家": "机灵",
    "气氛组": "乐天", "卷王": "勤奋", "吐槽役": "傲娇",
    "美食家": "贪吃", "和平主义者": "谨慎", "暴躁老哥": "暴躁",
    "夜猫子": "孤僻", "养生达人": "沉稳", "梗王": "活泼",
    "戏精": "戏精", "技术宅": "机灵", "小透明": "胆小",
}

# Emoji 多态变体（每个物种多个 emoji）
EMOJI_VARIANTS = {
    "goldfish": ["🐟", "🐟", "🐟", "🐠"],
    "koi": ["🎏", "🎏", "🐟"],
    "clownfish": ["🤡", "🐠", "🐟"],
    "betta": ["🐠", "🐠", "🐟"],
    "arowana": ["🐉", "🐲"],
    "angelfish": ["👼", "😇"],
    "shark": ["🦈", "🦈", "🐟"],
    "octopus": ["🐙", "🐙"],
    "squid": ["🦑", "🦑"],
    "crab": ["🦀", "🦀"],
    "lobster": ["🦞", "🦞"],
    "whale": ["🐋", "🐳"],
    "dolphin": ["🐬", "🐬"],
    "seal": ["🦭", "🦭"],
    "turtle": ["🐢", "🐢"],
    "frog": ["🐸", "🐸"],
}

# /领养 不在此表，由 create_fish 内 is_alive 检查控制（有存活鱼则不可领养）


# ==================== v1.16.0: 精力/性格辅助函数 ====================

def _count_today_events(group_id: int, wxid: str, event_type: str,
                        date_str: str = None) -> int:
    """统计某条鱼今天已执行某类指令的次数（仅摸鱼保留每日限制）"""
    from datetime import datetime as dt
    today = date_str or dt.now().strftime("%Y-%m-%d")
    conn = db.get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM fish_events
           WHERE group_id=? AND wxid=? AND event_type=?
           AND date(created_at)=?""",
        (group_id, wxid, event_type, today)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def _get_energy(group_id: int, wxid: str) -> tuple:
    """获取鱼的 (energy, max_energy)"""
    fish = db.get_fish(group_id, wxid)
    if not fish:
        return (0, 0)
    return (fish.get("energy", 100), fish.get("max_energy", 100))


def check_touch_daily_limit(group_id: int, wxid: str, date_str: str = None) -> dict | None:
    """摸鱼每日次数限制（唯一保留的每日上限）"""
    from config import config as cfg
    limit = getattr(cfg, "POND_TOUCH_DAILY_LIMIT", 5)
    count = _count_today_events(group_id, wxid, "touch", date_str)
    if count >= limit:
        return {"error": f"今日 /touch 次数已用完 ({count}/{limit})",
                "limit": limit, "used": count}
    return None


def _apply_trait_energy_mod(action: str, fish: dict) -> int:
    """根据鱼的性格修正精力消耗/恢复量"""
    import json
    cost = ACTION_ENERGY_COST.get(action, 0)
    traits_raw = fish.get("personality_traits", "[]")
    try:
        traits = json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
    except (json.JSONDecodeError, TypeError):
        return cost

    for trait in traits:
        if trait == "勤奋":
            cost = int(cost * 0.8) if cost > 0 else cost
        elif trait == "懒惰":
            cost = int(cost * 1.5) if cost < 0 else int(cost * 0.9) if cost > 0 else cost
        elif trait == "活泼" and action in ("showoff", "battle"):
            cost = max(0, cost - 5) if cost > 0 else cost
        elif trait == "贪吃" and action == "feed":
            cost = max(0, cost - 5) if cost > 0 else cost
    return cost


def check_energy(group_id: int, wxid: str, action: str) -> dict | None:
    """检查精力是否足够。返回 None 通过，返回 dict 表示失败。"""
    if action == "touch":
        return None  # 摸鱼恢复精力，永远有精力
    base_cost = ACTION_ENERGY_COST.get(action, 0)
    if base_cost <= 0:
        return None  # 恢复类动作
    fish = db.get_fish(group_id, wxid)
    if not fish:
        return {"error": "鱼不存在"}
    cost = _apply_trait_energy_mod(action, fish)
    energy = fish.get("energy", 100)
    if energy < cost:
        return {"error": f"精力不足！需要 {cost} 点精力，当前仅剩 {energy} 点",
                "energy_current": energy, "energy_needed": cost}
    return None


def spend_energy(group_id: int, wxid: str, action: str):
    """执行动作后扣除/恢复精力（含性格修正）"""
    fish = db.get_fish(group_id, wxid)
    if not fish:
        return
    cost = _apply_trait_energy_mod(action, fish)
    db.update_fish_energy(group_id, wxid, cost)


def regen_energy(group_id: int, wxid: str, amount: int = None):
    """恢复精力（含懒惰性格加成）"""
    from config import config as cfg
    if amount is None:
        amount = getattr(cfg, "POND_ENERGY_REGEN_AMOUNT", 5)
    fish = db.get_fish(group_id, wxid)
    if fish:
        import json
        traits_raw = fish.get("personality_traits", "[]")
        try:
            traits = json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
        except (json.JSONDecodeError, TypeError):
            pass
        else:
            if "懒惰" in traits:
                amount = int(amount * 1.5)
    db.update_fish_energy(group_id, wxid, -amount)  # negative = restore


# ==================== 互动指令 ====================

def cmd_feed(group_id: int, wxid: str, from_wxid: str = None,
             premium: bool = False, seed: str = None) -> dict:
    """/喂食：DEX 检定 DC10"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}
    # v1.16.0: 精力检查替代次数限制
    energy_check = check_energy(group_id, wxid, "feed")
    if energy_check:
        return energy_check

    traits = db.get_fish_traits(group_id, wxid)
    result = check_with_traits(fish["dexterity"], dc=10,
                               traits=traits, context="feed",
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

    # v1.16.0: 消耗精力
    spend_energy(group_id, wxid, "feed")

    return {
        "check": result.to_dict(), "growth_bonus": growth_bonus,
        "happiness_bonus": happiness_bonus, "evolved": evolved,
        "new_stage": new_stage, "xp": xp_result
    }


def cmd_touch(group_id: int, wxid: str, seed: str = None) -> dict:
    """/摸鱼：CHA 检定 DC12"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}
    # v1.16.0: 摸鱼保留每日5次上限，但恢复精力
    limit_check = check_touch_daily_limit(group_id, wxid)
    if limit_check:
        return limit_check

    traits = db.get_fish_traits(group_id, wxid)
    result = check_with_traits(fish["charisma"], dc=12,
                               traits=traits, context="touch",
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

    # v1.16.0: 摸鱼恢复精力
    spend_energy(group_id, wxid, "touch")

    return {"check": result.to_dict(), "intimacy_bonus": intimacy_bonus, "xp": xp_result}


def cmd_battle(group_id: int, wxid_a: str, wxid_b: str, seed: str = None) -> dict:
    """/斗鱼 @XX：STR 对抗检定"""
    fish_a = db.get_fish(group_id, wxid_a)
    fish_b = db.get_fish(group_id, wxid_b)
    if not fish_a or not fish_b or not fish_a["is_alive"] or not fish_b["is_alive"]:
        return {"error": "一方或双方鱼不存在/已死亡"}
    # v1.16.0: 精力检查替代次数限制
    energy_check = check_energy(group_id, wxid_a, "battle")
    if energy_check:
        return energy_check

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

    # v1.16.0: 消耗精力
    spend_energy(group_id, wxid_a, "battle")

    return {
        "check": result, "winner": winner_wxid, "loser": loser_wxid,
        "winner_growth": 20, "xp": xp_result
    }


def cmd_explore(group_id: int, wxid: str, seed: str = None) -> dict:
    """/探索：WIS/INT 检定 DC13，获得 1d10 鳞币"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}
    # v1.16.0: 精力检查替代次数限制
    energy_check = check_energy(group_id, wxid, "explore")
    if energy_check:
        return energy_check

    # 用较高的那个属性
    score = max(fish["wisdom"], fish["intelligence"])
    prof = "investigation" in get_proficiencies(fish["species"]) or \
          "nature" in get_proficiencies(fish["species"])

    traits = db.get_fish_traits(group_id, wxid)
    result = check_with_traits(score, dc=13,
                               traits=traits, context="explore",
                               is_proficient=prof, level=fish["level"], seed=seed)

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

    # v1.16.0: 消耗精力
    spend_energy(group_id, wxid, "explore")

    return {"check": result.to_dict(), "coin_amount": coin_amount, "xp": xp_result}


def cmd_showoff(group_id: int, wxid: str, seed: str = None) -> dict:
    """/晒鱼：CHA 检定，观众打赏"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}
    # v1.16.0: 精力检查替代次数限制
    energy_check = check_energy(group_id, wxid, "showoff")
    if energy_check:
        return energy_check

    traits = db.get_fish_traits(group_id, wxid)
    result = check_with_traits(fish["charisma"], dc=10,
                               traits=traits, context="showoff",
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

    # v1.16.0: 消耗精力
    spend_energy(group_id, wxid, "showoff")

    return {"check": result.to_dict(), "coin_amount": coin_amount}


# 训练属性名映射
TRAIN_ATTR_MAP = {
    "力量": ("strength", "athletics"),
    "敏捷": ("dexterity", "acrobatics"),
    "体质": ("constitution", "endurance"),
    "智力": ("intelligence", "investigation"),
    "感知": ("wisdom", "nature"),
    "魅力": ("charisma", "performance"),
}
TRAIN_COST = 30
TRAIN_ATTR_CAP = 20


def cmd_train(group_id: int, wxid: str, attr_name: str,
              seed: str = None) -> dict:
    """/训练 <属性名>：消耗鳞币训练单项属性，属值越高越难成功"""
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        return {"error": "鱼不存在或已死亡"}

    # 解析属性名
    attr_info = TRAIN_ATTR_MAP.get(attr_name)
    if not attr_info:
        valid = "、".join(TRAIN_ATTR_MAP.keys())
        return {"error": f"未知属性: {attr_name}，可选: {valid}"}

    attr_key, proficiency = attr_info
    current_val = fish[attr_key]
    if current_val >= TRAIN_ATTR_CAP:
        return {"error": f"{attr_name}已达上限({TRAIN_ATTR_CAP})"}

    # v1.16.0: 精力检查替代次数限制
    energy_check = check_energy(group_id, wxid, "train")
    if energy_check:
        return energy_check

    # 扣除鳞币
    wallet = db.spend_coins(group_id, wxid, TRAIN_COST, "train",
                           f"训练{attr_name}")
    if wallet is None:
        return {"error": f"鳞币不足，训练需要 {TRAIN_COST} 鳞币，当前余额不足"}

    # DC = 12 + 当前属性值（越高越难）
    dc = 12 + current_val
    traits = db.get_fish_traits(group_id, wxid)
    result = check_with_traits(current_val, dc=dc,
                               traits=traits, context="train",
                               is_proficient=proficiency in get_proficiencies(fish["species"]),
                               level=fish["level"], seed=seed)

    if result.success:
        new_val = current_val + 1
        db.update_fish_field(group_id, wxid, attr_key, new_val)
        # 更新 HP（体质影响 HP）
        if attr_key == "constitution":
            new_hp = compute_max_hp(new_val, fish["level"], fish["stage"])
            db.update_fish_field(group_id, wxid, "hp", new_hp)
            db.update_fish_field(group_id, wxid, "max_hp", new_hp)
        xp_amount = 15
        xp_result = add_xp(group_id, wxid, xp_amount, "train")
        attr_increased = True
    else:
        xp_amount = 3
        xp_result = add_xp(group_id, wxid, xp_amount, "train")
        attr_increased = False
        new_val = current_val

    db.add_fish_event(group_id, wxid, "train", {
        **result.to_dict(), "attr_name": attr_name, "attr_key": attr_key,
        "old_val": current_val, "new_val": new_val,
        "dc": dc, "coin_cost": TRAIN_COST, "success": result.success,
    })

    # v1.16.0: 消耗精力
    spend_energy(group_id, wxid, "train")

    return {
        "check": result.to_dict(), "attr_name": attr_name, "attr_key": attr_key,
        "old_val": current_val, "new_val": new_val,
        "increased": attr_increased, "dc": dc, "coin_cost": TRAIN_COST,
        "xp": xp_result,
    }


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
    # v1.16.0: 尝试从画像获取性格映射
    portrait_traits = None
    try:
        import json as _json
        conn = db.get_conn()
        member = conn.execute(
            "SELECT id FROM group_members WHERE group_id=? AND wxid=?", (group_id, wxid)
        ).fetchone()
        conn.close()
        if member:
            portrait = db.get_portrait(group_id, member["id"])
            if portrait and portrait.get("portrait_json"):
                portrait_data = _json.loads(portrait["portrait_json"])
                if isinstance(portrait_data, dict):
                    portrait_traits = portrait_data.get("traits", [])
    except Exception:
        pass
    return create_fish(group_id, wxid, display_name,
                       message_count=message_count, portrait_traits=portrait_traits)


# ==================== v1.16.2: 升级 + 决议 + 领养 + 热搜 + 称号 ====================

UPGRADE_COSTS = [100, 300, 600, 1000, 1500]  # Lv1→5 各等级消耗

UPGRADE_DEFS = {
    "purifier":  {"name": "💧 净水器", "desc": "疾病概率 -15%/级", "icon": "💧"},
    "shark_net": {"name": "🛡️ 防鲨网", "desc": "掠食者伤害 -2/级", "icon": "🛡️"},
    "nutrient":  {"name": "🌿 营养剂", "desc": "全体日成长 +1/级", "icon": "🌿"},
    "radar":     {"name": "📡 探测器", "desc": "宝藏概率 ×1.2/级", "icon": "📡"},
    "medbay":    {"name": "🏥 医疗站", "desc": "日自动回血 +1HP/级", "icon": "🏥"},
}

DECREE_DEFS = {
    "feed_all":    {"name": "🍞 全员投喂", "cost": 50,  "daily": 3,  "desc": "全体鱼获得喂食效果"},
    "energy_boost":{"name": "⚡ 精力补给", "cost": 80,  "daily": 2,  "desc": "全体鱼恢复 30 精力"},
    "elite_train": {"name": "🎓 精英培训", "cost": 200, "daily": 1,  "desc": "选一只鱼，随机属性+2", "needs_target": True},
    "heal":        {"name": "💊 急救包",   "cost": 30,  "daily": 5,  "desc": "选一只鱼，HP 回满", "needs_target": True},
    "force_event": {"name": "🎪 举办活动", "cost": 300, "daily": 1,  "desc": "强制触发一次稀有事件"},
    "rain":        {"name": "🌧️ 人工降雨", "cost": 100, "daily": 2,  "desc": "触发有益群体事件"},
    "clean":       {"name": "🪣 清理鱼塘", "cost": 20,  "daily": 3,  "desc": "全体 happiness+5，精力+10"},
    "title_award": {"name": "🏆 命名表彰", "cost": 50,  "daily": 999,"desc": "给鱼授予特殊称号", "needs_target": True},
}

POND_KEEPER_TITLES = {
    "newbie":          {"label": "🌱 新手塘主", "desc": "首次开启自动事件"},
    "builder":         {"label": "🏗️ 基建狂魔", "desc": "任意升级达到 Lv5"},
    "gambler":         {"label": "🎰 赌怪",     "desc": "手动触发事件 50 次"},
    "capitalist":      {"label": "💰 资本家",   "desc": "金库余额突破 5000"},
    "necromancer":     {"label": "👻 亡灵法师", "desc": "幽灵鱼复活 3 条鱼"},
    "dragon_lord":     {"label": "🐉 龙骑士",   "desc": "拥有 5 条传说级鱼"},
    "sweeper":         {"label": "🧹 勤劳清洁工","desc": "清理鱼塘 30 次"},
    "philanthropist":  {"label": "🎁 大慈善家", "desc": "全员投喂 50 次"},
}


def upgrade_pond(group_id: int, upgrade_key: str) -> dict:
    """升级鱼塘设施：检查金库→扣钱→升级+1"""
    if upgrade_key not in UPGRADE_DEFS:
        return {"error": f"未知升级项: {upgrade_key}"}

    treasury = db.get_treasury(group_id)
    current = _get_upgrade_level(group_id, upgrade_key)
    if current >= 5:
        return {"error": f"{UPGRADE_DEFS[upgrade_key]['name']}已满级(Lv5)"}

    cost = UPGRADE_COSTS[current]  # current=0→cost=100, current=4→cost=1500
    if treasury["balance"] < cost:
        return {"error": f"金库余额不足，需要 {cost} 鳞币，当前 {treasury['balance']}"}

    db.add_treasury(group_id, -cost, "upgrade",
                    f"{UPGRADE_DEFS[upgrade_key]['name']} Lv{current+1}→Lv{current+2}")
    db.set_upgrade(group_id, upgrade_key, current + 1)

    return {"upgrade_key": upgrade_key, "name": UPGRADE_DEFS[upgrade_key]["name"],
            "new_level": current + 1, "cost": cost}


def execute_decree(group_id: int, decree_key: str,
                   target_wxid: str = None) -> dict:
    """执行塘主决议"""
    if decree_key not in DECREE_DEFS:
        return {"error": f"未知决议: {decree_key}"}

    d = DECREE_DEFS[decree_key]
    daily = d.get("daily", 1)
    count = db.count_today_decrees(group_id, decree_key)
    if count >= daily:
        return {"error": f"{d['name']}今日已达上限 ({count}/{daily})"}

    treasury = db.get_treasury(group_id)
    cost = d["cost"]
    if treasury["balance"] < cost:
        return {"error": f"金库余额不足，需要 {cost} 鳞币，当前 {treasury['balance']}"}

    if d.get("needs_target") and not target_wxid:
        return {"error": "此决议需要指定目标鱼"}

    # 执行效果
    alive = db.get_alive_fish(group_id)
    effect = {}

    if decree_key == "feed_all":
        for fish in alive:
            cmd_feed(group_id, fish["wxid"], seed=f"decree_feed_{fish['wxid']}")
        effect["fed_count"] = len(alive)

    elif decree_key == "energy_boost":
        for fish in alive:
            db.update_fish_energy(group_id, fish["wxid"], -30)
        effect["boosted"] = len(alive)

    elif decree_key == "elite_train":
        attrs = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
        attr = random.choice(attrs)
        fish = db.get_fish(group_id, target_wxid)
        if fish:
            db.update_fish_field(group_id, target_wxid, attr, fish.get(attr, 10) + 2)
            effect = {"wxid": target_wxid, "attr": attr, "new_val": fish.get(attr, 10) + 2}

    elif decree_key == "heal":
        fish = db.get_fish(group_id, target_wxid)
        if fish:
            max_hp = compute_max_hp(fish.get("constitution", 10), fish.get("level", 1), fish.get("stage", "成鱼"))
            db.update_fish_field(group_id, target_wxid, "hp", max_hp)
            db.update_fish_field(group_id, target_wxid, "max_hp", max_hp)
            effect = {"wxid": target_wxid, "hp": max_hp}

    elif decree_key == "force_event":
        from services.passive_events import trigger_passive_events
        results = trigger_passive_events(group_id)
        effect = {"events": len(results)}

    elif decree_key == "rain":
        for fish in alive:
            g = fish.get("growth", 0) + 5
            h = min(100, fish.get("happiness", 50) + 5)
            db.update_fish_field(group_id, fish["wxid"], "growth", g)
            db.update_fish_field(group_id, fish["wxid"], "happiness", h)
            db.update_fish_energy(group_id, fish["wxid"], -10)
        effect = {"growth": 5, "happiness": 5, "energy": 10}

    elif decree_key == "clean":
        for fish in alive:
            h = min(100, fish.get("happiness", 50) + 5)
            db.update_fish_field(group_id, fish["wxid"], "happiness", h)
            db.update_fish_energy(group_id, fish["wxid"], -10)
        effect = {"happiness": 5, "energy": 10}

    elif decree_key == "title_award":
        db.update_fish_field(group_id, target_wxid, "fish_name",
                           f"{db.get_fish(group_id, target_wxid)['fish_name']}🏅")
        effect = {"wxid": target_wxid}

    # 扣金库 + 记录事件
    db.add_treasury(group_id, -cost, "decree",
                    f"{d['name']}消耗 {cost} 鳞币")
    db.add_fish_event(group_id, target_wxid or "", f"decree_{decree_key}",
                      {"decree": decree_key, "cost": cost, "effect": effect})

    # 称号检查
    _check_keeper_titles(group_id, decree_key)

    return {"decree": decree_key, "name": d["name"], "cost": cost, "effect": effect}


def batch_adopt(group_id: int) -> list[dict]:
    """一键领养：为所有没有存活鱼的群成员创建鱼"""
    conn = db.get_conn()
    members = conn.execute(
        "SELECT wxid, display_name FROM group_members WHERE group_id = ?", (group_id,)
    ).fetchall()
    conn.close()

    results = []
    for m in members:
        existing = db.get_fish(group_id, m["wxid"])
        if existing and existing.get("is_alive"):
            continue
        import json as _json
        portrait_traits = None
        try:
            conn2 = db.get_conn()
            mb = conn2.execute(
                "SELECT id FROM group_members WHERE group_id=? AND wxid=?", (group_id, m["wxid"])
            ).fetchone()
            conn2.close()
            if mb:
                portrait = db.get_portrait(group_id, mb["id"])
                if portrait and portrait.get("portrait_json"):
                    pd = _json.loads(portrait["portrait_json"])
                    if isinstance(pd, dict):
                        portrait_traits = pd.get("traits", [])
        except Exception:
            pass
        result = create_fish(group_id, m["wxid"], m["display_name"] or m["wxid"],
                           portrait_traits=portrait_traits)
        results.append({"wxid": m["wxid"], "display_name": m["display_name"],
                       "fish_name": result.get("fish", {}).get("fish_name", ""),
                       "species": result.get("species_info", {}).get("name", "")})

    return results


def get_hot_search(group_id: int, days: int = 7) -> dict:
    """鱼塘热搜榜：从 fish_events 聚合"""
    from datetime import datetime as dt, timedelta
    since = (dt.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = db.get_conn()

    # 最卷鱼王
    trains = conn.execute(
        """SELECT wxid, COUNT(*) as cnt FROM fish_events
           WHERE group_id=? AND event_type='train' AND created_at >= ?
           GROUP BY wxid ORDER BY cnt DESC LIMIT 1""",
        (group_id, since)
    ).fetchone()

    # 最欧锦鲤
    treasures = conn.execute(
        """SELECT wxid, COUNT(*) as cnt FROM fish_events
           WHERE group_id=? AND event_type='treasure' AND created_at >= ?
           GROUP BY wxid ORDER BY cnt DESC LIMIT 1""",
        (group_id, since)
    ).fetchone()

    # 斗鱼狂魔
    battles = conn.execute(
        """SELECT wxid, COUNT(*) as cnt FROM fish_events
           WHERE group_id=? AND event_type='battle' AND created_at >= ?
           GROUP BY wxid ORDER BY cnt DESC LIMIT 1""",
        (group_id, since)
    ).fetchone()

    conn.close()

    def fish_name(wxid):
        if not wxid: return "—"
        f = db.get_fish(group_id, wxid)
        return f["fish_name"] if f else wxid[:12]

    return {
        "most_trained":    {"label": "🔥 最卷鱼王", "fish": fish_name(trains["wxid"]) if trains else "—", "data": trains["cnt"] if trains else 0},
        "most_treasures":  {"label": "🍀 最欧锦鲤", "fish": fish_name(treasures["wxid"]) if treasures else "—", "data": treasures["cnt"] if treasures else 0},
        "most_battles":    {"label": "🥊 斗鱼狂魔", "fish": fish_name(battles["wxid"]) if battles else "—", "data": battles["cnt"] if battles else 0},
    }


def _get_upgrade_level(group_id: int, upgrade_key: str) -> int:
    upgrades = {u["upgrade_key"]: u["level"] for u in db.get_upgrades(group_id)}
    return upgrades.get(upgrade_key, 0)


def _check_keeper_titles(group_id: int, context: str = ""):
    """检查并解锁塘主称号"""
    import json as _json
    conn = db.get_conn()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'pond_keeper_titles'"
    ).fetchone()
    conn.close()
    unlocked = _json.loads(row["value"]) if row and row["value"] else []

    treasury = db.get_treasury(group_id)
    upgrades = {u["upgrade_key"]: u["level"] for u in db.get_upgrades(group_id)}
    alive = db.get_alive_fish(group_id)

    checks = {
        "newbie": lambda: "newbie" not in unlocked,
        "builder": lambda: any(v >= 5 for v in upgrades.values()),
        "capitalist": lambda: treasury["balance"] >= 5000,
        "dragon_lord": lambda: sum(1 for f in alive if f.get("rarity") == "传说") >= 5,
    }

    for key, check in checks.items():
        if key not in unlocked and key in POND_KEEPER_TITLES and check():
            unlocked.append(key)

    conn = db.get_conn()
    conn.execute(
        """INSERT INTO app_settings (key, value, value_type, description)
           VALUES ('pond_keeper_titles', ?, 'string', '塘主已解锁称号')
           ON CONFLICT(key) DO UPDATE SET value = ?""",
        (_json.dumps(unlocked, ensure_ascii=False), _json.dumps(unlocked, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


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
        new_max_hp = compute_max_hp(fish["constitution"], fish["level"], new_stage)
        db.update_fish_field(group_id, wxid, "hp", new_max_hp)
        db.update_fish_field(group_id, wxid, "max_hp", new_max_hp)
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

    # v1.16.0: 结算时恢复精力
    regen_energy(group_id, wxid)
    events.append({"type": "energy_regen", "amount": _get_energy(group_id, wxid)[0]})

    # v1.16.1: 生成今日状态语
    try:
        from services.passive_events import generate_daily_status
        today_evts = db.get_fish_events(group_id, wxid, 20)
        status = generate_daily_status(wxid, today_evts)
        if status:
            db.update_fish_field(group_id, wxid, "personality_traits",
                               fish.get("personality_traits", "[]"))
            # 状态语存入 fish_events
            db.add_fish_event(group_id, wxid, "daily_status", {"status": status})
            events.append({"type": "daily_status", "text": status})
    except Exception:
        pass

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
            # v1.16.1: 附加遗言
            from services.passive_events import FISH_LAST_WORDS
            import random as _random
            last_words = _random.choice(FISH_LAST_WORDS)
            db.add_fish_event(group_id, victim["wxid"], "shark_attack", {
                "victim": victim["fish_name"], "date": date_str,
                "last_words": last_words,
            })
            results.append({"wxid": victim["wxid"], "shark_attack": True,
                           "victim": victim["fish_name"],
                           "last_words": last_words})

    # 生成黑市
    black_market = generate_black_market(group_id, date_str)

    return {
        "settled": True,
        "date": date_str,
        "weather": weather,
        "results": results,
        "fish_count": len(alive_fish),
        "black_market": [{
            "key": bm["key"],
            "name": ITEMS.get(bm["key"], {}).get("name", bm["key"]),
            "price": bm["price"],
            "stock": bm["stock"],
            "rarity": ITEMS.get(bm["key"], {}).get("rarity", ""),
            "desc": ITEMS.get(bm["key"], {}).get("desc", ""),
        } for bm in black_market],
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

    # v1.16.1: 金库 + 自动事件状态
    from config import config as _cfg
    try:
        treasury = db.get_treasury(group_id)
    except Exception:
        treasury = {"balance": 0, "total_earned": 0, "total_spent": 0}

    return {
        "weather": weather,
        "fish": enriched,
        "alive_count": len([f for f in fish_list if f.get("is_alive")]),
        "dead_count": len([f for f in fish_list if not f.get("is_alive")]),
        "leaderboards": leaderboards,
        "coin_leaders": coin_leaders,
        "recent_events": recent_events,
        "auto_events_enabled": getattr(_cfg, "POND_AUTO_EVENTS_ENABLED", False),
        "treasury": treasury,
    }


# ==================== 历史消息指令解析 ====================

_COMMAND_PATTERNS = [
    (r"^/领养$", "adopt"),
    (r"^/喂食$", "feed"),
    (r"^/摸鱼$", "touch"),
    (r"^/斗鱼\s*@(.+)$", "battle"),
    (r"^/探索$", "explore"),
    (r"^/晒鱼$", "showoff"),
    (r"^/鱼塘$", "pond"),
    (r"^/购买\s+(.+)$", "buy"),
    (r"^/赠予\s*@(.+?)\s+(.+)$", "gift"),
    (r"^/道具$", "item_list"),
    (r"^/道具\s+(.+)$", "item_action"),
    (r"^/训练\s+(.+)$", "train"),
    (r"^/改名\s+(.+)$", "rename"),
    (r"^/休息$", "rest"),  # v1.16.0
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
            elif cmd_type == "buy":
                result["item_key"] = m.group(1).strip()
            elif cmd_type == "gift":
                result["target_name"] = m.group(1).strip()
                result["item_key"] = m.group(2).strip()
            elif cmd_type == "rename":
                result["new_name"] = m.group(1).strip()
            elif cmd_type == "train":
                result["attr_name"] = m.group(1).strip()
            elif cmd_type == "item_action":
                parts = m.group(1).strip().split(None, 1)
                result["item_action"] = parts[0] if parts else ""
                result["item_key"] = parts[1] if len(parts) > 1 else ""
            elif cmd_type == "item_list":
                result["item_action"] = "库存"
                result["item_key"] = ""
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
            elif cmd["type"] == "showoff":
                result = cmd_showoff(group_id, wxid, seed=seed)
            elif cmd["type"] == "buy":
                result = cmd_buy(group_id, wxid, cmd.get("item_key", ""))
            elif cmd["type"] == "gift":
                result = cmd_gift(group_id, wxid,
                                  cmd.get("target_name", ""),
                                  cmd.get("item_key", ""))
            elif cmd["type"] in ("item_list", "item_action"):
                result = cmd_item(group_id, wxid,
                                  cmd.get("item_action", "库存"),
                                  cmd.get("item_key", ""))
            elif cmd["type"] == "train":
                result = cmd_train(group_id, wxid, cmd.get("attr_name", ""), seed=seed)
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


def resettle_day(group_id: int, date_str: str, messages: list[dict],
                 get_name_by_wxid) -> dict:
    """重新结算指定日期：只处理该天尚未结算的指令 + 天结算

    已结算判定：检查 fish_events 中当天该 wxid 该指令类型是否已达每日上限。
    已达上限的指令直接跳过，未达上限的执行并可能触发新的限额。

    Returns:
        {date, skipped: N, processed: [...], settle: {...}}
    """
    skipped = []
    processed = []
    errors = []

    for msg in sorted(messages, key=lambda m: m.get("createTime", 0)):
        content = (msg.get("content") or "").strip()
        if not is_game_command(content):
            continue

        cmd = parse_command(content)
        if not cmd:
            continue

        wxid = msg.get("wxid", "")
        if not wxid:
            continue

        # v1.16.0: 检查精力（替代每日上限）
        action = cmd["type"]
        cost = ACTION_ENERGY_COST.get(action, 0)
        if cost > 0:
            fish = db.get_fish(group_id, wxid)
            if fish:
                energy = fish.get("energy", 100)
                adj_cost = _apply_trait_energy_mod(action, fish)
                if energy < adj_cost:
                    skipped.append({
                        "wxid": wxid, "type": action, "content": content,
                        "reason": f"精力不足 ({energy}/{adj_cost})",
                        "time": msg.get("formattedTime", ""),
                    })
                    continue

        display_name = get_name_by_wxid(wxid)
        seed = f"cmd_{group_id}_{msg.get('platformMessageId', '')}"

        try:
            result = _execute_command(cmd, group_id, wxid, display_name, seed)
            processed.append({
                "type": cmd["type"], "wxid": wxid,
                "display_name": display_name, "content": content,
                "result": result, "time": msg.get("formattedTime", ""),
            })
        except Exception as e:
            logger.error(f"resettle 指令执行失败: {content} | {e}")
            errors.append({"msg": content, "error": str(e)})

    # 天结算
    settle_result = settle_all_fish(group_id, date_str)

    return {
        "date": date_str,
        "skipped": len(skipped),
        "skipped_details": skipped,
        "processed_count": len(processed),
        "processed": processed,
        "errors": errors,
        "settle": {
            "weather": settle_result.get("weather"),
            "fish_count": settle_result.get("fish_count"),
        },
    }


def _execute_command(cmd: dict, group_id: int, wxid: str,
                     display_name: str, seed: str = None) -> dict:
    """执行单条指令（内部共用）"""
    if cmd["type"] == "adopt":
        return cmd_adopt(group_id, wxid, display_name)
    elif cmd["type"] == "feed":
        return cmd_feed(group_id, wxid, seed=seed)
    elif cmd["type"] == "touch":
        return cmd_touch(group_id, wxid, seed=seed)
    elif cmd["type"] == "explore":
        return cmd_explore(group_id, wxid, seed=seed)
    elif cmd["type"] == "showoff":
        return cmd_showoff(group_id, wxid, seed=seed)
    elif cmd["type"] == "battle":
        target_wxid = _find_wxid_by_name(group_id, cmd.get("target_name", ""))
        if target_wxid:
            return cmd_battle(group_id, wxid, target_wxid, seed=seed)
        return {"error": f"找不到目标: {cmd.get('target_name', '')}"}
    elif cmd["type"] == "buy":
        return cmd_buy(group_id, wxid, cmd.get("item_key", ""))
    elif cmd["type"] == "gift":
        return cmd_gift(group_id, wxid,
                        cmd.get("target_name", ""),
                        cmd.get("item_key", ""))
    elif cmd["type"] in ("item_list", "item_action"):
        return cmd_item(group_id, wxid,
                        cmd.get("item_action", "库存"),
                        cmd.get("item_key", ""))
    elif cmd["type"] == "train":
        return cmd_train(group_id, wxid, cmd.get("attr_name", ""), seed=seed)
    elif cmd["type"] == "rename":
        return cmd_rename(group_id, wxid, cmd.get("new_name", ""))
    elif cmd["type"] == "rest":  # v1.16.0
        fish = db.get_fish(group_id, wxid)
        if not fish or not fish["is_alive"]:
            return {"error": "鱼不存在或已死亡"}
        energy, max_energy = _get_energy(group_id, wxid)
        if energy >= max_energy:
            return {"type": "rest", "energy": energy, "max_energy": max_energy,
                    "restored": 0, "message": "精力已满"}
        rest_amount = max_energy - energy
        regen_energy(group_id, wxid, rest_amount)
        fish = db.get_fish(group_id, wxid)
        return {"type": "rest", "energy": fish.get("energy", max_energy),
                "max_energy": max_energy, "restored": rest_amount,
                "message": f"恢复了 {rest_amount} 点精力"}
    elif cmd["type"] == "pond":
        db.add_fish_event(group_id, wxid, "pond_view", {})
        return {"type": "pond", "status": "viewed"}
    return {"error": f"未知指令类型: {cmd.get('type', '')}"}


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
