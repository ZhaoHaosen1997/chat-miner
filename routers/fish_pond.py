"""
群鱼塘 API 路由
"""
import json
import asyncio
import logging
from datetime import datetime
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
    """[已弃用] 触发全群结算 — 静默鱼塘开启后由定时事件自动结算，此接口保留兼容旧版"""
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


# ---- v1.16.2: 升级 + 决议 + 领养 + 热搜 ----


@router.get("/upgrades")
def get_upgrades_endpoint(group_id: int):
    """获取鱼塘升级状态（含未购买的升级项，level=0）"""
    purchased = {u["upgrade_key"]: u["level"] for u in db.get_upgrades(group_id)}
    result = []
    for key, defn in fp.UPGRADE_DEFS.items():
        level = purchased.get(key, 0)
        costs = defn.get("costs") or fp.UPGRADE_COSTS
        result.append({
            "key": key, "level": level,
            "name": defn["name"], "icon": defn["icon"], "desc": defn["desc"],
            "next_cost": costs[level] if level < 5 else 0,
        })
    return {"code": 200, "message": "ok", "data": result}


@router.post("/upgrade")
async def upgrade_endpoint(group_id: int, body: dict):
    """升级鱼塘设施"""
    result = await asyncio.to_thread(fp.upgrade_pond, group_id, body.get("upgrade_key", ""))
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": f"{result['name']}升级到 Lv{result['new_level']}", "data": result}


@router.post("/decree")
async def decree_endpoint(group_id: int, body: dict):
    """执行塘主决议"""
    result = await asyncio.to_thread(fp.execute_decree, group_id,
                                      body.get("decree", ""),
                                      body.get("target_wxid"))
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": f"{result['name']}执行完成", "data": result}


@router.get("/decree-limits")
def decree_limits(group_id: int):
    """查询当日决议剩余次数"""
    limits = {}
    for key, d in fp.DECREE_DEFS.items():
        used = db.count_today_decrees(group_id, key)
        limits[key] = {"name": d["name"], "used": used, "max": d.get("daily", 1)}
    return {"code": 200, "message": "ok", "data": limits}


@router.post("/batch-adopt")
async def batch_adopt_endpoint(group_id: int):
    """一键领养：为所有无鱼成员创建鱼"""
    results = await asyncio.to_thread(fp.batch_adopt, group_id)
    return {"code": 200, "message": f"领养 {len(results)} 条鱼", "data": results}


@router.get("/hot-search")
def hot_search_endpoint(group_id: int, days: int = 7):
    """鱼塘热搜榜"""
    data = fp.get_hot_search(group_id, days)
    return {"code": 200, "message": "ok", "data": data}


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
    """[已弃用] 扫描今日聊天记录中的 / 指令并执行 — 静默鱼塘开启后由定时事件自动处理，此接口保留兼容旧版和指令模拟器"""
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


# ==================== v1.16.4: 鱼际关系 API ====================

class RelationTarget(BaseModel):
    pass  # 预留，无请求体


@router.get("/fish/{wxid}/relationships")
async def get_fish_relationships(group_id: int, wxid: str):
    """获取某鱼的关系列表（朋友圈）"""
    try:
        rels = db.get_fish_relationships(group_id, wxid)
        return {"code": 200, "message": "ok", "data": {"wxid": wxid, "relationships": rels}}
    except Exception as e:
        logger.error(f"查询鱼际关系失败: {e}")
        raise HTTPException(500, f"查询失败: {e}")


# ==================== v1.16.4: 传奇鱼任务 API ====================

class LegendaryQuestBody(BaseModel):
    pass  # 无额外参数


