"""
群友画像 API：获取、刷新画像
v0.3.3: 刷新改为异步任务 + SSE 进度推送
"""
import json
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from config import config
from models.database import (
    get_group, get_portraits, get_portrait, log_analysis,
    get_member, get_members,
    get_portrait_versions, get_latest_portrait_version,
    save_member_portrait, save_portrait_version,
)
from services.portrait import generate_single_portrait, refresh_portraits
from services.task_manager import task_manager
from routers.groups import get_chat_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups/{group_id}", tags=["群友画像"])


@router.get("/portraits")
async def api_get_portraits(group_id: int):
    """获取群所有成员的画像"""
    from models.database import get_portraits as db_get_portraits
    portraits = db_get_portraits(group_id)

    from models.database import get_member_awards_batch

    # 批量获取所有成员的奖项（避免 N+1 查询）
    member_ids = [p["member_id"] for p in portraits]
    awards_map = get_member_awards_batch(group_id, member_ids) if member_ids else {}

    result = []
    for p in portraits:
        try:
            pj = json.loads(p["portrait_json"])
        except (json.JSONDecodeError, TypeError):
            pj = {}

        # 合并成员信息
        member = get_member(group_id, p["member_id"])

        # 获取该成员奖项（最多返回最近3个）
        awards = awards_map.get(p["member_id"], [])
        award_summary = None
        if awards:
            award_summary = {
                "count": len(awards),
                "latest": [{"name": a["award_name"], "emoji": a.get("award_emoji", "🏆"),
                            "year": a["year"]} for a in awards[:3]]
            }

        result.append({
            "member_id": p["member_id"],
            "display_name": p["display_name"],
            "avatar": member["avatar"] if member else "",
            "total_messages": p["total_analyzed_messages"],
            "portrait": pj,
            "awards": award_summary,
            "data_start_date": p.get("data_start_date") or "",
            "data_end_date": p.get("data_end_date") or "",
            "last_updated": p["last_updated"],
        })

    return {"code": 200, "message": "获取成功", "data": result}


@router.get("/portrait/{member_id}")
async def api_get_single_portrait(group_id: int, member_id: int):
    """获取单个成员的画像"""
    portrait = get_portrait(group_id, member_id)
    if not portrait:
        raise HTTPException(404, detail="该成员尚无画像，请先分析几天数据")

    try:
        pj = json.loads(portrait["portrait_json"])
    except (json.JSONDecodeError, TypeError):
        pj = {}

    member = get_member(group_id, member_id)

    # 获取该成员历年奖项
    from models.database import get_member_awards as db_get_member_awards
    awards = db_get_member_awards(group_id, member_id)

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "member_id": member_id,
            "display_name": portrait["display_name"],
            "avatar": member["avatar"] if member else "",
            "total_messages": portrait["total_analyzed_messages"],
            "portrait": pj,
            "awards": [{"name": a["award_name"], "emoji": a.get("award_emoji", "🏆"),
                        "reason": a.get("award_reason", ""), "year": a["year"]}
                       for a in awards],
            "data_start_date": portrait.get("data_start_date") or "",
            "data_end_date": portrait.get("data_end_date") or "",
            "last_updated": portrait["last_updated"],
        },
    }


async def _run_portrait_and_save(group_id: int, member_id: int, task):
    """后台执行：画像生成 + 保存（v0.13.0: 加 try/except 防任务挂起）"""
    try:
        await _do_run_portrait_and_save(group_id, member_id, task)
    except Exception as e:
        logger.error(f"画像生成异常 [member_id={member_id}]: {e}", exc_info=True)
        try:
            task.finish(success=False, error={"type": "internal_error", "detail": str(e)})
        except Exception:
            pass


