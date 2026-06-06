"""
群管理 API：列表、创建、上传（新建群）、导入（追加到已有群）、删除
"""
import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel

from config import config
from models.database import (
    create_group, list_groups, get_group, delete_group,
    upsert_members, update_member_message_count, get_members,
    get_conn,
)
from services.parser import load_and_parse, ParsedChat, merge_chat_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups", tags=["群管理"])

# 全局缓存已解析的聊天数据: {group_id: ParsedChat}
_chat_cache: dict[int, ParsedChat] = {}


def get_chat_cache(group_id: int) -> ParsedChat | None:
    """获取缓存的 ParsedChat 对象（延迟加载）"""
    if group_id in _chat_cache:
        return _chat_cache[group_id]

    group = get_group(group_id)
    if not group or not group.get("file_path"):
        return None

    file_path = Path(group["file_path"])
    if not file_path.exists():
        return None

    chat = load_and_parse(file_path)
    _chat_cache[group_id] = chat
    return chat


def _invalidate_cache(group_id: int):
    """清除群缓存（数据变更后调用）"""
    _chat_cache.pop(group_id, None)


class CreateGroupBody(BaseModel):
    name: str
    display_name: str = ""


@router.get("")
async def api_list_groups():
    """获取所有已导入的群列表"""
    groups = list_groups()
    return {"code": 200, "message": "获取成功", "data": groups}


@router.post("")
async def api_create_group(body: CreateGroupBody):
    """手动创建空群（不含数据，后续通过导入追加数据）"""
    if not body.name.strip():
        raise HTTPException(400, detail="群名不能为空")

    group_id = create_group(
        name=body.name.strip(),
        display_name=body.display_name.strip() or body.name.strip(),
    )
    logger.info(f"创建空群: {body.name} (id={group_id})")
    return {
        "code": 200,
        "message": f"群「{body.name}」创建成功",
        "data": {"group_id": group_id, "name": body.name},
    }


@router.post("/upload")
async def api_upload_group(file: UploadFile = File(...)):
    """上传群聊 JSON 文件，自动创建新群并导入数据"""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, detail="请上传 .json 格式的聊天记录文件")

    # 保存文件
    config.ensure_dirs()
    safe_name = Path(file.filename).stem
    group_dir = config.DATA_DIR / f"import_{safe_name}"
    group_dir.mkdir(parents=True, exist_ok=True)
    file_path = group_dir / file.filename

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, detail=f"文件保存失败: {e}")

    # 解析 JSON
    try:
        chat = ParsedChat(file_path).load()
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail=f"JSON 解析失败: {e}")
    except Exception as e:
        raise HTTPException(500, detail=f"文件处理失败: {e}")

    # 写入数据库
    date_start, date_end = chat.get_date_range()
    group_id = create_group(
        name=chat.group_name,
        wxid=chat.group_wxid,
        display_name=chat.group_name,
        message_count=chat.message_count,
        sender_count=len(chat.senders),
        date_start=date_start,
        date_end=date_end,
        file_path=str(file_path),
    )

    # 写入成员 + 消息计数
    upsert_members(group_id, chat.senders)
    counts = chat.sender_text_counts()
    for wxid_val, count in counts.items():
        update_member_message_count(group_id, wxid_val, count)

    # 缓存
    _chat_cache[group_id] = chat

    logger.info(f"导入群成功: {chat.group_name} (id={group_id}), "
                f"{chat.message_count}条消息, {len(chat.senders)}人, "
                f"{len(chat.all_dates())}天有数据")

    return {
        "code": 200,
        "message": f"群「{chat.group_name}」导入成功",
        "data": {
            "group_id": group_id,
            "group_name": chat.group_name,
            "message_count": chat.message_count,
            "sender_count": len(chat.senders),
            "date_range": [date_start, date_end],
            "total_dates": len(chat.all_dates()),
        },
    }