@router.get("/fish/{wxid}/legendary-quest-status")
async def get_legendary_quest_status(group_id: int, wxid: str):
    """查询传奇试炼状态"""
    try:
        fish = db.get_fish(group_id, wxid)
        if not fish:
            raise HTTPException(404, "鱼不存在")
        step = fish.get("legendary_quest_step", 0)
        # 检查今日是否已挑战
        date_str = datetime.now().strftime("%Y-%m-%d")
        quest_date_key = f"legendary_quest_date_{group_id}_{wxid}"
        conn = db.get_conn()
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?", (quest_date_key,)
        ).fetchone()
        conn.close()
        today_attempted = (row and row["value"] == date_str)
        return {"code": 200, "message": "ok", "data": {
            "step": step,
            "step_names": ["未开始", "力量试炼(STR DC15)", "智慧试炼(WIS DC18)", "意志试炼(CHA DC20)", "已通关"],
            "today_attempted": today_attempted,
            "can_challenge": (step > 0 and step < 4 and not today_attempted
                              and fish.get("stage") == "传说" and fish.get("level", 0) >= 8
                              and fish.get("energy", 0) >= 50),
        }}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询传奇任务状态失败: {e}")
        raise HTTPException(500, f"查询失败: {e}")


@router.post("/fish/{wxid}/legendary-quest")
async def do_legendary_quest(group_id: int, wxid: str):
    """执行传奇试炼下一步"""
    from datetime import datetime as dt
    try:
        fish = db.get_fish(group_id, wxid)
        if not fish or not fish.get("is_alive"):
            raise HTTPException(400, "鱼不存在或已死亡")
        if fish.get("stage") != "传说" or fish.get("level", 0) < 8:
            raise HTTPException(400, "仅传说阶段且等级≥8的鱼可挑战传奇试炼")
        if fish.get("energy", 0) < 50:
            raise HTTPException(400, f"精力不足（需要50，当前{fish['energy']}）")

        step = fish.get("legendary_quest_step", 0)
        if step == 0:
            # 首次发起：设为第1步
            step = 1
            db.update_fish_field(group_id, wxid, "legendary_quest_step", 1)
        if step >= 4:
            raise HTTPException(400, "已通关传奇试炼，不可重复挑战")

        # 检查今日是否已尝试
        date_str = dt.now().strftime("%Y-%m-%d")
        quest_date_key = f"legendary_quest_date_{group_id}_{wxid}"
        conn = db.get_conn()
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key=?", (quest_date_key,)
        ).fetchone()
        if row and row["value"] == date_str:
            conn.close()
            raise HTTPException(400, "今日已挑战过，明天再来")
        conn.close()

        # 消耗精力
        db.update_fish_energy(group_id, wxid, 50)

        # 根据当前 step 执行检定
        from services.d20 import ability_check
        from services.passive_events import _has_proficiency
        import random as _random

        step_config = {
            1: ("strength", 15, "力量试炼"),
            2: ("wisdom", 18, "智慧试炼"),
            3: ("charisma", 20, "意志试炼"),
        }
        attr, dc, name = step_config[step]
        is_prof = _has_proficiency(fish, attr)
        check = ability_check(fish.get(attr, 10), dc=dc,
                              is_proficient=is_prof, level=fish.get("level", 1))

        # 记录今日挑战
        conn = db.get_conn()
        try:
            conn.execute(
                "INSERT INTO app_settings (key, value, value_type) VALUES (?, ?, 'string') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (quest_date_key, date_str)
            )
            conn.commit()
        finally:
            conn.close()

        if check.success:
            new_step = step + 1
            db.update_fish_field(group_id, wxid, "legendary_quest_step", new_step)
            db.add_fish_event(group_id, wxid, "legendary_quest", {
                "step": step, "step_name": name, "success": True,
                "dc": dc, "attr": attr, "new_step": new_step,
                "check": check.to_dict(),
            })
            if new_step == 4:
                # 通关！全塘广播
                db.add_fish_event(group_id, "", "flavor", {
                    "type": "legendary_complete",
                    "fish_name": fish["fish_name"],
                    "desc": f"{fish['fish_name']}通过传奇试炼！全塘鱼仰望！",
                })
                # 奖励：写入永久优势标记（存在 personality_traits 中）
                import json as _json
                traits_raw = fish.get("personality_traits", "[]")
                try:
                    traits = _json.loads(traits_raw) if isinstance(traits_raw, str) else traits_raw
                except (_json.JSONDecodeError, TypeError):
                    traits = []
                if "传奇" not in traits:
                    traits.append("传奇")
                    db.update_fish_field(group_id, wxid, "personality_traits",
                                        _json.dumps(traits, ensure_ascii=False))
                return {"code": 200,
                        "message": f"🎉 通关！{fish['fish_name']}完成全部传奇试炼！",
                        "data": {"step": 4, "success": True, "completed": True,
                                 "check": check.to_dict()}}
            return {"code": 200,
                    "message": f"✓ {name}通过！进入下一步",
                    "data": {"step": new_step, "success": True, "completed": False,
                             "check": check.to_dict()}}
        else:
            db.add_fish_event(group_id, wxid, "legendary_quest", {
                "step": step, "step_name": name, "success": False,
                "dc": dc, "attr": attr,
                "check": check.to_dict(),
            })
            return {"code": 200,
                    "message": f"✗ {name}失败，明天再试",
                    "data": {"step": step, "success": False, "completed": False,
                             "check": check.to_dict()}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"传奇试炼失败: {e}")
        raise HTTPException(500, f"传奇试炼出错: {e}")