async def _do_run_portrait_and_save(group_id: int, member_id: int, task):
    """_run_portrait_and_save 的实际实现"""
    group = get_group(group_id)
    chat = get_chat_cache(group_id)
    member = get_member(group_id, member_id)
    if not all([group, chat, member]):
        task.finish(success=False, error={"type": "data_missing", "detail": "数据未找到"})
        return

    result = await generate_single_portrait(
        group_id=group_id,
        group_name=group["name"],
        wxid=member["wxid"],
        sender_name=member["display_name"] or member["nickname"],
        chat=chat,
        model=config.OLLAMA_MODEL,
        task=task,
    )

    if result["success"] and result["data"]:
        from models.database import save_member_portrait
        portrait_json = json.dumps(result["data"], ensure_ascii=False)
        save_member_portrait(
            group_id=group_id, member_id=member_id,
            display_name=member["display_name"] or member["nickname"],
            total_messages=result.get("_analyzed_msg_count", member["message_count"]),
            portrait_json=portrait_json,
            data_start=result.get("_data_start") or group.get("date_range_start") or "",
            data_end=result.get("_data_end") or group.get("date_range_end") or "",
        )
        task.finish(success=True)
        log_analysis(group_id, "", "portrait", "success", duration_ms=result["duration_ms"])
    else:
        task.finish(success=False, error={"type": "ai_failed", "detail": result.get("error", "")})


@router.post("/portrait/{member_id}/refresh")
async def api_refresh_single_portrait(group_id: int, member_id: int):
    """刷新单个成员的画像（已合并到统一分析端点）"""
    return await api_analyze_portrait(group_id, member_id)


