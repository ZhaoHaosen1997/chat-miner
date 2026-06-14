"""
群鱼塘 API 路由
"""
import json
import asyncio
import logging
from fastapi import APIRouter, HTTPException, Path

logger = logging.getLogger(__name__)
from pydantic import BaseModel

from services import fish_pond as fp
from models import database as db

router = APIRouter(prefix="/api/groups/{group_id}/fishpond", tags=["鱼塘"])


# ---- 请求模型 ----
class FeedBody(BaseModel):
    from_wxid: str = None
    premium_feed: bool = False

class BattleBody(BaseModel):
    target_wxid: str

class RenameBody(BaseModel):
    name: str
    use_tag: bool = False

class SpendBody(BaseModel):
    item: str
    amount: int = 0

class SettleBody(BaseModel):
    reference_date: str = None

class AdoptBody(BaseModel):
    display_name: str = ""
    message_count: int = 0


# ---- 鱼塘总览 ----

@router.get("")
@router.get("/")
async def get_pond(group_id: int):
    """获取鱼塘全貌（含天气、所有鱼、排行榜、事件）"""
    state = await asyncio.to_thread(fp.get_pond_state, group_id)
    return {"code": 200, "message": "ok", "data": state}


@router.post("/settle")
async def settle_pond(group_id: int, body: SettleBody = SettleBody()):
    """触发全群结算"""
    result = await asyncio.to_thread(fp.settle_all_fish, group_id, body.reference_date)
    return {"code": 200, "message": "结算完成", "data": result}


# ---- v1.16.1: 被动事件 + 金库 ----


@router.get("/pond-log")
def get_pond_log(group_id: int, limit: int = 30):
    """获取鱼塘事件日志（含被动事件和风味文本）"""
    events = db.get_fish_events(group_id, limit=limit)
    # 按时间正序（最近在最后）
    events.reverse()
    return {"code": 200, "message": "ok", "data": events}


@router.post("/trigger-event")
async def trigger_pond_event(group_id: int):
    """手动触发一次被动事件（测试用/塘主特权）"""
    from services.passive_events import trigger_passive_events
    results = await asyncio.to_thread(trigger_passive_events, group_id)
    return {"code": 200, "message": f"触发 {len(results)} 个事件", "data": results}


@router.get("/treasury")
def get_treasury_endpoint(group_id: int):
    """查看金库余额 + 近期流水"""
    treasury = db.get_treasury(group_id)
    log_entries = db.get_treasury_log(group_id, 20)
    return {"code": 200, "message": "ok", "data": {
        "treasury": treasury, "log": log_entries,
    }}


# ---- 鱼塘日报 ----

@router.post("/generate-report")
async def generate_fish_report(group_id: int, date: str = ""):
    """生成鱼塘日报 (DeepSeek)"""
    from datetime import datetime as dt
    from services import fish_report
    if not date:
        date = dt.now().strftime("%Y-%m-%d")

    try:
        from routers.groups import get_chat_cache
        chat = get_chat_cache(group_id)
    except Exception as e:
        logger.error("加载聊天缓存失败 (group=%d): %s", group_id, e, exc_info=True)
        raise HTTPException(400, "无法加载聊天数据")

    # 拿当日消息解析
    day_msgs = [m for m in chat.messages
                if (m.get("formattedTime") or "").startswith(date)]
    day_msgs.sort(key=lambda m: m.get("createTime", 0))
    parse_result = fp.parse_commands_from_messages(
        group_id, day_msgs,
        get_name_by_wxid=chat.get_name_by_wxid
    )
    settle_result = fp.settle_all_fish(group_id, date)
    parse_log = parse_result.get("processed", [])

    result = await fish_report.generate_fish_daily_report(
        group_id, date, parse_log, settle_result
    )
    if not result["success"]:
        raise HTTPException(500, result.get("error", "生成失败"))
    return {"code": 200, "message": "日报生成完成", "data": result}


@router.get("/report/{date}")
def get_fish_report(group_id: int, date: str):
    """获取某天鱼塘日报"""
    from models.database import get_periodic_report
    r = get_periodic_report(group_id, "fish_daily", date)
    if not r:
        raise HTTPException(404, "该日无鱼塘日报")
    import json
    try:
        r["report_json"] = json.loads(r["report_json"])
    except (json.JSONDecodeError, TypeError):
        r["report_json"] = {}
        logger.warning("鱼塘日报 report_json 解析失败 (date=%s)", date)
    return {"code": 200, "message": "ok", "data": r}