# ==================== v1.16.4: 公告牌 API ====================

class BulletinBody(BaseModel):
    content: str


@router.get("/bulletin")
async def get_bulletin(group_id: int):
    """获取鱼塘公告牌"""
    try:
        from config import config as _cfg
        content = getattr(_cfg, "POND_BULLETIN_BOARD", "")
        return {"code": 200, "message": "ok", "data": {"content": content or ""}}
    except Exception as e:
        raise HTTPException(500, f"获取公告牌失败: {e}")


@router.post("/bulletin")
async def set_bulletin(group_id: int, body: BulletinBody):
    """设置鱼塘公告牌"""
    try:
        content = (body.content or "").strip()
        if len(content) > 200:
            raise HTTPException(400, "公告牌内容最多200字符")
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO app_settings (key, value, value_type) VALUES ('pond_bulletin_board', ?, 'string') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (content,)
        )
        conn.commit()
        conn.close()
        # 刷新 config
        from config import config as _cfg
        _cfg.POND_BULLETIN_BOARD = content
        return {"code": 200, "message": "公告牌已更新", "data": {"content": content}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"设置公告牌失败: {e}")


# ==================== v1.16.5: 调试 API（需作弊模式） ====================

def _require_cheat():
    """校验作弊模式是否开启，否则返回 403"""
    from config import config as _cfg
    if not getattr(_cfg, "POND_CHEAT_MODE", False):
        raise HTTPException(403, '调试功能仅在作弊模式下可用，请在设置中开启「允许作弊」')


class DebugCoinsBody(BaseModel):
    wxid: str
    amount: int  # 正=加币，负=扣币


@router.post("/debug/coins")
async def debug_coins(group_id: int, body: DebugCoinsBody):
    """加减鳞币"""
    _require_cheat()
    try:
        import random as _random
        amount = body.amount
        if amount > 0:
            db.earn_coins(group_id, body.wxid, amount, "debug", "被不明力量赠与了鳞币")
        else:
            wallet = db.get_coin_wallet(group_id, body.wxid)
            current = wallet.get("balance", 0) if wallet else 0
            deduct = min(current, -amount)
            if deduct > 0:
                db.earn_coins(group_id, body.wxid, -deduct, "debug", "被不明力量取走了鳞币")
        db.add_fish_event(group_id, body.wxid, "flavor", {
            "text": f"被不明力量{'赠与' if amount > 0 else '取走'}了 {abs(amount)} 鳞币"
        })
        return {"code": 200, "message": f"鳞币{'增加' if amount > 0 else '减少'} {abs(amount)}"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"操作失败: {e}")


class DebugEventBody(BaseModel):
    event_group: str  # danger / lucky / welfare / rare / flavor