@router.post("/portraits/refresh-all")
async def api_refresh_all_portraits(group_id: int, force: bool = False):
    """刷新群内所有需要更新的画像"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    results = await refresh_portraits(
        group_id=group_id,
        group_name=group["name"],
        chat=chat,
        model=config.OLLAMA_MODEL,
        force=force,
    )

    refreshed_count = sum(1 for r in results if r["refreshed"])
    # 构建返回结果：portrait 可能是 DB 行的 portrait_json 字符串，也可能是已解析的 dict
    result_list = []
    for r in results:
        portrait = r.get("portrait")
        if isinstance(portrait, dict):
            # 如果是 DB 行 dict（有 portrait_json 键），解析 JSON 字符串
            if "portrait_json" in portrait:
                try:
                    portrait_data = json.loads(portrait["portrait_json"])
                except (json.JSONDecodeError, TypeError):
                    portrait_data = {}
            else:
                # 已经是解析好的画像 dict
                portrait_data = portrait
        else:
            portrait_data = {}
        result_list.append({
            "member_name": r["member"]["display_name"],
            "refreshed": r["refreshed"],
            "portrait": portrait_data,
        })
    return {
        "code": 200,
        "message": f"画像刷新完成，{refreshed_count}/{len(results)} 个需要更新",
        "data": {
            "total": len(results),
            "refreshed": refreshed_count,
            "results": result_list,
        },
    }


# ---- v0.5 新端点 ----

@router.get("/portrait/{member_id}/history")
async def api_portrait_history(group_id: int, member_id: int):
    """获取成员画像的版本历史"""
    portrait = get_portrait(group_id, member_id)
    if not portrait:
        raise HTTPException(404, detail="该成员尚无画像")

    versions = get_portrait_versions(group_id, member_id)

    # 当前版本也算一个版本
    try:
        current_data = json.loads(portrait["portrait_json"])
    except (json.JSONDecodeError, TypeError):
        current_data = {}

    history = []
    for v in versions:
        try:
            vj = json.loads(v["portrait_json"])
        except (json.JSONDecodeError, TypeError):
            vj = {}
        history.append({
            "version": v["version"],
            "analyzed_msg_count": v["analyzed_msg_count"],
            "data_start_date": v.get("data_start_date") or "",
            "data_end_date": v.get("data_end_date") or "",
            "created_at": v["created_at"],
            "one_line": vj.get("one_line", ""),
            "personality": vj.get("personality", []),
            "role": vj.get("role", ""),
            "emoji_style": vj.get("emoji_style", ""),
        })

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "current": {
                "one_line": current_data.get("one_line", ""),
                "personality": current_data.get("personality", []),
                "role": current_data.get("role", ""),
                "emoji_style": current_data.get("emoji_style", ""),
                "last_updated": portrait["last_updated"],
            },
            "history": history,
        },
    }


@router.get("/portrait/{member_id}/stats")
async def api_portrait_stats(group_id: int, member_id: int):
    """获取成员的 Python 统计数据

    优化：大部分数据在画像生成时已计算并存入 portrait JSON，
    此处只读缓存，仅 recent_status 和 emotion_timeline 需要实时计算。
    """
    portrait_row = get_portrait(group_id, member_id)
    if not portrait_row:
        raise HTTPException(404, detail="该成员尚无画像")

    try:
        portrait_json = json.loads(portrait_row["portrait_json"])
    except (json.JSONDecodeError, TypeError):
        portrait_json = {}

    # 从缓存读取（画像刷新时一次性计算并存储）
    activity = portrait_json.get("activity_stats", {})
    language = portrait_json.get("language_stats", {})
    social_relations = portrait_json.get("social_relations", [])
    message_style = portrait_json.get("message_style", {})
    topic_role = portrait_json.get("topic_role", {})
    highlight_quotes = portrait_json.get("highlight_quotes", [])
    signature_emoji = portrait_json.get("signature_emoji", "")

    # 仅补全轻量级字段（不需要全量消息遍历的）
    if not message_style and activity:
        from services.stats_engine import compute_message_style
        message_style = compute_message_style(language, activity)
    if not signature_emoji and language:
        signature_emoji = language.get("top_emojis", [{}])[0].get("emoji", "") if language.get("top_emojis") else ""

    # 使用深度画像中的月度情绪数据作为 timeline
    from services.pipelines import MOOD_MAP
    emotion = portrait_json.get("emotion_profile", {}).get("timeline", [])
    if not emotion:
        # 回退：从 monthly_analyses 构建
        deep_monthly = portrait_json.get("monthly_analyses", [])
        if not deep_monthly:
            deep_monthly = portrait_json.get("emotion_profile", {}).get("monthly_analyses", [])
        emotion = [
            {"date": m.get("month", ""), "mood": m.get("mood", ""),
             "mood_emoji": MOOD_MAP.get(m.get("mood", ""), "😐")}
            for m in deep_monthly
        ]
    # 补全旧数据可能缺失的 emoji
    for e in emotion:
        if not e.get("mood_emoji"):
            e["mood_emoji"] = MOOD_MAP.get(e.get("mood", ""), "😐")

    # 仅 realtime 数据需要实时计算（轻量，只查最近30天）
    chat = get_chat_cache(group_id)
    member = get_member(group_id, member_id)
    wxid = member["wxid"] if member else ""
    member_names = set()
    if chat and wxid:
        for s in chat.senders:
            name = chat.get_name_by_wxid(s.get("wxid", "") or f"unknown_{s.get('senderID', 0)}")
            if name and len(name) >= 2:
                member_names.add(name)
        sender_msgs = [m for m in chat.messages if m.get("wxid") == wxid]
        from services.stats_engine import compute_recent_status
        recent_status = compute_recent_status([], member_names=member_names, sender_msgs=sender_msgs)

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "activity": activity,
            "language": language,
            "social_relations": social_relations,
            "emotion_timeline": emotion,
            "message_style": message_style,
            "recent_status": recent_status,
            "topic_role": topic_role,
            "highlight_quotes": highlight_quotes,
            "signature_emoji": signature_emoji,
        },
    }


async def _run_full_portrait_analysis(group_id: int, member_id: int, task, model_id: int = None):
    """统一画像分析：基础 pipeline + 深度 pipeline + Python 统计，一次生成完整画像

    v0.12.2: 支持 model_id 选择模型（本地或在线均可）。
    """
    try:
        await _do_run_full_portrait_analysis(group_id, member_id, task, model_id=model_id)
    except Exception as e:
        logger.error(f"画像分析异常: {e}", exc_info=True)
        if task.type != "analyze_all_portraits":
            task.finish(success=False, error={"type": "internal_error", "detail": str(e)})


async def _do_run_full_portrait_analysis(group_id: int, member_id: int, task, model_id: int = None):
    group = get_group(group_id)
    chat = get_chat_cache(group_id)
    member = get_member(group_id, member_id)
    if not all([group, chat, member]):
        if task.type != "analyze_all_portraits":
            task.finish(success=False, error={"type": "data_missing", "detail": "数据未找到"})
        return

    # v0.12.2: 解析模型配置
    from services.model_config import get_effective_model, _row_to_config
    from models.database import get_model_config as db_get_model_config

    if model_id is not None:
        db_config = db_get_model_config(model_id)
        if not db_config or not db_config.get("is_enabled", 1):
            if task.type != "analyze_all_portraits":
                task.finish(success=False, error={"type": "invalid_model", "detail": f"模型 ID={model_id} 不存在或已禁用"})
            return
        model_config = _row_to_config(db_config)
    else:
        model_config = get_effective_model("local")
    is_online = model_config.get("model_type") == "online"

    wxid = member["wxid"]
    sender_name = member["display_name"] or member["nickname"]

    # 收集该成员的文本消息
    all_dates = sorted(chat.all_dates())

    all_msgs = []
    for date in all_dates:
        day_msgs = chat.get_portrait_messages_for_date(date)
        all_msgs.extend([m for m in day_msgs if m.get("wxid") == wxid])

    if len(all_msgs) < 5:
        if task.type != "analyze_all_portraits":
            task.finish(success=False, error={
                "type": "too_few",
                "detail": f"{sender_name} 仅 {len(all_msgs)} 条文本消息（需至少 5 条）"
            })
        return

    existing = get_portrait(group_id, member_id)

    import time as _time
    start_time = _time.time()

    # 统一管理步骤：清空后两个 pipeline 各自追加
    if task:
        task.steps.clear()

    # ---- Step 1: 画像 Pipeline（v0.12.2: 在线单次 / 本地分步） ----
    # 构建 member_names + all_wxids（增量和全量都需要）
    member_names = set()
    all_wxids = set()
    for s in chat.senders:
        name = chat.get_name_by_wxid(s.get("wxid", "") or f"unknown_{s.get('senderID', 0)}")
        if name and len(name) >= 2:
            member_names.add(name)
        swxid = s.get("wxid", "")
        if swxid:
            all_wxids.add(swxid)

    from services.parser import format_sender_messages_for_portrait
    chat_text = format_sender_messages_for_portrait(all_msgs, sender_name,
                                                     member_names=member_names)

    is_private = len(chat.senders) <= 2

    if is_online:
        # v0.12.2: 在线模型单次调用画像管线
        task.update("inference", f"🎨 {model_config.get('model_name', 'AI')} 正在描绘 {sender_name} 的群聊人格...")
        from services.pipelines import run_portrait_pipeline_online
        try:
            portrait_data = await run_portrait_pipeline_online(
                chat_text, sender_name, group["name"], len(all_msgs),
                model_config=model_config, task=task, is_private=is_private,
            )
        except Exception as e:
            logger.error(f"在线画像管线失败: {sender_name}: {e}")
            if task.type != "analyze_all_portraits":
                task.finish(success=False, error={"type": "portrait_failed", "detail": str(e)})
            return
    else:
        # 本地模型：原有 4 步子任务管线
        task.update("inference", "🎭 基础画像分析中...")
        from services.pipelines import run_portrait_pipeline
        try:
            portrait_data = await run_portrait_pipeline(
                chat_text, sender_name, group["name"], len(all_msgs), task=task,
                is_private=is_private,
            )
        except Exception as e:
            logger.error(f"基础画像 pipeline 失败: {sender_name}: {e}")
            if task.type != "analyze_all_portraits":
                task.finish(success=False, error={"type": "basic_failed", "detail": str(e)})
            return

    data_start = all_dates[0] if all_dates else ""
    data_end = all_dates[-1] if all_dates else ""
    portrait_data["_data_start"] = data_start
    portrait_data["_data_end"] = data_end

    # ---- Step 2: Python 统计 ----
    task.update("inference", "📊 数据分析中...")
    task.add_step(name="统计数据", status="running")
    from services.stats_engine import (
        compute_activity_stats, compute_language_stats,
        compute_social_relations, format_stats_for_ai,
    )
    from services.social import analyze_social_relations

    activity = compute_activity_stats(chat.messages, wxid)
    language = compute_language_stats(chat.messages, wxid, member_names)
    social_relations = await analyze_social_relations(
        chat.messages, wxid, sender_name, chat.get_sender_name, chat.get_name_by_wxid,
        model_config=model_config if is_online else None,
    )
    stats_summary = format_stats_for_ai(activity, language, social_relations, [])

    # v0.6.4: 如果 AI emoji 为空，用 Python 根据实际数据自动选择（兜底）
    if not portrait_data.get("emoji_style"):
        from services.pipelines import _auto_select_emoji
        portrait_data["emoji_style"] = _auto_select_emoji(
            top_emojis=language.get("top_emojis", []),
            peak_hour=activity.get("peak_hour", 12),
            avg_msg_len=language.get("avg_msg_len", 0),
            avg_daily=activity.get("avg_daily_msgs", 0),
        )
        logger.info(f"{sender_name}: AI emoji 未匹配，Python 自动选择 {portrait_data['emoji_style']}")

    # ---- Step 3: 深度画像分析（v0.12.2: 在线模型已在 Step1 完成，跳过） ----
    if not is_online:
        if task:
            for s in task.steps:
                if s["name"] == "统计数据" and s["status"] == "running":
                    s["status"] = "done"
        task.update("inference", "🔬 深度分析中...")
        from services.pipelines import run_deep_portrait_pipeline
        deep_data = await run_deep_portrait_pipeline(
            chat_text="",
            messages=all_msgs,
            sender_name=sender_name,
            group_name=group["name"],
            group_id=group_id,
            msg_count=len(all_msgs),
            stats_summary=stats_summary,
            task=task,
        )
        portrait_data["emotion_profile"] = deep_data.get("emotion_profile", {})
        portrait_data["language_style"] = deep_data.get("language_style", {})
        portrait_data["monthly_synthesis"] = deep_data.get("monthly_synthesis", "")
    else:
        # v0.12.2: 在线模型已在单次调用中生成深度字段
        portrait_data["emotion_profile"] = {
            "primary": portrait_data.get("emotion_summary", ""),
            "trend": "",
            "timeline": [],
        }
        portrait_data["language_style"] = {
            "style_notes": portrait_data.get("language_notes", ""),
        }
        portrait_data["monthly_synthesis"] = portrait_data.get("deep_insight", "")
        # 在线模型标记
        portrait_data["_online_generated"] = True

    # ---- 合并数据统计（增量全量都更新） ----
    portrait_data["social_relations"] = social_relations
    portrait_data["activity_stats"] = {
        "total_days_active": activity["total_days_active"],
        "total_messages": activity["total_messages"],
        "avg_daily_msgs": activity["avg_daily_msgs"],
        "peak_hour": activity["peak_hour"],
        "hourly_heatmap": activity["hourly_heatmap"],
        "monthly_trend": activity["monthly_trend"],
    }
    portrait_data["language_stats"] = language  # 全量存储，供前端展示

    # v0.6.4: 一次性计算可缓存数据，避免每次打开页面重算
    from services.stats_engine import (
        compute_message_style, compute_topic_role,
        compute_highlight_quotes,
    )
    portrait_data["message_style"] = compute_message_style(language, activity)
    portrait_data["topic_role"] = compute_topic_role(chat.messages, wxid, all_wxids)
    portrait_data["highlight_quotes"] = compute_highlight_quotes(
        group_id, wxid, sender_name, all_msgs
    )
    portrait_data["signature_emoji"] = (
        language.get("top_emojis", [{}])[0].get("emoji", "") if language.get("top_emojis") else ""
    )
    # ---- 趣味功能 (v0.5.1, v0.12.2: 在线模型时走在线调用) ----
    task.update("inference", "🏆 趣味称号生成中...")
    from services.stats_engine import compute_fun_title_basis
    from services.pipelines import FUN_TITLE_PROMPTS, FUN_RELATION_PROMPTS

    # 趣味称号
    title_basis = compute_fun_title_basis(activity, language, social_relations,
                                           language.get("top_emojis", []))
    title_user = FUN_TITLE_PROMPTS["user"].format(
        name=sender_name, data_summary=title_basis["data_summary"]
    )
    fun_title = title_basis["category"]  # Python 统计兜底
    try:
        if is_online:
            from services.online_model import call_online_chat
            title_result = await call_online_chat(
                FUN_TITLE_PROMPTS["system"], title_user, model_config,
                temperature=0.5, max_tokens=30,
            )
        else:
            from services.analyzer import call_ollama_chat
            title_result = await call_ollama_chat(
                FUN_TITLE_PROMPTS["system"], title_user, config.OLLAMA_MODEL, timeout=20
            )
        if title_result.get("data"):
            fun_title = str(title_result["data"]).strip()
    except Exception as e:
        logger.warning(f"趣味称号生成失败: {e}，使用统计兜底")

    # 关系趣味解读（Top 1 互动对象）
    fun_relation = ""
    if social_relations and len(social_relations) > 0:
        top = social_relations[0]
        rel_user = FUN_RELATION_PROMPTS["user"].format(
            name_a=sender_name, name_b=top.get("name", "?"),
            count=top.get("total_interactions", 0),
            relation_type=top.get("relation_type", "群友"),
        )
        try:
            if is_online:
                from services.online_model import call_online_chat
                rel_result = await call_online_chat(
                    FUN_RELATION_PROMPTS["system"], rel_user, model_config,
                    temperature=0.5, max_tokens=30,
                )
            else:
                from services.analyzer import call_ollama_chat
                rel_result = await call_ollama_chat(
                    FUN_RELATION_PROMPTS["system"], rel_user, config.OLLAMA_MODEL, timeout=20
                )
            fun_relation = str(rel_result["data"]).strip() if rel_result.get("data") else ""
        except Exception as e:
            logger.warning(f"关系解读生成失败: {e}")

    portrait_data["fun_title"] = fun_title
    portrait_data["fun_relation"] = fun_relation

    portrait_data["_analyzed_at"] = datetime.now().isoformat()
    portrait_data["_analyzed_msg_count"] = len(all_msgs)

    # ---- 归档旧版本 + 保存 ----
    if existing:
        latest_ver = get_latest_portrait_version(group_id, member_id)
        save_portrait_version(
            group_id=group_id, member_id=member_id,
            version=latest_ver + 1,
            portrait_json=existing.get("portrait_json", "{}"),
            analyzed_msg_count=existing.get("total_analyzed_messages", 0),
            data_start=existing.get("data_start_date", ""),
            data_end=existing.get("data_end_date", ""),
            model_used=task.model_used or config.OLLAMA_MODEL,
            duration_ms=task.duration_ms,
        )

    portrait_json = json.dumps(portrait_data, ensure_ascii=False)
    date_start, date_end = chat.get_date_range()
    save_member_portrait(
        group_id=group_id, member_id=member_id,
        display_name=sender_name,
        total_messages=len(all_msgs),
        portrait_json=portrait_json,
        data_start=date_start,
        data_end=date_end,
    )
    duration_ms = int((_time.time() - start_time) * 1000)
    model_used = model_config.get("model_name", config.OLLAMA_MODEL)
    task.model_used = model_used
    task.duration_ms = duration_ms
    # 批量任务不在这里 finish，由外层循环控制
    if task.type != "analyze_all_portraits":
        task.finish(success=True)
    log_analysis(group_id, "", "full_portrait", "success",
                 model_used=model_used, duration_ms=duration_ms)


@router.post("/portrait/{member_id}/analyze")
async def api_analyze_portrait(group_id: int, member_id: int, model_id: int = None):
    """统一画像分析：一键生成/刷新完整画像（基础+深度）

    v0.12.2: 新增 model_id 参数，支持选择在线模型单次生成画像。
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    member = get_member(group_id, member_id)
    if not member:
        raise HTTPException(404, detail="成员不存在")

    existing = get_portrait(group_id, member_id)
    label = "刷新" if existing else "生成"

    task = task_manager.create("full_portrait", group_id, {"member_id": member_id})
    task.update("pending", f"全量{label} {member['display_name']} 的画像...")
    asyncio.create_task(_run_full_portrait_analysis(group_id, member_id, task, model_id=model_id))

    return {
        "code": 200,
        "message": f"画像{label}任务已创建",
        "data": {"task_id": task.task_id, "status": "pending"},
    }