@router.get("/reports")
def list_fish_reports(group_id: int):
    """列出所有鱼塘日报"""
    from models.database import list_periodic_reports
    reports = list_periodic_reports(group_id, "fish_daily")
    return {"code": 200, "message": "ok", "data": reports}


@router.post("/resettle")
def resettle_pond(group_id: int, date: str = ""):
    """重新结算指定日期：只处理该天未结算的指令 + 天结算"""
    from datetime import datetime as dt
    if not date:
        date = dt.now().strftime("%Y-%m-%d")
    try:
        from routers.groups import get_chat_cache
        chat = get_chat_cache(group_id)
    except Exception:
        raise HTTPException(400, "无法加载聊天数据，请先导入群")

    # 只取指定日期的消息
    day_msgs = [m for m in chat.messages
                if (m.get("formattedTime") or "").startswith(date)]
    day_msgs.sort(key=lambda m: m.get("createTime", 0))

    result = fp.resettle_day(group_id, date, day_msgs,
                             get_name_by_wxid=chat.get_name_by_wxid)
    return {"code": 200, "message": f"{date} 结算完成", "data": result}


# ---- 单鱼操作 ----

@router.post("/fish/{wxid}/delete")
def delete_fish(group_id: int, wxid: str):
    """删除鱼（硬删除，用于测试清理）"""
    fish = db.get_fish(group_id, wxid)
    if not fish:
        raise HTTPException(404, "鱼不存在")
    conn = db.get_conn()
    conn.execute("DELETE FROM fish_events WHERE group_id=? AND wxid=?", (group_id, wxid))
    conn.execute("DELETE FROM fish_inventory WHERE group_id=? AND wxid=?", (group_id, wxid))
    conn.execute("DELETE FROM fish_pond WHERE group_id=? AND wxid=?", (group_id, wxid))
    conn.commit()
    conn.close()
    return {"code": 200, "message": f"已删除 {fish.get('fish_name', wxid)}", "data": None}


@router.post("/fish/{wxid}/adopt")
def adopt_fish(group_id: int, wxid: str, body: AdoptBody = AdoptBody()):
    """/领养：创建鱼"""
    result = fp.cmd_adopt(group_id, wxid, body.display_name or wxid,
                         message_count=body.message_count)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "领养成功", "data": result}


@router.get("/fish/{wxid}")
def get_fish_detail(group_id: int, wxid: str):
    """鱼详情"""
    fish = fp.get_fish_with_equip(group_id, wxid)
    if not fish:
        raise HTTPException(404, "鱼不存在，请先 /领养")
    species_info = fp.get_species_info(fish["species"])
    proficiencies = fp.get_proficiencies(fish["species"])
    coins = db.get_coin_wallet(group_id, wxid)
    events = db.get_fish_events(group_id, wxid, 10)
    bonuses = fp.get_equip_bonus(group_id, wxid)
    equipped = fish.get("equipped_item", "")
    equipped_info = None
    if equipped:
        ei = fp.ITEMS.get(equipped, {})
        equipped_info = {"key": equipped, "name": ei.get("name", ""), "desc": ei.get("desc", ""),
                         "bonus": ei.get("bonus", 0), "stat": ei.get("stat", "")}
    # v1.16.0: 解析性格和精力
    import json as _json
    traits_raw = fish.get("personality_traits", "[]")
    try:
        traits = _json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
    except (_json.JSONDecodeError, TypeError):
        traits = []
    traits_detail = [{"key": t, **fp.FISH_TRAITS.get(t, {"desc": "", "icon": ""})} for t in traits]

    return {"code": 200, "message": "ok", "data": {
        "fish": fish, "species_info": species_info,
        "proficiencies": proficiencies, "coins": coins, "recent_events": events,
        "equip_bonuses": bonuses, "equipped": equipped_info,
        "personality_traits": traits_detail,
        "energy": fish.get("energy", 100),
        "max_energy": fish.get("max_energy", 100),
        "emoji_variant": fish.get("emoji_variant", ""),
    }}


@router.post("/fish/{wxid}/feed")
def feed_fish(group_id: int, wxid: str, body: FeedBody = FeedBody()):
    """/喂食"""
    result = fp.cmd_feed(group_id, wxid, body.from_wxid, body.premium_feed)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": result["check"].get("describe", "喂食完成"), "data": result}


@router.post("/fish/{wxid}/touch")
def touch_fish(group_id: int, wxid: str):
    """/摸鱼"""
    result = fp.cmd_touch(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "摸鱼完成", "data": result}