@router.post("/debug/trigger-event")
async def debug_trigger_event(group_id: int, body: DebugEventBody):
    """强制触发指定分组的被动事件"""
    _require_cheat()
    try:
        from services.passive_events import (
            trigger_passive_events, get_merged_flavor_events,
            DANGER_EVENTS, LUCKY_EVENTS, WELFARE_EVENTS,
            RARE_EVENTS, CHALLENGE_EVENTS,
        )
        import random as _random
        group = body.event_group
        db.add_fish_event(group_id, "", "flavor", {
            "text": "一股不明力量搅动了鱼塘..."
        })
        if group == "flavor":
            flavors = get_merged_flavor_events()
            text = _random.choice(flavors) if flavors else "不明力量拂过水面..."
            db.add_fish_event(group_id, "", "flavor", {"text": text})
        else:
            # 从指定分组随机选一个事件执行
            evt_pool = {"danger": DANGER_EVENTS, "lucky": LUCKY_EVENTS,
                        "welfare": WELFARE_EVENTS, "rare": RARE_EVENTS,
                        "challenge": CHALLENGE_EVENTS}.get(group)
            if not evt_pool:
                raise HTTPException(400, f"未知事件分组: {group}")
            alive = db.get_alive_fish(group_id)
            if not alive:
                raise HTTPException(400, "鱼塘没有活鱼")
            from services.passive_events import _execute_single_event, _execute_rare_event
            evt = _random.choice(evt_pool)
            if group == "rare":
                _execute_rare_event(group_id, evt[0], evt[1], evt[2], alive)
            else:
                target = _random.choice(alive)
                _execute_single_event(group_id, evt, target)
        return {"code": 200, "message": f"已触发 {group} 事件"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"触发失败: {e}")


class DebugWeatherBody(BaseModel):
    weather_type: str  # sunny/rain/storm/rainbow/double_rainbow/sandstorm/meteor


@router.post("/debug/weather")
async def debug_set_weather(group_id: int, body: DebugWeatherBody):
    """覆盖当日天气"""
    _require_cheat()
    try:
        valid = {"sunny","rain","storm","rainbow","double_rainbow","sandstorm","meteor"}
        if body.weather_type not in valid:
            raise HTTPException(400, f"无效天气类型，可选: {', '.join(sorted(valid))}")
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO app_settings (key, value, value_type) VALUES ('pond_cheat_weather_override', ?, 'string') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (body.weather_type,)
        )
        conn.commit()
        conn.close()
        from config import config as _cfg
        _cfg.POND_CHEAT_WEATHER_OVERRIDE = body.weather_type
        db.add_fish_event(group_id, "", "flavor", {
            "text": f"天空异变...天气被不明力量改变为{body.weather_type}"
        })
        return {"code": 200, "message": f"天气已覆盖为 {body.weather_type}"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"设置失败: {e}")


class DebugKillBody(BaseModel):
    wxid: str


@router.post("/debug/kill")
async def debug_kill_fish(group_id: int, body: DebugKillBody):
    """秒杀鱼"""
    _require_cheat()
    try:
        fish = db.get_fish(group_id, body.wxid)
        if not fish or not fish.get("is_alive"):
            raise HTTPException(400, "鱼不存在或已死亡")
        db.update_fish_field(group_id, body.wxid, "hp", 0)
        db.mark_fish_dead(group_id, body.wxid)
        import random as _random
        from services.passive_events import get_merged_last_words
        last_words = _random.choice(get_merged_last_words())
        db.add_fish_event(group_id, body.wxid, "flavor", {
            "text": f"被不明力量秒杀了", "last_words": last_words
        })
        return {"code": 200, "message": f"{fish['fish_name']} 已被秒杀", "data": {"last_words": last_words}}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"操作失败: {e}")


class DebugReviveBody(BaseModel):
    wxid: str


@router.post("/debug/revive")
async def debug_revive_fish(group_id: int, body: DebugReviveBody):
    """复活鱼"""
    _require_cheat()
    try:
        fish = db.get_fish(group_id, body.wxid)
        if not fish:
            raise HTTPException(400, "鱼不存在")
        if fish.get("is_alive"):
            raise HTTPException(400, "鱼还活着，无需复活")
        # 复活
        conn = db.get_conn()
        conn.execute("UPDATE fish_pond SET is_alive=1, hp=1 WHERE group_id=? AND wxid=?",
                     (group_id, body.wxid))
        max_energy = fish.get("max_energy", 100)
        conn.execute("UPDATE fish_pond SET energy=? WHERE group_id=? AND wxid=?",
                     (max_energy, group_id, body.wxid))
        conn.commit()
        conn.close()
        db.add_fish_event(group_id, body.wxid, "flavor", {
            "text": "被不明力量复活了"
        })
        return {"code": 200, "message": f"{fish['fish_name']} 已复活"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"操作失败: {e}")