# 保留旧端点兼容，内部转发
@router.post("/portrait/{member_id}/deep")
async def api_deep_portrait(group_id: int, member_id: int, model_id: int = None):
    """触发深度画像生成（已合并到 /analyze，保留兼容）"""
    return await api_analyze_portrait(group_id, member_id, model_id=model_id)


async def _run_analyze_all_portraits(group_id: int, group_name: str, task, model_id: int = None):
    """后台执行：一键分析全群画像（全量分析所有成员，不做增量跳过）

    v0.12.2: 支持 model_id 参数。
    """
    chat = get_chat_cache(group_id)
    if not chat:
        task.finish(success=False, error={"type": "data_missing", "detail": "群数据未加载"})
        return

    members = get_members(group_id)
    if not members:
        task.update("done", "没有成员数据")
        task.finish(success=True)
        return

    total = len(members)
    failed = 0
    task.update("pending", f"准备分析 {total} 人...", progress={"current": 0, "total": total})

    for i, member in enumerate(members):
        if task_manager.is_cancelled(task.task_id):
            task.update("cancelled", f"已取消 (完成 {i}/{total})")
            return

        sender_name = member["display_name"] or member["nickname"]
        task.update("inference", f"({i+1}/{total}) 分析 {sender_name}...",
                   progress={"current": i, "total": total})

        try:
            await _run_full_portrait_analysis(group_id, member["id"], task, model_id=model_id)
        except Exception as e:
            logger.error(f"批量画像分析失败: {sender_name}: {e}")
            failed += 1
            task.update("inference", f"({i+1}/{total}) {sender_name} 失败",
                       progress={"current": i + 1, "total": total})

        task.update("inference", f"已完成 {i + 1}/{total} (失败 {failed})",
                   progress={"current": i + 1, "total": total})
        await asyncio.sleep(2)  # 成员之间短暂冷却

    # 分析完成后强制 Python GC 回收临时对象
    import gc
    gc.collect()
    # 注：系统级缓存（Ollama 模型遗留的 ~8GB page cache）由 WSL autoMemoryReclaim 自动回收
    # 不要手动 drop_caches，可能触发 OOM 或导致其他服务异常

    msg = f"画像分析完成：{total - failed}/{total} 成功"
    if failed > 0:
        msg += f"，{failed} 人失败"
    task.update("done", msg, progress={"current": total, "total": total})
    task.finish(success=True)