@router.post("/fish/{wxid}/rest")
def rest_fish(group_id: int, wxid: str):
    """v1.16.0: /休息 — 立即恢复全部精力"""
    import asyncio
    fish = db.get_fish(group_id, wxid)
    if not fish or not fish["is_alive"]:
        raise HTTPException(400, "鱼不存在或已死亡")
    energy = fish.get("energy", 100)
    max_energy = fish.get("max_energy", 100)
    if energy >= max_energy:
        return {"code": 200, "message": "精力已满", "data": {"energy": energy, "max_energy": max_energy, "restored": 0}}
    restore_amount = max_energy - energy
    fp.regen_energy(group_id, wxid, restore_amount)
    fish = db.get_fish(group_id, wxid)
    return {"code": 200, "message": f"恢复了 {restore_amount} 点精力",
            "data": {"energy": fish.get("energy", max_energy), "max_energy": max_energy, "restored": restore_amount}}


@router.post("/fish/{wxid}/explore")
def explore(group_id: int, wxid: str):
    """/探索"""
    result = fp.cmd_explore(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "探索完成", "data": result}


@router.post("/fish/{wxid}/showoff")
def showoff(group_id: int, wxid: str):
    """/晒鱼"""
    result = fp.cmd_showoff(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "晒鱼完成", "data": result}


class TrainBody(BaseModel):
    attr_name: str

class ItemBody(BaseModel):
    action: str = "库存"
    item_key: str = ""
    qty: int = 1

class SimLogBody(BaseModel):
    wxid: str
    command: str
    display_name: str = ""
    d20: dict = None
    growth: float = 0
    coin_amount: int = 0
    happiness: int = 0
    evolved: bool = False
    fish_info: dict = None
    battle_winner: str = ""
    error: str = ""


class BuyBody(BaseModel):
    item_key: str

class GiftBody(BaseModel):
    target_name: str
    item_key: str


@router.get("/black-market")
def get_black_market(group_id: int, date: str = ""):
    """查看黑市"""
    from datetime import datetime as dt
    if not date:
        date = dt.now().strftime("%Y-%m-%d")
    items = fp.get_black_market_items(group_id, date)
    return {"code": 200, "message": "ok", "data": {"date": date, "items": items}}


@router.post("/log-sim-command")
def log_sim_command(group_id: int, body: SimLogBody):
    """记录模拟器发出的指令到 fish_events，供日志和日报使用"""
    from datetime import datetime as dt
    import json
    db.add_fish_event(group_id, body.wxid, "sim_command", {
        "command": body.command,
        "display_name": body.display_name,
        "d20": body.d20,
        "growth": body.growth,
        "coin_amount": body.coin_amount,
        "happiness": body.happiness,
        "evolved": body.evolved,
        "fish_info": body.fish_info,
        "battle_winner": body.battle_winner,
        "error": body.error,
        "time": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return {"code": 200, "message": "logged"}


@router.post("/fish/{wxid}/buy")
def buy_item(group_id: int, wxid: str, body: BuyBody):
    """/购买 <商品名>"""
    result = fp.cmd_buy(group_id, wxid, body.item_key)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": f"购买成功", "data": result}


@router.post("/fish/{wxid}/gift")
def gift_item(group_id: int, wxid: str, body: GiftBody):
    """/赠予 @XX <道具名>"""
    result = fp.cmd_gift(group_id, wxid, body.target_name, body.item_key)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": f"赠予成功", "data": result}


@router.post("/fish/{wxid}/items")
def fish_items(group_id: int, wxid: str, body: ItemBody = ItemBody()):
    """/道具 [操作] [道具名]"""
    result = fp.cmd_item(group_id, wxid, body.action, body.item_key, body.qty)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "ok", "data": result}


@router.post("/fish/{wxid}/train")
def train_fish(group_id: int, wxid: str, body: TrainBody):
    """/训练 <属性>"""
    result = fp.cmd_train(group_id, wxid, body.attr_name)
    if "error" in result:
        raise HTTPException(400, result["error"])
    msg = f"训练{body.attr_name}{'成功' if result.get('increased') else '失败'}"
    return {"code": 200, "message": msg, "data": result}


@router.post("/fish/{wxid}/rename")
def rename_fish(group_id: int, wxid: str, body: RenameBody):
    """/改名"""
    result = fp.cmd_rename(group_id, wxid, body.name, body.use_tag)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "改名成功", "data": result}


