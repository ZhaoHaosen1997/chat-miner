"""
v1.5.0 Personas API — 跨群/跨平台身份关联
v1.5.2: 全面画像生成
"""
import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.database import (
    get_default_prompt,
    create_persona, link_member_to_persona, unlink_member_from_persona,
    get_persona, get_persona_by_member, list_personas, delete_persona,
    merge_personas,
    auto_link_by_wxid, get_cross_group_members, get_cross_group_wxids,
    save_comprehensive_portrait, get_model_config, get_default_model,
)
from services.task_manager import task_manager

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
        # v1.5.2: 原子合并，单事务防竞态
        merge_personas(persona_b["id"], persona_a["id"])
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


# ---- v1.5.2: 全面画像 ----

COMPREHENSIVE_PORTRAIT_SYSTEM = """你是一位跨群人格分析专家。同一个人在不同群里可能展现不同侧面，你的任务是综合所有群的表现，提炼出核心人格特质和群际差异。

分析原则：
1. 核心性格：跨群一致、稳定不变的底层人格特质（2-3句话）
2. 群际差异：在每个群中扮演的不同角色和表现差异，要具体到群名
3. 统一人设：用一句话（8-18字）概括这个人
4. 深度洞察：综合所有群的数据，给出有深度的分析

只输出 JSON，不要任何其他文字。"""


def _build_comprehensive_prompt(persona: dict) -> str:
    """构建全面画像的用户 prompt"""
    parts = []
    for i, m in enumerate(persona.get("members", []), 1):
        pj = None
        raw = m.get("portrait_json")
        if raw:
            try:
                pj = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                pass

        platform_label = "微信" if m.get("platform") == "wechat" else (
            "QQ" if m.get("platform") == "qq" else "未知平台"
        )
        parts.append(f"## 第{i}个身份：{platform_label}群「{m.get('group_name', '未知群')}」")
        parts.append(f"- 昵称：{m.get('display_name', '未知')}")
        parts.append(f"- 消息数：{m.get('message_count', 0)}")

        if pj:
            personality = pj.get("personality", [])
            if isinstance(personality, list):
                parts.append(f"- 性格标签：{' / '.join(personality[:5])}")
            elif personality:
                parts.append(f"- 性格：{personality}")
            parts.append(f"- 说话风格：{pj.get('speaking_style', '')}")
            parts.append(f"- 角色：{pj.get('role', '')}")
            interests = pj.get("interests", [])
            if isinstance(interests, list):
                parts.append(f"- 兴趣：{' / '.join(interests[:5])}")
            elif interests:
                parts.append(f"- 兴趣：{interests}")
            parts.append(f"- 口头禅：{pj.get('signature_phrase', '')}")
            parts.append(f"- 活跃时段：{pj.get('active_hours', '')}")
            parts.append(f"- 一句话人设：{pj.get('one_line', '')}")
            parts.append(f"- emoji标签：{pj.get('emoji_style', '')}")
            if pj.get("emotion_summary"):
                parts.append(f"- 情绪特征：{pj['emotion_summary']}")
            if pj.get("deep_insight"):
                parts.append(f"- 深度洞察：{pj['deep_insight']}")
        else:
            parts.append("- (该群暂无画像)")
        parts.append("")

    parts.append("""请综合以上所有身份，输出以下 JSON：
{
  "core_personality": "核心性格（跨群不变的特质，2-3句话）",
  "group_differences": [
    {"group": "群名", "role": "该群中扮演的角色", "difference": "该群中独特的表现"}
  ],
  "unified_oneline": "统一人设描述（8-18字）",
  "unified_emoji": "最能代表这个人的 emoji（1-2个）",
  "comprehensive_insight": "深度综合洞察（2-3句话）",
  "interest_overlap": "跨群共同兴趣",
  "social_style": "社交风格总结（1句话）"
}""")

    return "\n".join(parts)


class ComprehensiveBody(BaseModel):
    model_id: int | None = None


@router.post("/{persona_id}/comprehensive")
async def api_comprehensive_portrait(persona_id: int, body: ComprehensiveBody = ComprehensiveBody()):
    """v1.5.2: 生成全面画像 — 聚合 persona 下所有身份的画像，用在线模型综合分析"""
    persona = get_persona(persona_id)
    if not persona:
        raise HTTPException(404, detail="Persona 不存在")
    if len(persona.get("members", [])) < 2:
        raise HTTPException(400, detail="Persona 至少需要 2 个身份才能生成全面画像")

    # 检查是否有至少一个成员有画像
    has_portrait = any(m.get("portrait_json") for m in persona["members"])
    if not has_portrait:
        raise HTTPException(400, detail="关联的成员都还没有画像，请先生成各群的画像")

    task = task_manager.create("comprehensive_portrait", None, {"persona_id": persona_id})
    task.update("pending", f"生成 {persona.get('name') or 'Persona#' + str(persona_id)} 的全面画像...")

    asyncio.create_task(_run_comprehensive_portrait(persona, task, body.model_id))

    return {
        "code": 200,
        "message": "全面画像生成任务已创建",
        "data": {"task_id": task.task_id, "status": "pending"},
    }


async def _run_comprehensive_portrait(persona: dict, task, model_id: int | None = None):
    """后台：聚合 persona 下所有画像，调用在线模型生成全面画像"""
    try:
        # 1. 解析模型配置
        if model_id:
            model_config = get_model_config(model_id)
            if not model_config or model_config.get("model_type") != "online":
                model_config = get_default_model("online")
        else:
            model_config = get_default_model("online")

        if not model_config:
            task.finish(success=False, error={"type": "no_model", "detail": "未配置在线模型，请在设置中添加 DeepSeek API"})
            return

        persona_name = persona.get("name") or f"Persona#{persona.get('id')}"
        task.update("inference", f"正在综合分析 {persona_name} 的 {len(persona['members'])} 个身份...")

        # 2. 构建 prompt
        user_prompt = _build_comprehensive_prompt(persona)

        # 3. 调用在线模型
        from services.online_model import call_online_chat
        result = await call_online_chat(
            system_prompt=get_default_prompt("comprehensive") or COMPREHENSIVE_PORTRAIT_SYSTEM,
            user_prompt=user_prompt,
            model_config=model_config,
            temperature=0.7,
            json_mode=True,
            max_tokens=2048,
        )

        if not result.get("success"):
            error_msg = result.get("error", "未知错误")
            task.finish(success=False, error={"type": "ai_error", "detail": error_msg})
            return

        # 4. 解析 JSON 输出
        raw_text = result.get("data", "")
        try:
            portrait_data = json.loads(raw_text) if isinstance(raw_text, str) else raw_text
        except (json.JSONDecodeError, TypeError):
            # 尝试提取 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', str(raw_text))
            if match:
                try:
                    portrait_data = json.loads(match.group())
                except (json.JSONDecodeError, TypeError):
                    task.finish(success=False, error={"type": "parse_error", "detail": "模型返回格式异常"})
                    return
            else:
                task.finish(success=False, error={"type": "parse_error", "detail": "模型返回格式异常"})
                return

        task.add_step(
            "comprehensive_portrait", "done",
            model=result.get("model", ""),
            duration_ms=result.get("duration_ms", 0),
        )

        # 5. 保存
        save_comprehensive_portrait(persona["id"], json.dumps(portrait_data, ensure_ascii=False))
        task.update("done", f"{persona_name} 的全面画像已生成")
        task.finish(success=True)

    except Exception as e:
        logger.error(f"全面画像生成异常: {e}", exc_info=True)
        try:
            task.finish(success=False, error={"type": "internal_error", "detail": str(e)})
        except Exception:
            pass
