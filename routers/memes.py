"""
群梗百科 API v1.18.8
"""
import json
import logging

from fastapi import APIRouter, HTTPException, Query

from models.database import (
    get_group, get_group_memes, add_group_meme, update_group_meme,
    delete_group_meme, approve_group_meme, reject_group_meme,
)
from routers.groups import get_chat_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}/memes", tags=["群梗百科"])

_MEME_SCAN_SYSTEM = """你是一个群聊文化观察员。你的任务是发现群友之间可能存在的**自有梗/黑话**——
外部人看不懂、群内约定俗成的表达。不是全网通用的网络流行语（如"绝了""6"不算）。

⚠️ 重要指引：
- 你的目标是**尽可能发现潜在梗**，宁可多报待审也不要漏掉。群友会人工审核确认。
- 如果你**有把握**确定梗的含义 → description 用陈述句解释（如"敷衍对方时的反讽式附和"）
- 如果你**不确定**含义，但某个词/短语反复出现、用法特殊、或引起群友异常反应 → description 用疑问句（如"似乎是某种反讽表达？具体含义待群友确认"）
- 只有真的没有任何特殊用法时才返回空数组"""


@router.get("")
async def api_list_memes(group_id: int,
                         status: str = Query("", description="筛选状态：pending/approved/all，默认非rejected")):
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")
    memes = get_group_memes(group_id, status=status)
    return {"code": 200, "message": "ok", "data": memes}


@router.post("")
async def api_add_meme(group_id: int, body: dict):
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")
    term = (body.get("term") or "").strip()
    desc = (body.get("description") or "").strip()
    if not term or not desc:
        raise HTTPException(400, detail="term 和 description 不能为空")
    mid = add_group_meme(group_id, term, desc, "user", "approved")
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


@router.post("/{meme_id}/approve")
async def api_approve_meme(group_id: int, meme_id: int):
    """审核通过"""
    if not approve_group_meme(meme_id):
        raise HTTPException(404, detail="梗不存在")
    return {"code": 200, "message": "已审核通过", "data": None}


@router.post("/{meme_id}/reject")
async def api_reject_meme(group_id: int, meme_id: int):
    """驳回"""
    if not reject_group_meme(meme_id):
        raise HTTPException(404, detail="梗不存在")
    return {"code": 200, "message": "已驳回", "data": None}


@router.delete("/{meme_id}")
async def api_delete_meme(group_id: int, meme_id: int):
    if not delete_group_meme(meme_id):
        raise HTTPException(404, detail="梗不存在")
    return {"code": 200, "message": "已删除", "data": None}


@router.post("/scan")
async def api_scan_memes(group_id: int):
    """AI 扫描群聊近期自有梗（结果入库 status=pending，需人工审核）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    total_msgs = len(chat.messages)
    recent = [m for m in chat.messages[-2000:] if (m.get("content") or "").strip()]
    logger.info("梗扫描开始: group=%d 总消息=%d 近2000条有效=%d",
                group_id, total_msgs, len(recent))

    if len(recent) < 20:
        logger.info("梗扫描跳过: group=%d 有效消息不足20条", group_id)
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

    # v1.18.8: 获取已有梗，作为去重参考传入 AI
    existing = get_group_memes(group_id)
    approved_terms = [m["term"] for m in existing if m.get("status") == "approved"]
    pending_terms = [m["term"] for m in existing if m.get("status") == "pending"]
    existing_terms = approved_terms + pending_terms
    logger.info("梗扫描已有梗: group=%d approved=%d pending=%d",
                group_id, len(approved_terms), len(pending_terms))

    lines = [f'以下是群聊"{gname}"的近期消息。请仔细观察，发现其中可能的自有梗：']
    char_count = 0
    for m in sampled:
        c = filter_pii((m.get("content") or "").strip())
        if c:
            lines.append(f"[{m.get('senderID','?')}]: {c}")
            char_count += len(c)

    # 注入近期事件作为扫描线索
    event_count = 0
    try:
        from models.database import get_events
        recent_events = get_events(group_id)[-20:]
        if recent_events:
            lines.append("")
            lines.append("近期群内事件（供参考，可能有梗相关线索）：")
            for evt in recent_events[:10]:
                title = evt.get("title") or ""
                desc = (evt.get("description") or "")[:80]
                etype = evt.get("event_type") or ""
                if title:
                    lines.append(f"[事件·{etype}] {title}：{desc}")
                    event_count += 1
    except Exception as e:
        logger.warning("梗扫描事件线索失败: %s", e)

    # 已知梗提醒（放末尾，避免开局打压积极性）
    if existing_terms:
        lines.append("")
        lines.append(f"💡 以下梗已有记录，无需再报：{', '.join(existing_terms)}")

    logger.info("梗扫描采样: group=%d sender=%d 消息字符=%d 事件线索=%d",
                group_id, len(sampled), char_count, event_count)

    json_inst = """
严格按 JSON 返回（无 markdown）：
{"memes": [{"term": "梗文本", "description": "一句话解释"}]}
没有则返回 {"memes": []}"""

    from services.online_model import call_online_chat
    from services.model_config import get_effective_model
    online_cfg = get_effective_model("online")
    if not online_cfg.get("api_key"):
        raise HTTPException(400, detail="在线模型未配置，无法使用 AI 扫描")

    prompt = "\n".join(lines)
    logger.info("梗扫描调用AI: group=%d model=%s prompt_chars=%d",
                group_id, online_cfg.get("model_name", "?"), len(prompt))

    result = await call_online_chat(
        system_prompt=_MEME_SCAN_SYSTEM + "\n\n" + json_inst,
        user_prompt=prompt,
        model_config=online_cfg,
        temperature=0.6,
        json_mode=True,
        max_tokens=2048,
        timeout=60,
    )

    if not result.get("success"):
        logger.error("梗扫描AI失败: group=%d error=%s", group_id, result.get("error"))
        raise HTTPException(500, detail=f"AI 扫描失败: {result.get('error')}")

    raw_data = result.get("data", "")
    logger.info("梗扫描AI返回: group=%d chars=%d preview=%s",
                group_id, len(raw_data) if raw_data else 0,
                str(raw_data)[:200])

    try:
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{[^{}]*"memes"\s*:\s*\[.*?\][^{}]*\}', raw_data or "", re.DOTALL)
        data = json.loads(m.group(0)) if m else {"memes": []}
        logger.warning("梗扫描JSON解析回退: group=%d regex_match=%s", group_id, bool(m))

    memes_found = data.get("memes", [])
    logger.info("梗扫描识别结果: group=%d AI返回梗数=%d 明细=%s",
                group_id, len(memes_found),
                [(m.get("term", ""), (m.get("description", "") or "")[:40]) for m in memes_found])

    new_count = 0
    for item in memes_found:
        t = (item.get("term") or "").strip()
        d = (item.get("description") or "").strip()
        if t and d:
            if add_group_meme(group_id, t, d, "ai", "pending"):
                new_count += 1
                logger.info("AI新梗入库(pending): group=%d term=%r desc=%s", group_id, t, d[:60])

    logger.info("梗扫描完成: group=%d AI返回=%d 新增=%d",
                group_id, len(memes_found), new_count)

    return {"code": 200,
            "message": f"发现 {len(memes_found)} 个，新增 {new_count} 个（待审核）",
            "data": {"memes": memes_found, "new_count": new_count,
                     "ai_raw": str(raw_data)[:500] if raw_data else ""}}