@router.get("/portrait/{member_id}/archaeology")
async def api_member_archaeology(group_id: int, member_id: int):
    """群友考古：第一条发言、最长发言、历史今日"""
    chat = get_chat_cache(group_id)
    member = get_member(group_id, member_id)
    if not chat or not member:
        raise HTTPException(404, detail="数据未找到")

    wxid = member["wxid"]
    name = member["display_name"] or member["nickname"]

    # 筛选该成员的文本消息
    msgs = [m for m in chat.messages
            if m.get("wxid") == wxid
            and m.get("type") == "文本消息"
            and (m.get("content") or "").strip()]

    if not msgs:
        return {"code": 200, "message": "暂无数据", "data": None}

    msgs.sort(key=lambda m: m.get("createTime", 0))

    first = msgs[0]
    longest = max(msgs, key=lambda m: len((m.get("content") or "").strip()))
    last = msgs[-1]

    # 历史上的今天：找去年同月同日的消息
    today = datetime.now().strftime("%m-%d")
    on_this_day = []
    for m in msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 10 and ft[5:] == today:
            yr = ft[:4]
            if yr != datetime.now().strftime("%Y"):
                on_this_day.append(m)
    on_this_day = on_this_day[-3:]  # 最近3条

    # 按年统计发言量
    year_counts = {}
    for m in msgs:
        ft = m.get("formattedTime", "")
        if len(ft) >= 4:
            yr = ft[:4]
            year_counts[yr] = year_counts.get(yr, 0) + 1

    data = {
        "name": name,
        "total_msgs": len(msgs),
        "first_msg": {
            "date": first.get("formattedTime", "")[:10],
            "content": (first.get("content") or "").strip()[:200],
        },
        "longest_msg": {
            "date": longest.get("formattedTime", "")[:10],
            "content": (longest.get("content") or "").strip()[:200],
            "length": len((longest.get("content") or "").strip()),
        },
        "latest_msg": {
            "date": last.get("formattedTime", "")[:10],
            "content": (last.get("content") or "").strip()[:200],
        },
        "on_this_day": [{"date": m.get("formattedTime", "")[:10],
                          "content": (m.get("content") or "").strip()[:200]}
                         for m in on_this_day],
        "yearly_counts": year_counts,
        "date_range": [msgs[0].get("formattedTime", "")[:10],
                       msgs[-1].get("formattedTime", "")[:10]],
    }

    return {"code": 200, "message": "获取成功", "data": data}


