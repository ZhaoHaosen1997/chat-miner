"""
群鱼塘 API 路由
"""
import json
from fastapi import APIRouter, HTTPException, Path
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
def get_pond(group_id: int):
    """获取鱼塘全貌（含天气、所有鱼、排行榜、事件）"""
    state = fp.get_pond_state(group_id)
    return {"code": 200, "message": "ok", "data": state}


@router.post("/settle")
def settle_pond(group_id: int, body: SettleBody = SettleBody()):
    """触发全群结算"""
    result = fp.settle_all_fish(group_id, body.reference_date)
    return {"code": 200, "message": "结算完成", "data": result}


# ---- 单鱼操作 ----

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
    fish = db.get_fish(group_id, wxid)
    if not fish:
        raise HTTPException(404, "鱼不存在，请先 /领养")
    species_info = fp.get_species_info(fish["species"])
    proficiencies = fp.get_proficiencies(fish["species"])
    coins = db.get_coin_wallet(group_id, wxid)
    events = db.get_fish_events(group_id, wxid, 10)
    return {"code": 200, "message": "ok", "data": {
        "fish": fish, "species_info": species_info,
        "proficiencies": proficiencies, "coins": coins, "recent_events": events
    }}


@router.post("/fish/{wxid}/feed")
def feed_fish(group_id: int, wxid: str, body: FeedBody = FeedBody()):
    """/喂食"""
    result = fp.cmd_feed(group_id, wxid, body.from_wxid, body.premium_feed)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": result["check"].get("describe", "喂食完成"), "data": result}


@router.post("/fish/{wxid}/clean")
def clean_tank(group_id: int, wxid: str):
    """/换水"""
    result = fp.cmd_clean(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "换水完成", "data": result}


@router.post("/fish/{wxid}/touch")
def touch_fish(group_id: int, wxid: str):
    """/摸鱼"""
    result = fp.cmd_touch(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "摸鱼完成", "data": result}


@router.post("/fish/{wxid}/explore")
def explore(group_id: int, wxid: str):
    """/探索"""
    result = fp.cmd_explore(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "探索完成", "data": result}


@router.post("/fish/{wxid}/treasure")
def treasure(group_id: int, wxid: str):
    """/寻宝"""
    result = fp.cmd_treasure(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "寻宝完成", "data": result}


@router.post("/fish/{wxid}/showoff")
def showoff(group_id: int, wxid: str):
    """/晒鱼"""
    result = fp.cmd_showoff(group_id, wxid)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"code": 200, "message": "晒鱼完成", "data": result}


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


# ---- 历史指令解析 ----

@router.post("/parse-commands")
def parse_commands(group_id: int):
    """扫描聊天记录中的 / 指令并执行"""
    # 获取 ParsedChat 和消息
    try:
        from routers.groups import get_chat_cache
        chat = get_chat_cache(group_id)
    except Exception:
        raise HTTPException(400, "无法加载聊天数据，请先导入群")

    all_messages = chat.messages
    result = fp.parse_commands_from_messages(
        group_id, all_messages,
        get_name_by_wxid=chat.get_name_by_wxid
    )
    return {"code": 200, "message": f"解析完成，处理 {result['events_processed']} 条指令",
            "data": result}