@router.post("/fish/{wxid}/battle")
def battle_fish(group_id: int, wxid: str, body: BattleBody):
    """/斗鱼"""
    result = fp.cmd_battle(group_id, wxid, body.target_wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": f"斗鱼结束，胜者: {result['winner']}", "data": result}


# ---- 排行榜 ----

@router.get("/leaderboard")
def leaderboard(group_id: int, sort: str = "growth"):
    """排行榜"""
    fish_list = db.get_alive_fish(group_id)
    if sort in ("growth", "happiness", "experience"):
        fish_list.sort(key=lambda x: x.get(sort, 0), reverse=True)
    elif sort in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"):
        fish_list.sort(key=lambda x: x.get(sort, 0), reverse=True)
    # 附加品种信息
    for f in fish_list[:20]:
        f["species_info"] = fp.get_species_info(f.get("species", ""))
    return {"code": 200, "message": "ok", "data": fish_list[:20]}


# ---- 鳞币 ----

@router.get("/fish/{wxid}/coins")
def coin_info(group_id: int, wxid: str):
    """鳞币余额 + 流水"""
    wallet = db.get_coin_wallet(group_id, wxid)
    transactions = db.get_coin_transactions(group_id, wxid, 20)
    return {"code": 200, "message": "ok", "data": {
        "wallet": wallet, "transactions": transactions
    }}


@router.post("/fish/{wxid}/coins/spend")
def spend_coins(group_id: int, wxid: str, body: SpendBody):
    """消费鳞币"""
    item_name = fp.SHOP_ITEMS.get(body.item, {}).get("name", body.item)
    price = body.amount or fp.SHOP_ITEMS.get(body.item, {}).get("price", 0)
    if not price:
        raise HTTPException(400, "未知商品或金额")

    wallet = db.spend_coins(group_id, wxid, price, "purchase",
                           f"购买 {item_name}")
    if wallet is None:
        raise HTTPException(400, "鳞币不足")
    return {"code": 200, "message": f"购买 {item_name} 成功", "data": wallet}


@router.get("/shop")
def shop_items():
    """商店物品列表"""
    return {"code": 200, "message": "ok", "data": fp.SHOP_ITEMS}


# ---- 事件 ----

@router.get("/events")
def fish_events(group_id: int, wxid: str = "", limit: int = 20):
    """事件列表"""
    events = db.get_fish_events(group_id, wxid, limit)
    return {"code": 200, "message": "ok", "data": events}


# ---- 今日指令解析 + 结算 ----

@router.post("/parse-commands")
def parse_commands(group_id: int):
    """扫描今日聊天记录中的 / 指令并执行，然后自动结算"""
    from datetime import datetime as dt
    try:
        from routers.groups import get_chat_cache
        chat = get_chat_cache(group_id)
    except Exception:
        raise HTTPException(400, "无法加载聊天数据，请先导入群")

    # 只取今日消息
    today = dt.now().strftime("%Y-%m-%d")
    today_msgs = [m for m in chat.messages
                  if (m.get("formattedTime") or "").startswith(today)]

    # 按时间排序
    today_msgs.sort(key=lambda m: m.get("createTime", 0))

    # 解析指令（聊天记录中的 / 指令）
    parse_result = fp.parse_commands_from_messages(
        group_id, today_msgs,
        get_name_by_wxid=chat.get_name_by_wxid
    )

    # 自动结算
    settle_result = fp.settle_all_fish(group_id, today)

    # 捞取今日所有指令事件（sim_command + 各 cmd 直接调用产生的 fish_events）
    import json
    cmd_event_types = ("feed", "touch", "explore", "showoff", "battle", "train",
                       "born", "rename", "buy", "gift", "sim_command", "evolve",
                       "level_up", "market_buy")
    conn = db.get_conn()
    placeholders = ",".join("?" * len(cmd_event_types))
    event_rows = conn.execute(
        f"""SELECT * FROM fish_events WHERE group_id=? AND event_type IN ({placeholders})
           AND date(created_at)=? ORDER BY created_at""",
        (group_id, *cmd_event_types, today)
    ).fetchall()
    conn.close()

    today_events = []
    for evt in event_rows:
        evt = dict(evt)
        try:
            ed = json.loads(evt["event_data"]) if isinstance(evt["event_data"], str) else evt["event_data"]
        except Exception as e:
            logger.debug("事件数据 JSON 解析失败: %s", e)
            ed = {}
        # 从 event_data 还原指令信息
        cmd_text = ed.get("command", "")
        if not cmd_text:
            # 无 sim_command 标记时，从 event_type 反推
            cmd_text = {
                "feed": "/喂食", "touch": "/摸鱼", "explore": "/探索",
                "showoff": "/晒鱼", "battle": "/斗鱼", "train": "/训练",
                "born": "/领养", "rename": "/改名", "buy": "/购买", "gift": "/赠予",
                "evolve": "进化!", "level_up": "升级!", "market_buy": "/购买",
            }.get(evt["event_type"], f"/{evt['event_type']}")

        entry = {
            "time": ed.get("time", (evt.get("created_at") or "")[11:19]),
            "sender": ed.get("display_name", evt["wxid"]),
            "wxid": evt["wxid"],
            "command": cmd_text,
            "type": evt["event_type"],
        }
        # D20 结果
        if "check" in ed:
            c = ed["check"]
            entry["d20"] = {"roll": c.get("roll"), "modifier": c.get("modifier"),
                           "total": c.get("total"), "dc": c.get("dc"),
                           "success": c.get("success"),
                           "critical_hit": c.get("critical_hit"),
                           "critical_miss": c.get("critical_miss")}
        elif "d20" in ed and ed["d20"]:
            entry["d20"] = ed["d20"]
        if ed.get("growth") or ed.get("growth_bonus"):
            entry["growth"] = ed.get("growth") or ed.get("growth_bonus", 0)
        if ed.get("happiness") or ed.get("happiness_bonus"):
            entry["happiness"] = ed.get("happiness") or ed.get("happiness_bonus", 0)
        if ed.get("coin_amount"):
            entry["coin_amount"] = ed["coin_amount"]
        if ed.get("evolved"):
            entry["evolved"] = True
        if ed.get("fish_info"):
            entry["fish"] = ed["fish_info"]
        if ed.get("battle_winner"):
            entry["battle_winner"] = ed["battle_winner"]
        if ed.get("error"):
            entry["error"] = ed["error"]
        today_events.append(entry)

    # 构建详细日志（优先 fish_events，因为它们是已经执行过的）
    log_entries = []
    seen_keys = set()

    # 先加入 fish_events 中的指令（已执行的真实记录）
    for e in today_events:
        key = (e["wxid"], e["command"], e.get("time", ""))
        seen_keys.add(key)
        log_entries.append(e)

    # 再补入聊天消息中解析的新指令（去重）
    for p in parse_result.get("processed", []):
        entry = {
            "time": p.get("time", ""),
            "sender": p.get("display_name", ""),
            "wxid": p.get("wxid", ""),
            "command": p.get("content", ""),
            "type": p.get("type", ""),
        }
        r = p.get("result", {})
        if "check" in r:
            c = r["check"]
            entry["d20"] = {
                "roll": c.get("roll"), "modifier": c.get("modifier"),
                "total": c.get("total"), "dc": c.get("dc"),
                "success": c.get("success"),
                "critical_hit": c.get("critical_hit"),
                "critical_miss": c.get("critical_miss"),
            }
        if r.get("growth_bonus"):
            entry["growth"] = r["growth_bonus"]
        if r.get("happiness_bonus"):
            entry["happiness"] = r["happiness_bonus"]
        if r.get("coin_amount"):
            entry["coin_amount"] = r["coin_amount"]
        if r.get("evolved"):
            entry["evolved"] = True
        if r.get("new_stage"):
            entry["new_stage"] = r["new_stage"]
        if "fish" in r:
            entry["fish"] = {
                "name": r["fish"].get("fish_name"),
                "species": r["fish"].get("species"),
                "rarity": r["fish"].get("rarity"),
            }
        if "error" in r:
            entry["error"] = r["error"]
        if r.get("winner"):
            entry["battle_winner"] = r["winner"]
        # 去重
        key = (entry["wxid"], entry["command"], entry.get("time", ""))
        if key not in seen_keys:
            seen_keys.add(key)
            log_entries.append(entry)

    # 错误
    for e in parse_result.get("errors", []):
        log_entries.append({
            "time": "", "sender": "", "command": e.get("msg", ""),
            "error": e.get("error", ""), "type": "error"
        })

    # 按时间排序
    log_entries.sort(key=lambda e: e.get("time", ""))

    return {"code": 200,
            "message": f"今日解析 {parse_result['events_processed']} 条指令，结算完成",
            "data": {
                "today": today,
                "commands_found": parse_result["commands_found"],
                "events_processed": parse_result["events_processed"],
                "log": log_entries,
                "settle": {
                    "weather": settle_result.get("weather"),
                    "fish_count": settle_result.get("fish_count"),
                    "black_market": settle_result.get("black_market", []),
                },
                "report_url": f"/#/fish-report/{today}",
            }}