@router.post("/{group_id}/import")
async def api_import_to_group(group_id: int, file: UploadFile = File(...),
                               mode: str = "append"):
    """向已有群导入 JSON 数据

    Args:
        mode: "append"=去重追加（默认）, "replace"=完全替换
    """
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, detail="请上传 .json 格式的聊天记录文件")

    if mode not in ("append", "replace"):
        raise HTTPException(400, detail="mode 必须是 append 或 replace")

    config.ensure_dirs()
    group_dir = Path(group["file_path"]).parent if group.get("file_path") else config.DATA_DIR / f"group_{group_id}"
    group_dir.mkdir(parents=True, exist_ok=True)

    # 保存上传文件
    upload_path = group_dir / file.filename
    try:
        content = await file.read()
        with open(upload_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, detail=f"文件保存失败: {e}")

    # 解析新 JSON
    try:
        new_chat = ParsedChat(upload_path).load()
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail=f"JSON 解析失败: {e}")

    existing_chat = get_chat_cache(group_id)

    # === wxid → senderID 映射：同一个人多次导出 senderID 可能不同 ===
    if existing_chat and mode == "append":
        # 构建已有数据的 wxid → senderID 映射
        wxid_to_sid: dict[str, int] = {}
        for s in existing_chat.senders:
            wxid = s.get("wxid", "")
            if wxid:
                wxid_to_sid[wxid] = s.get("senderID", 0)

        # 检查新数据中的 sender，同 wxid 但 senderID 不同 → remap
        remap: dict[int, int] = {}  # old_sid → new_sid
        for s in new_chat.senders:
            wxid = s.get("wxid", "")
            old_sid = wxid_to_sid.get(wxid, 0)
            new_sid = s.get("senderID", 0)
            if old_sid and old_sid != new_sid:
                remap[new_sid] = old_sid
                s["senderID"] = old_sid  # 更新 sender 记录

        # remap 消息中的 senderID
        if remap:
            remapped = 0
            for m in new_chat.messages:
                sid = m.get("senderID", 0)
                if sid in remap:
                    m["senderID"] = remap[sid]
                    remapped += 1
            logger.info(f"senderID remap: {len(remap)} 人, {remapped} 条消息")

    if mode == "replace" or not existing_chat:
        # 完全替换
        merged_chat = new_chat
        added = len(new_chat.messages)
        skipped = 0
    else:
        # 去重追加
        merge_result = merge_chat_data(existing_chat.messages, new_chat.messages)
        if merge_result["added"]:
            existing_chat.messages.extend(merge_result["added"])
            existing_chat.messages.sort(key=lambda m: m.get("createTime", 0))
            existing_chat._by_date = None
        merged_chat = existing_chat
        added = len(merge_result["added"])
        skipped = merge_result["skipped"]

    # 写回完整数据集到磁盘（重启后数据不丢失）
    merged_path = group_dir / "merged_data.json"
    try:
        merged_data = {
            "session": merged_chat.session,
            "senders": merged_chat.senders,
            "messages": merged_chat.messages,
        }
        with open(merged_path, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, ensure_ascii=False)
        logger.info(f"完整数据已写入: {merged_path} ({len(merged_chat.messages)} 条消息)")
    except Exception as e:
        logger.warning(f"写入合并文件失败: {e}，数据仅存于内存中")

    # 更新数据库
    date_start, date_end = merged_chat.get_date_range()
    conn = get_conn()
    conn.execute(
        """UPDATE chat_groups SET
           message_count=?, sender_count=?,
           date_range_start=?, date_range_end=?, file_path=?
           WHERE id=?""",
        (len(merged_chat.messages), len(merged_chat.senders),
         date_start, date_end, str(merged_path), group_id)
    )
    conn.commit()
    conn.close()

    # 更新成员
    upsert_members(group_id, merged_chat.senders)
    counts = merged_chat.sender_text_counts()
    for wxid_val, count in counts.items():
        update_member_message_count(group_id, wxid_val, count)

    # 刷新缓存
    _invalidate_cache(group_id)
    _chat_cache[group_id] = merged_chat

    return {
        "code": 200,
        "message": f"导入完成：新增 {added} 条，跳过 {skipped} 条重复",
        "data": {
            "group_id": group_id,
            "added": added,
            "skipped": skipped,
            "total_now": len(merged_chat.messages),
            "date_range": [date_start, date_end],
        },
    }


@router.delete("/{group_id}")
async def api_delete_group(group_id: int):
    """删除群及其所有数据（含文件和缓存）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    # 删除文件
    if group.get("file_path"):
        file_path = Path(group["file_path"])
        parent_dir = file_path.parent
        if parent_dir.exists():
            shutil.rmtree(parent_dir, ignore_errors=True)

    # 删除数据库记录（CASCADE 自动清理关联数据）
    delete_group(group_id)

    # 清理缓存
    _invalidate_cache(group_id)

    logger.info(f"删除群: {group.get('name')} (id={group_id})")
    return {"code": 200, "message": f"群「{group['name']}」已删除", "data": None}


@router.get("/{group_id}/members")
async def api_get_members(group_id: int):
    """获取群成员列表"""
    members = get_members(group_id)
    return {"code": 200, "message": "获取成功", "data": members}
