"""
鱼塘日报生成器 — 基于 DeepSeek 将解析日志写成自然语言日报
"""
import json
import logging
from datetime import datetime

from config import config
from services.online_model import call_deepseek_chat
from services import fish_pond as fp
from models import database as db

logger = logging.getLogger(__name__)

FISH_DAILY_PROMPT = """你是一个群聊养鱼游戏的日报记者，驻守在"群鱼塘"旁边，每天写一份生动有趣的鱼塘日报。

你的读者是群聊成员，他们每人拥有一条鱼，每天通过发言活跃度获得成长，通过 /指令 互动。

写作要求：
1. 语气轻松幽默，像一个热心的鱼塘管理员在唠嗑
2. 把数据翻译成人话，不要列数字表格，要讲故事
3. 每条鱼都有自己的"人设"——稀有度高的鱼更有排面，力量高的鱼很能打，魅力高的鱼是群宠
4. 突出今天的亮点事件（谁进化了、谁斗鱼赢了、谁领养了新鱼）
5. 黑市商品要推荐一两件最值的，制造紧迫感
6. 如果今天无事发生，就写写天气、鱼的近况，鼓励大家明天多互动
7. 字数控制在 300-500 字
8. 不要用 markdown 表格，用自然段落

输出纯文本格式的日报。"""


async def generate_fish_daily_report(
    group_id: int,
    date_str: str,
    parse_log: list[dict] = None,
    settle_result: dict = None
) -> dict:
    """生成鱼塘日报

    Args:
        group_id: 群 ID
        date_str: 日期 YYYY-MM-DD
        parse_log: 解析日志条目列表 (from parse-commands)
        settle_result: 结算结果 (from settle_all_fish)

    Returns:
        {"success": bool, "report": str, "model": str, "duration_ms": int}
    """
    # 构建提示词
    user_parts = [f"日期: {date_str}"]

    # 天气
    weather = (settle_result or {}).get("weather", {})
    if weather:
        user_parts.append(
            f"今日天气: {weather.get('emoji', '')} {weather.get('name', '')} — {weather.get('effect', '')}"
        )

    # 鱼塘概况
    alive = db.get_alive_fish(group_id)
    user_parts.append(f"鱼塘概况: {len(alive)} 条鱼")

    # 成功的指令日志
    if parse_log:
        events = []
        for entry in parse_log:
            if entry.get("error"):
                continue
            sender = entry.get("sender", "?")
            cmd = entry.get("command", "")
            d20 = entry.get("d20", {})
            growth = entry.get("growth", 0)
            coins = entry.get("coin_amount", 0)
            happiness = entry.get("happiness", 0)
            fish_info = entry.get("fish", {})
            evolved = entry.get("evolved")

            desc = f"{sender} 执行了 {cmd}"
            if d20:
                roll_desc = f"d20={d20.get('roll')}+{d20.get('modifier')}={d20.get('total')} vs DC{d20.get('dc')}"
                if d20.get("critical_hit"):
                    roll_desc += " 大成功!"
                elif d20.get("critical_miss"):
                    roll_desc += " 大失败!"
                elif d20.get("success"):
                    roll_desc += " 成功"
                else:
                    roll_desc += " 失败"
                desc += f" [{roll_desc}]"
            if growth:
                desc += f" 成长+{growth}"
            if coins:
                desc += f" 鳞币+{coins}"
            if happiness:
                desc += f" 幸福+{happiness}"
            if evolved:
                desc += " 并进化了!"
            if fish_info:
                desc += f" 获得了{fish_info.get('rarity', '')}的{fish_info.get('name', '')}"
            events.append(desc)
        if events:
            user_parts.append("今日群友动态:\n" + "\n".join(events))
        else:
            user_parts.append("今日群友动态: 暂无，大家都在潜水...")
    else:
        user_parts.append("今日暂无指令动态")

    # 结算摘要
    if settle_result:
        results = settle_result.get("results", [])
        evolutions = [r for r in results if
                      any(e.get("type") == "evolve" for e in r.get("events", []))]
        sharks = [r for r in results if r.get("shark_attack")]
        if evolutions:
            names = [r.get("fish_name", "?") for r in evolutions]
            user_parts.append(f"今日进化: {', '.join(names)}")
        if sharks:
            names = [r.get("victim", "?") for r in sharks]
            user_parts.append(f"💀 鲨鱼来袭! 遇难者: {', '.join(names)}")

    # 黑市
    bm = (settle_result or {}).get("black_market", [])
    if bm:
        bm_lines = ["今日黑市商品:"]
        for item in bm:
            bm_lines.append(
                f"  - {item.get('name', '?')} ({item.get('rarity', '')}) "
                f"{item.get('price', 0)}鳞币, 库存{item.get('stock', 0)}件"
                f" — {item.get('desc', '')}"
            )
        user_parts.append("\n".join(bm_lines))
    else:
        user_parts.append("今日黑市: 休市中")

    # 排行榜
    if alive:
        top_growth = sorted(alive, key=lambda f: f["growth"], reverse=True)[:3]
        top_xp = sorted(alive, key=lambda f: f["experience"], reverse=True)[:3]
        user_parts.append(
            "成长榜 TOP3: " + ", ".join(
                f"{f['fish_name']}({f['growth']:.0f})" for f in top_growth
            )
        )
        user_parts.append(
            "经验榜 TOP3: " + ", ".join(
                f"{f['fish_name']}(Lv{f['level']} {f['experience']}XP)" for f in top_xp
            )
        )

    user_prompt = "\n".join(user_parts)

    # 调用 DeepSeek
    result = await call_deepseek_chat(
        system_prompt=FISH_DAILY_PROMPT,
        user_prompt=user_prompt,
        temperature=0.9,
        max_tokens=2000,
    )

    if result["success"]:
        report_text = result["data"]
        # 保存到 periodic_reports
        db.save_periodic_report(
            group_id=group_id,
            report_type="fish_daily",
            period_key=date_str,
            date_start=date_str,
            date_end=date_str,
            day_count=1,
            total_messages=0,
            active_members=len(alive),
            report_json=json.dumps({
                "text": report_text,
                "weather": weather,
                "black_market": bm,
                "parse_log": parse_log,
            }, ensure_ascii=False),
            model_used=result.get("model", config.DEEPSEEK_MODEL),
        )
        logger.info(f"鱼塘日报生成成功: group={group_id} date={date_str}")
        return {"success": True, "report": report_text,
                "model": result["model"], "duration_ms": result["duration_ms"]}
    else:
        logger.error(f"鱼塘日报生成失败: {result.get('error', 'unknown')}")
        return {"success": False, "error": result.get("error", "unknown"),
                "report": None}
