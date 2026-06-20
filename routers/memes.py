"""
群梗百科 API v1.18.3
"""
import json
import logging

from fastapi import APIRouter, HTTPException

from models.database import (
    get_group, get_group_memes, add_group_meme, update_group_meme, delete_group_meme,
)
from routers.groups import get_chat_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}/memes", tags=["群梗百科"])

_MEME_SCAN_SYSTEM = """你是一个群聊文化观察员。识别群友之间使用的**自有梗/黑话**——外部人看不懂、群内约定俗成的表达。不是全网通用的网络流行语（如"绝了""6"不算）。每个梗用一句话解释。没有明显梗就返回空数组。"""


@router.get("")
async def api_list_memes(group_id: int):
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")
    return {"code": 200, "message": "ok", "data": get_group_memes(group_id)}


@router.post("")
async def api_add_meme(group_id: int, body: dict):
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")
    term = (body.get("term") or "").strip()
    desc = (body.get("description") or "").strip()
    if not term or not desc:
        raise HTTPException(400, detail="term 和 description 不能为空")
    mid = add_group_meme(group_id, term, desc, "user")
    if mid is None:
        raise HTTPException(409, detail=f"梗 '{term}' 已存在")
    return {"code": 200, "message": "已添加", "data": {"id": mid}}


@router.put("/{meme_id}")
async def api_update_meme(group_id: int, meme_id: int, body: dict):
    desc = (body.get("description") or "").strip()
    if not desc:
        raise HTTPException(400, detail="description 不能为空")
    if not update_group_meme(meme_id, desc):
        raise HTTPException(404, detail="梗不存在")
    return {"code": 200, "message": "已更新", "data": None}


@router.delete("/{meme_id}")
async def api_delete_meme(group_id: int, meme_id: int):
    if not delete_group_meme(meme_id):
        raise HTTPException(404, detail="梗不存在")
    return {"code": 200, "message": "已删除", "data": None}


@router.post("/scan")
async def api_scan_memes(group_id: int):
    """AI 扫描群聊近期自有梗"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    recent = [m for m in chat.messages[-2000:] if (m.get("content") or "").strip()]
    if len(recent) < 20:
        return {"code": 200, "message": "消息不足", "data": {"memes": [], "new_count": 0}}

    # 去重 sender，限 300 条
    seen = set()
    sampled = []
    for m in recent:
        sid = str(m.get("senderID", ""))
        if sid not in seen:
            seen.add(sid)
            sampled.append(m)
        if len(sampled) >= 300:
            break

    from services.desensitize import filter_pii
    gname = group.get("display_name") or group.get("name", "")
    lines = [f'以下是群聊"{gname}"的近期消息。识别自有梗：']
    for m in sampled:
        c = filter_pii((m.get("content") or "").strip())
        if c:
            lines.append(f"[{m.get('senderID','?')}]: {c}")

    json_inst = """
严格按 JSON 返回（无 markdown）：
{"memes": [{"term": "梗文本", "description": "一句话解释"}]}
没有则返回 {"memes": []}"""

    from services.online_model import call_online_chat
    from services.model_config import get_effective_model
    online_cfg = get_effective_model("online")
    if not online_cfg.get("api_key"):
        raise HTTPException(400, detail="在线模型未配置，无法使用 AI 扫描")
    result = await call_online_chat(
        system_prompt=_MEME_SCAN_SYSTEM + "\n\n" + json_inst,
        user_prompt="\n".join(lines),
        model_config=online_cfg,
        temperature=0.6,
        json_mode=True,
        max_tokens=2048,
        timeout=60,
    )

    if not result.get("success"):
        raise HTTPException(500, detail=f"AI 扫描失败: {result.get('error')}")

    try:
        data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{[^{}]*"memes"\s*:\s*\[.*?\][^{}]*\}', result.get("data", ""), re.DOTALL)
        data = json.loads(m.group(0)) if m else {"memes": []}

    new_count = 0
    for item in data.get("memes", []):
        t = (item.get("term") or "").strip()
        d = (item.get("description") or "").strip()
        if t and d:
            if add_group_meme(group_id, t, d, "ai"):
                new_count += 1
                logger.info("AI 新梗: group=%d term=%r", group_id, t)

    return {"code": 200, "message": f"发现 {len(data.get('memes',[]))} 个，新增 {new_count} 个",
            "data": {"memes": data.get("memes", []), "new_count": new_count}}
