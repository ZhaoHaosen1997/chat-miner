"""
v1.5.0 Personas API — 跨群/跨平台身份关联
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.database import (
    create_persona, link_member_to_persona, unlink_member_from_persona,
    get_persona, get_persona_by_member, list_personas, delete_persona,
    auto_link_by_wxid, get_cross_group_members, get_cross_group_wxids,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/personas", tags=["personas"])


class CreatePersonaBody(BaseModel):
    name: str = ""
    member_ids: list[int] = []


class LinkMemberBody(BaseModel):
    member_id: int


class ManualLinkBody(BaseModel):
    """手动关联两个 member（创建或合并 persona）"""
    member_id_a: int
    member_id_b: int


# ---- Personas CRUD ----

@router.get("")
async def api_list_personas():
    """列出所有 persona"""
    personas = list_personas()
    return {"code": 200, "message": "ok", "data": personas}


@router.post("")
async def api_create_persona(body: CreatePersonaBody):
    """创建 persona 并关联初始成员"""
    persona_id = create_persona(body.name)
    for mid in body.member_ids:
        link_member_to_persona(persona_id, mid)
    persona = get_persona(persona_id)
    return {"code": 200, "message": "persona 创建成功", "data": persona}


@router.get("/{persona_id}")
async def api_get_persona(persona_id: int):
    """获取 persona 详情（含所有关联成员及画像）"""
    persona = get_persona(persona_id)
    if not persona:
        raise HTTPException(404, detail="Persona 不存在")
    return {"code": 200, "message": "ok", "data": persona}


@router.delete("/{persona_id}")
async def api_delete_persona(persona_id: int):
    """删除 persona"""
    if not delete_persona(persona_id):
        raise HTTPException(404, detail="Persona 不存在")
    return {"code": 200, "message": "persona 已删除", "data": None}


@router.post("/{persona_id}/members")
async def api_link_member(persona_id: int, body: LinkMemberBody):
    """将成员关联到 persona"""
    if not link_member_to_persona(persona_id, body.member_id):
        raise HTTPException(404, detail="成员不存在")
    persona = get_persona(persona_id)
    return {"code": 200, "message": "关联成功", "data": persona}


@router.delete("/{persona_id}/members/{member_id}")
async def api_unlink_member(persona_id: int, member_id: int):
    """从 persona 中移除成员"""
    if not unlink_member_from_persona(member_id):
        raise HTTPException(404, detail="关联不存在")
    return {"code": 200, "message": "已移除关联", "data": None}


# ---- Manual cross-platform linking ----

@router.post("/link")
async def api_manual_link(body: ManualLinkBody):
    """手动关联两个成员（用于跨平台微信↔QQ关联）

    如果任一成员已属于 persona，则将另一个也加入该 persona；
    如果两个都已属于不同 persona，则合并 persona；
    如果都不属于 persona，则创建新的 persona。
    """
    a_id = body.member_id_a
    b_id = body.member_id_b

    persona_a = get_persona_by_member(a_id)
    persona_b = get_persona_by_member(b_id)

    if persona_a and persona_b:
        if persona_a["id"] == persona_b["id"]:
            return {"code": 200, "message": "已在同一 persona 中", "data": persona_a}
        # 合并：将 persona_b 的成员全部移到 persona_a
        for m in persona_b["members"]:
            link_member_to_persona(persona_a["id"], m["id"])
        delete_persona(persona_b["id"])
        persona = get_persona(persona_a["id"])
        return {"code": 200, "message": "已合并两个 persona", "data": persona}

    target = persona_a or persona_b
    if target:
        link_member_to_persona(target["id"], a_id)
        link_member_to_persona(target["id"], b_id)
        persona = get_persona(target["id"])
        return {"code": 200, "message": "已加入已有 persona", "data": persona}

    # 都不属于 persona，新建
    persona_id = create_persona()
    link_member_to_persona(persona_id, a_id)
    link_member_to_persona(persona_id, b_id)
    persona = get_persona(persona_id)
    return {"code": 200, "message": "已创建新 persona 并关联", "data": persona}


# ---- Auto-link by wxid ----

@router.post("/auto-link")
async def api_auto_link():
    """自动关联：为同一 wxid 在不同群的成员创建 persona"""
    count = auto_link_by_wxid()
    return {
        "code": 200,
        "message": f"已创建 {count} 个 persona",
        "data": {"created": count},
    }


# ---- Cross-group queries ----

@router.get("/cross-group/wxids")
async def api_cross_group_wxids():
    """列出所有在多个群出现的 wxid"""
    wxids = get_cross_group_wxids()
    return {"code": 200, "message": "ok", "data": wxids}


@router.get("/cross-group/{wxid}")
async def api_cross_group_detail(wxid: str):
    """获取某 wxid 在所有群的画像（用于跨群对比）"""
    members = get_cross_group_members(wxid)
    if not members:
        raise HTTPException(404, detail="该 wxid 不存在或仅在单个群")
    # 检测是否已关联到 persona
    persona = None
    if members:
        persona = get_persona_by_member(members[0]["id"])
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "wxid": wxid,
            "members": members,
            "persona": persona,
        },
    }
