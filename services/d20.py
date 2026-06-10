"""
D20 检定引擎：标准 D&D 5e SRD 规则子集

用法：
    from services.d20 import ability_check, ability_modifier, proficiency_bonus

    result = ability_check(ability_score=16, dc=10, is_proficient=True, level=3)
    if result.success:
        print(f"检定成功! d20={result.roll} + {result.modifier} = {result.total}")
"""

import random
from dataclasses import dataclass, field


@dataclass
class D20Result:
    """一次 d20 检定的完整结果"""
    roll: int                    # d20 原始掷骰 (1-20)
    modifier: int                # 属性调整值 + 熟练加值
    total: int                   # roll + modifier
    dc: int                      # 难度等级
    success: bool                # total >= dc
    critical_hit: bool = False   # roll == 20 (自然20)
    critical_miss: bool = False  # roll == 1 (自然1)

    def __post_init__(self):
        self.critical_hit = self.roll == 20
        self.critical_miss = self.roll == 1

    def to_dict(self) -> dict:
        return {
            "roll": self.roll,
            "modifier": self.modifier,
            "total": self.total,
            "dc": self.dc,
            "success": self.success,
            "critical_hit": self.critical_hit,
            "critical_miss": self.critical_miss,
        }

    def describe(self) -> str:
        """人类可读的检定描述"""
        parts = [f"d20({self.roll}) + {self.modifier} = {self.total}"]
        if self.critical_hit:
            parts.append("🎉 大成功!")
        elif self.critical_miss:
            parts.append("💀 大失败!")
        parts.append(f"{'✅ 成功' if self.success else '❌ 失败'} (DC={self.dc})")
        return " | ".join(parts)


def ability_modifier(score: int) -> int:
    """属性调整值 = floor((score - 10) / 2)

    >>> ability_modifier(16)
    3
    >>> ability_modifier(8)
    -1
    """
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    """熟练加值，随等级成长

    Lv1-3: +2, Lv4-5: +3, Lv6-8: +4, Lv9-10: +5
    """
    if level < 1:
        return 2
    return (level - 1) // 3 + 2  # 1-3→2, 4-6→3, 7-9→4, 10+→5


def roll_d20(seed: str = None) -> int:
    """掷一个 d20

    Args:
        seed: 可选的确定性种子（用于回放/测试），
              格式如 "group_1_wxid_abc_2025-06-01_feed"
    """
    if seed is not None:
        rng = random.Random(seed)
        return rng.randint(1, 20)
    return random.randint(1, 20)


def ability_check(ability_score: int, dc: int,
                  is_proficient: bool = False, level: int = 1,
                  advantage: bool = False, disadvantage: bool = False,
                  seed: str = None) -> D20Result:
    """标准能力检定

    Args:
        ability_score: 属性值 (6-22)
        dc: 难度等级
        is_proficient: 是否有熟练项
        level: 角色等级
        advantage: 优势（掷两次取高）
        disadvantage: 劣势（掷两次取低）
        seed: 确定性种子

    Returns:
        D20Result: 完整检定结果

    Example:
        # 斗鱼：STR 16, 熟练运动, Lv3, vs DC 14 (对手AC)
        result = ability_check(16, 14, is_proficient=True, level=3)
    """
    mod = ability_modifier(ability_score)
    prof = proficiency_bonus(level) if is_proficient else 0
    total_mod = mod + prof

    if advantage and disadvantage:
        advantage = disadvantage = False  # 优劣势抵消

    if advantage:
        r1 = roll_d20(seed + "_adv1" if seed else None)
        r2 = roll_d20(seed + "_adv2" if seed else None)
        roll = max(r1, r2)
    elif disadvantage:
        r1 = roll_d20(seed + "_dis1" if seed else None)
        r2 = roll_d20(seed + "_dis2" if seed else None)
        roll = min(r1, r2)
    else:
        roll = roll_d20(seed)

    total = roll + total_mod
    return D20Result(
        roll=roll,
        modifier=total_mod,
        total=total,
        dc=dc,
        success=total >= dc,
    )


def opposed_check(attacker_score: int, defender_score: int,
                  att_prof: bool = False, def_prof: bool = False,
                  level: int = 1,
                  seed: str = None) -> dict:
    """对抗检定（用于 /斗鱼）

    双方各掷 d20 + 调整值，比较结果。
    平手时攻方胜（D&D 规则：对抗检定平手维持现状）。

    Returns:
        {
            "attacker": D20Result,
            "defender": D20Result,
            "winner": "attacker" | "defender",
            "margin": int  # 胜方超过败方的差值
        }
    """
    att_mod = ability_modifier(attacker_score) + (proficiency_bonus(level) if att_prof else 0)
    def_mod = ability_modifier(defender_score) + (proficiency_bonus(level) if def_prof else 0)

    att_roll = roll_d20(seed + "_att" if seed else None)
    def_roll = roll_d20(seed + "_def" if seed else None)

    att_total = att_roll + att_mod
    def_total = def_roll + def_mod

    att_result = D20Result(att_roll, att_mod, att_total, dc=def_total + 1,
                           success=att_total >= def_total + 1)
    def_result = D20Result(def_roll, def_mod, def_total, dc=att_total,
                           success=def_total >= att_total)

    if att_total >= def_total:
        winner = "attacker"
        margin = att_total - def_total
    else:
        winner = "defender"
        margin = def_total - att_total

    return {
        "attacker": att_result.to_dict(),
        "defender": def_result.to_dict(),
        "winner": winner,
        "margin": margin,
    }


def saving_throw(ability_score: int, dc: int,
                 is_proficient: bool = False, level: int = 1,
                 seed: str = None) -> D20Result:
    """豁免检定

    与能力检定规则相同，但语义不同（被动抵抗而非主动尝试）。
    用于：抵抗暴风雨、躲避鲨鱼、抵御疾病。
    """
    return ability_check(ability_score, dc,
                        is_proficient=is_proficient, level=level, seed=seed)


def roll_dice(dice_str: str, seed: str = None) -> tuple[int, list[int]]:
    """掷多面骰

    Args:
        dice_str: 如 "1d10", "2d6", "3d4+2"
        seed: 确定性种子

    Returns:
        (total, [individual_rolls])

    Example:
        >>> roll_dice("1d10")
        (7, [7])
        >>> roll_dice("2d6")
        (8, [3, 5])
    """
    parts = dice_str.lower().split("d")
    count = int(parts[0])
    bonus = 0
    face_part = parts[1]
    if "+" in face_part:
        face, bonus = face_part.split("+")
        bonus = int(bonus)
    elif "-" in face_part:
        face, bonus = face_part.split("-")
        bonus = -int(bonus)
    else:
        face = face_part
    face = int(face)

    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    rolls = [rng.randint(1, face) for _ in range(count)]
    total = sum(rolls) + bonus
    return total, rolls


# ---- 便捷函数 ----

def coin_roll(dice_str: str, seed: str = None) -> int:
    """掷骰获得鳞币数量（只返回总数）"""
    total, _ = roll_dice(dice_str, seed)
    return total
