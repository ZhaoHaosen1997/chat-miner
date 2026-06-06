"""
群管理 API：列表、上传、删除
"""
import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from config import config
from models.database import (
    create_group, list_groups, get_group, delete_group,
    upsert_members, update_member_message_count,
)
from services.parser import load_and_parse, ParsedChat

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


@router.get("")
async def api_list_groups():
    """获取所有已导入的群列表"""
    groups = list_groups()
    return {"code": 200, "message": "获取成功", "data": groups}


@router.post("/upload")
async def api_upload_group(file: UploadFile = File(...)):
    """上传群聊 JSON 文件，解析并导入"""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, detail="请上传 .json 格式的聊天记录文件")

    # 保存文件到 data/ 目录
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

    # 写入成员
    upsert_members(group_id, chat.senders)

    # 更新成员消息数
    counts = chat.sender_text_counts()
    for sender_id, count in counts.items():
        update_member_message_count(group_id, sender_id, count)

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
    _chat_cache.pop(group_id, None)

    logger.info(f"删除群: {group.get('name')} (id={group_id})")
    return {"code": 200, "message": f"群「{group['name']}」已删除", "data": None}


@router.get("/{group_id}/members")
async def api_get_members(group_id: int):
    """获取群成员列表"""
    from models.database import get_members
    members = get_members(group_id)
    return {"code": 200, "message": "获取成功", "data": members}