@router.get("/relations")
async def api_group_relations(group_id: int):
    """获取群内成员互动关系图数据（所有配对）"""
    chat = get_chat_cache(group_id)
    if not chat:
        raise HTTPException(404, detail="群数据未加载")

    members = get_members(group_id)
    if len(members) < 2:
        return {"code": 200, "message": "成员不足", "data": {"nodes": [], "links": []}}

    from services.stats_engine import compute_social_relations

    nodes = []
    all_links = []

    for m in members:
        wxid = m["wxid"]
        name = m["display_name"] or m["nickname"]
        nodes.append({"id": m["id"], "wxid": wxid, "name": name, "msg_count": m["message_count"]})

        relations = compute_social_relations(
            chat.messages, wxid, chat.get_sender_name, chat.get_name_by_wxid
        )
        for r in relations:
            if r.get("total_interactions", 0) > 0:
                all_links.append({
                    "source": wxid,
                    "target": r["wxid"],
                    "weight": r["total_interactions"],
                })

    # 去重：只保留 source < target 的链接（无向图）
    seen = set()
    links = []
    for link in all_links:
        key = tuple(sorted([link["source"], link["target"]]))
        if key not in seen:
            seen.add(key)
            links.append(link)

    # 只保留 Top 50 链接
    links.sort(key=lambda x: x["weight"], reverse=True)
    links = links[:50]

    return {"code": 200, "message": "获取成功", "data": {"nodes": nodes, "links": links}}


@router.post("/portraits/analyze-all")
async def api_analyze_all_portraits(group_id: int, model_id: int = None):
    """一键分析全群画像

    v0.12.2: 新增 model_id 参数。
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    members = get_members(group_id)
    if not members:
        return {"code": 200, "message": "没有成员数据", "data": {"total": 0}}

    total = len(members)
    task = task_manager.create("analyze_all_portraits", group_id, {"total": total})
    task.update("pending", f"批量分析 {total} 人...", progress={"current": 0, "total": total})

    asyncio.create_task(_run_analyze_all_portraits(group_id, group["name"], task, model_id=model_id))

    return {
        "code": 200,
        "message": f"批量画像分析已创建：{total} 人",
        "data": {"task_id": task.task_id, "total": total},
    }
