"""
群管理 API：列表、创建、上传（新建群）、导入（追加到已有群）、删除
"""
import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
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


@router.post("/{group_id}/import")
async def api_import_to_group(group_id: int, file: UploadFile = File(...)):
    """向已有群追加导入 JSON 数据（去重合并）"""
    group = get_group(group_id)
    if not group:
        raise HTTPException(404, detail="群不存在")

    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, detail="请上传 .json 格式的聊天记录文件")

    # 保存新文件（与已有数据放在同一目录）
    config.ensure_dirs()
    group_dir = Path(group["file_path"]).parent if group.get("file_path") else config.DATA_DIR / f"group_{group_id}"
    group_dir.mkdir(parents=True, exist_ok=True)
    new_file_path = group_dir / f"import_{Path(file.filename).name}"

    try:
        content = await file.read()
        with open(new_file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, detail=f"文件保存失败: {e}")

    # 解析新 JSON
    try:
        new_chat = ParsedChat(new_file_path).load()
    except json.JSONDecodeError as e:
        raise HTTPException(400, detail=f"JSON 解析失败: {e}")

    # 检测群名变化
    if new_chat.group_name and new_chat.group_name != group["name"]:
        logger.info(f"群名不一致: DB={group['name']}, JSON={new_chat.group_name}，保留原群名")

    # 加载已有数据并合并
    existing_chat = get_chat_cache(group_id)
    existing_msgs = existing_chat.messages if existing_chat else []

    merge_result = merge_chat_data(existing_msgs, new_chat.messages)

    if merge_result["added"]:
        # 合并消息到已有 chat 对象
        if existing_chat:
            existing_chat.messages.extend(merge_result["added"])
            existing_chat.messages.sort(key=lambda m: m.get("createTime", 0))
            existing_chat._by_date = None  # 使分块缓存失效
        else:
            # 首次导入到这个群
            existing_chat = new_chat

        # 更新数据库
        date_start, date_end = existing_chat.get_date_range()

        # 更新群信息
        conn = get_conn()
        conn.execute(
            """UPDATE chat_groups SET
               message_count=?, sender_count=?,
               date_range_start=?, date_range_end=?
               WHERE id=?""",
            (len(existing_chat.messages), len(existing_chat.senders),
             date_start, date_end, group_id)
        )
        conn.commit()
        conn.close()

        # 合并成员列表
        upsert_members(group_id, existing_chat.senders)
        counts = existing_chat.sender_text_counts()
        for sender_id, count in counts.items():
            update_member_message_count(group_id, sender_id, count)

        # 更新 file_path（指向导入文件所在目录）
        if not group.get("file_path"):
            conn2 = get_conn()
            conn2.execute("UPDATE chat_groups SET file_path=? WHERE id=?",
                          (str(new_file_path), group_id))
            conn2.commit()
            conn2.close()

        _invalidate_cache(group_id)
        _chat_cache[group_id] = existing_chat

        logger.info(f"追加导入: 群={group['name']}, 新增{len(merge_result['added'])}条, "
                    f"跳过{merge_result['skipped']}条重复")
    else:
        logger.info(f"追加导入: 全部 {merge_result['total_new']} 条消息均为重复，已跳过")

    return {
        "code": 200,
        "message": f"追加导入完成：新增 {len(merge_result['added'])} 条，跳过 {merge_result['skipped']} 条重复",
        "data": {
            "group_id": group_id,
            "added": len(merge_result["added"]),
            "skipped": merge_result["skipped"],
            "total_in_file": merge_result["total_new"],
            "total_now": (len(existing_chat.messages) if existing_chat else len(new_chat.messages)),
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
