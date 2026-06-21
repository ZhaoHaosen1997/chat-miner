"""
WeFlow 同步引擎
ChatLab 格式 → ParsedChat 格式转换 + 增量消息拉取 + 群关联
"""
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import config
from services.weflow_client import WeFlowClient, WeFlowError, WECHAT_TYPE_MAP
from services.parser import merge_chat_data

logger = logging.getLogger(__name__)

# 可分析的消息类型（客户端过滤：API 返回所有类型，我们只保留文本+引用）
_ANALYZABLE_TYPES = {0, 49}

# 文本类型（用于统计 TEXT_TYPES 口径，和 parser.py 的 TEXT_TYPES 对齐）
_TEXT_TYPES = {"文本消息", "引用消息"}


def filter_analyzable(messages: list[dict]) -> list[dict]:
    """客户端过滤：只保留可分析的消息（type=0 文本 + type=49 引用）

    其余类型（图片/视频/表情/语音/系统消息等）不在 chat-miner 分析范围内，
    丢弃以节省存储和内存。
    """
    filtered = [m for m in messages if m.get("type") in _ANALYZABLE_TYPES]
    if len(messages) > len(filtered):
        skipped = len(messages) - len(filtered)
        logger.debug(f"消息过滤: {len(messages)} → {len(filtered)} "
                     f"(丢弃 {skipped} 条非文本/非引用消息)")
    return filtered


def normalize_chatlab_to_parsed(chatlab_data: dict) -> dict:
    """ChatLab 格式 → ParsedChat 兼容格式

    将 WeFlow ChatLab Pull 返回的 {meta, members, messages, sync}
    转换为 ParsedChat 兼容的 {session, senders, messages}：
    - members[].platformId     → senders[].wxid
    - members[].groupNickname  → senders[].displayName 优先
    - members[].nickName       → senders[].displayName 次选（微信昵称）
    - members[].accountName    → senders[].displayName 兜底（备注）
    - members[].groupNickname  → senders[].groupNickname
    - messages[].sender        → messages[].wxid
    - messages[].timestamp     → messages[].createTime
    - messages[].type (int)    → messages[].type (str)

    Returns:
        {"session": {...}, "senders": [...], "messages": [...]}
        可直接传给 merge_chat_data + 磁盘写入
    """
    meta = chatlab_data.get("meta", {})
    members = chatlab_data.get("members", [])
    messages = chatlab_data.get("messages", [])

    # 1. 构建 session
    session = {
        "nickname": meta.get("name", ""),
        "wxid": meta.get("groupId", ""),
        "messageCount": len(messages),
    }

    # 2. 构建 senders（含 wxid → senderID 映射）
    wxid_to_sid: dict[str, int] = {}
    sid_to_sender: dict[int, dict] = {}
    next_sid = 1

    for member in members:
        wxid = member.get("platformId", "")
        if not wxid:
            continue
        if wxid in wxid_to_sid:
            continue
        wxid_to_sid[wxid] = next_sid
        # v1.2.11: 显示名优先级 群昵称 > 微信昵称 > 备注
        nick_name = member.get("nickName", "")
        account_name = member.get("accountName", "")
        group_nick = member.get("groupNickname", "")
        sid_to_sender[next_sid] = {
            "senderID": next_sid,
            "wxid": wxid,
            "displayName": group_nick or nick_name or account_name or "",
            "nickname": nick_name or account_name or "",
            "groupNickname": group_nick,
            "avatar": member.get("avatar", ""),
        }
        next_sid += 1

    # 对 messages 中出现但 members 中未列出的 sender，动态补齐
    for msg in messages:
        sender_wxid = msg.get("sender", "")
        if not sender_wxid or sender_wxid in wxid_to_sid:
            continue
        # 排除群 ID 自身（系统消息的 sender 可能是 chatroom id）
        if "@chatroom" in sender_wxid:
            continue
        nick_name = msg.get("nickName", "")
        account_name = msg.get("accountName", "")
        group_nick = msg.get("groupNickname", "")
        wxid_to_sid[sender_wxid] = next_sid
        sid_to_sender[next_sid] = {
            "senderID": next_sid,
            "wxid": sender_wxid,
            "displayName": group_nick or nick_name or account_name or "",
            "nickname": nick_name or account_name or "",
            "groupNickname": group_nick,
            "avatar": "",
        }
        logger.debug(f"动态补充成员: {sender_wxid} → senderID={next_sid}")
        next_sid += 1

    senders = list(sid_to_sender.values())

    # 3. 转换消息
    normalized_msgs = []
    for msg in messages:
        sender_wxid = msg.get("sender", "")
        sid = wxid_to_sid.get(sender_wxid, 0)
        timestamp = msg.get("timestamp", 0)
        numeric_type = msg.get("type", 0)
        str_type = WECHAT_TYPE_MAP.get(numeric_type, "系统消息")
        content = msg.get("content", "") or ""
        platform_id = msg.get("platformMessageId", "")

        normalized_msgs.append({
            "wxid": sender_wxid,
            "senderID": sid,
            "createTime": timestamp,
            "formattedTime": datetime.fromtimestamp(timestamp).strftime(
                "%Y-%m-%d %H:%M:%S") if timestamp else "",
            "type": str_type,
            "content": content,
            "platformMessageId": str(platform_id),
        })

    # 按时间排序
    normalized_msgs.sort(key=lambda m: m.get("createTime", 0))

    logger.debug(f"ChatLab 转换: {len(members)} 成员, {len(messages)} 消息 "
                 f"→ {len(senders)} senders, {len(normalized_msgs)} messages")

    return {
        "session": session,
        "senders": senders,
        "messages": normalized_msgs,
    }


def _get_last_message_timestamp(group_id: int) -> int:
    """获取已有数据的最后一条消息时间戳（秒）

    三层 fallback：内存缓存 → merged_data.json → 原始上传文件
    """
    # 优先从内存缓存取
    try:
        from routers.groups import get_chat_cache
        chat = get_chat_cache(group_id)
        if chat and chat.messages:
            ts = max(m.get("createTime", 0) for m in chat.messages)
            logger.debug(f"[WeFlow] since 来源=内存缓存 group={group_id} ts={ts}")
            return ts
    except Exception as e:
        logger.debug("从内存缓存读取最后消息时间失败: %s", e)

    # 回退：读 merged_data.json
    merged_path = _get_merged_data_path(group_id)
    if merged_path and merged_path.exists():
        try:
            with open(merged_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
            if messages:
                ts = max(m.get("createTime", 0) for m in messages)
                logger.debug(f"[WeFlow] since 来源=merged_data.json group={group_id} ts={ts}")
                return ts
        except Exception as e:
            logger.debug("从磁盘读取最后消息时间失败: %s", e)

    # 最后 fallback：从原始上传文件读取
    try:
        from services.parser import load_and_parse
        from models.database import get_group
        grp = get_group(group_id)
        if grp and grp.get("file_path"):
            fp = Path(grp["file_path"])
            if fp.exists():
                chat = load_and_parse(fp)
                if chat and chat.messages:
                    ts = max(m.get("createTime", 0) for m in chat.messages)
                    logger.info(f"[WeFlow] since 来源=原始文件 group={group_id} ts={ts}")
                    return ts
    except Exception as e:
        logger.debug("从原始文件读取最后时间失败: %s", e)

    logger.info(f"[WeFlow] since 来源=无 (从头拉取) group={group_id}")
    return 0


def _get_merged_data_path(group_id: int) -> Optional[Path]:
    """根据 group_id 获取 merged_data.json 路径

    优先直接从 group 的 file_path 目录查找，不要求原始文件一定存在
    （原始文件可能被清理但 merged_data.json 仍在同目录）。
    """
    from models.database import get_group
    group = get_group(group_id)
    if not group or not group.get("file_path"):
        return None
    merged_path = Path(group["file_path"]).parent / "merged_data.json"
    if not merged_path.is_absolute():
        merged_path = config.BASE_DIR / merged_path
    if merged_path.exists():
        return merged_path
    return None


def sync_messages_incremental(client: WeFlowClient, group_id: int,
                               task=None) -> dict:
    """增量拉取 WeFlow 新消息并合并到已有数据

    1. 获取已有数据最后消息时间 → since
    2. 循环调用 ChatLab Pull（分页），拉取 since 之后的新消息
    3. 过滤非文本消息
    4. 格式转换
    5. 调用 merge_chat_data 去重合并
    6. 写入磁盘 + 更新 DB

    Args:
        client: WeFlow API 客户端
        group_id: chat-miner 群 ID
        task: 可选的 TaskInfo 对象（用于进度上报和取消检测）

    Returns:
        {"added": N, "skipped": N, "total_pulled": N, "new_date_range_end": str}
    """
    from models.database import get_group, upsert_members, update_member_message_count

    group = get_group(group_id)
    if not group:
        raise ValueError(f"群不存在: group_id={group_id}")

    chatroom_id = group.get("wxid", "")
    if not chatroom_id:
        raise ValueError(f"群 wxid 为空: group_id={group_id}")

    # 1. 计算 since
    since = _get_last_message_timestamp(group_id)
    if task:
        task.update("pending", f"增量拉取 since={datetime.fromtimestamp(since).strftime('%Y-%m-%d %H:%M') if since else '全量'}...")

    logger.info(f"[WeFlow Sync] group={group['name']} chatroom={chatroom_id} since={since}"
                f" (ts={datetime.fromtimestamp(since).strftime('%Y-%m-%d %H:%M:%S') if since else '从头拉取'})")

    # 2. 分页拉取所有新消息
    all_chatlab_messages = []
    offset = 0
    batch = 0
    total_pulled = 0

    while True:
        if task and task._cancelled:
            return {"added": 0, "skipped": 0, "total_pulled": total_pulled,
                    "cancelled": True}

        batch += 1
        try:
            resp = client.get_session_messages(
                chatroom_id, limit=1000, since=since, offset=offset
            )
        except WeFlowError as e:
            logger.error(f"[WeFlow Sync] 拉取失败 (batch={batch}): {e}")
            if task:
                task.update("failed", f"拉取失败: {e}")
            raise

        messages = resp.get("messages", [])
        sync = resp.get("sync", {})
        total_pulled += len(messages)
        all_chatlab_messages.extend(messages)

        if task:
            task.update("pending",
                        f"拉取第 {batch} 批 ({len(messages)} 条)...",
                        progress={"current": total_pulled, "total": 0})

        logger.info(f"[WeFlow Sync] 第 {batch} 批: {len(messages)} 条, "
                     f"hasMore={sync.get('hasMore')}, offset={offset}, total={total_pulled}")

        if not sync.get("hasMore"):
            break

        offset = sync.get("nextOffset", offset + 5000)
        # 安全上限：避免无限循环（180K 消息 36 批）
        if batch > 200:
            logger.warning(f"[WeFlow Sync] 超过 200 批（{total_pulled} 条），强制停止")
            break

    if not all_chatlab_messages:
        logger.info(f"[WeFlow Sync] {group['name']}: 没有新消息")
        if task:
            task.update("done", "同步完成，无新消息")
        return {"added": 0, "skipped": 0, "total_pulled": 0,
                "new_date_range_end": ""}

    # 3. 获取群成员（用于成员表更新）
    try:
        member_resp = client.get_group_members(chatroom_id)
        weflow_members = member_resp.get("members", [])
    except Exception as e:
        logger.warning(f"[WeFlow Sync] 获取成员失败: {e}")
        weflow_members = []

    # 4. 过滤 + 格式转换
    analyzable = filter_analyzable(all_chatlab_messages)
    # 构建 ChatLab 数据用于转换
    chatlab_data = {
        "meta": {"name": group["name"], "groupId": chatroom_id},
        "members": resp.get("members", []),
        "messages": analyzable,
    }
    normalized = normalize_chatlab_to_parsed(chatlab_data)
    new_messages = normalized["messages"]
    new_senders = normalized["senders"]

    # 5. 合并去重
    existing_messages = []
    merged_path = _get_merged_data_path(group_id)

    # 优先从 merged_data.json 加载
    if merged_path and merged_path.exists():
        try:
            with open(merged_path, "r", encoding="utf-8") as f:
                existing_messages = json.load(f).get("messages", [])
            logger.debug(f"[WeFlow Sync] 已有消息来源=merged_data.json: {len(existing_messages)} 条")
        except Exception as e:
            logger.debug("读取已有合并数据失败: %s", e)

    # fallback: 从内存缓存加载
    if not existing_messages:
        try:
            from routers.groups import get_chat_cache
            chat = get_chat_cache(group_id)
            if chat and chat.messages:
                existing_messages = chat.messages
                logger.info(f"[WeFlow Sync] 已有消息来源=内存缓存: {len(existing_messages)} 条")
        except Exception as e:
            logger.debug("从缓存加载现有消息失败: %s", e)

    # 最后 fallback: 从原始上传文件加载（防止首次 WeFlow 同步覆盖原数据）
    if not existing_messages and group.get("file_path"):
        try:
            from services.parser import load_and_parse
            fp = Path(group["file_path"])
            if fp.exists():
                chat = load_and_parse(fp)
                if chat and chat.messages:
                    existing_messages = chat.messages
                    logger.info(f"[WeFlow Sync] 已有消息来源=原始文件: {len(existing_messages)} 条")
        except Exception as e:
            logger.debug("从原始文件加载消息失败: %s", e)

    if not existing_messages:
        logger.info(f"[WeFlow Sync] 无已有消息，本次将作为首次导入")

    merge_result = merge_chat_data(existing_messages, new_messages)
    added = merge_result["added"]
    skipped = merge_result["skipped"]

    logger.info(f"[WeFlow Sync] {group['name']}: 拉取 {total_pulled} 条, "
                f"过滤后 {len(new_messages)} 条, 新增 {len(added)} 条, "
                f"跳过 {skipped} 条")

    # 合并后类型分布（用于排查过滤/丢失问题）
    merged_for_stats = existing_messages + added
    type_counts = {}
    for m in merged_for_stats:
        t = m.get("type", "?")
        type_counts[t] = type_counts.get(t, 0) + 1
    logger.info(f"[WeFlow Sync] 合并后 {len(merged_for_stats)} 条, 类型分布: {type_counts}")

    if not added:
        if task:
            task.update("done", f"同步完成，无新消息 (已拉取 {total_pulled} 条，跳过 {skipped} 条重复)")
        return {"added": 0, "skipped": skipped, "total_pulled": total_pulled,
                "new_date_range_end": ""}

    # 6. 写入磁盘（原子写入）
    merged = existing_messages + added
    merged.sort(key=lambda m: m.get("createTime", 0))

    if merged_path:
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = merged_path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({
                    "session": {"nickname": group["name"], "wxid": chatroom_id,
                                "messageCount": len(merged)},
                    "senders": list({
                                       s["wxid"]: s for s in
                                       (new_senders + _load_existing_senders(merged_path))
                                   }.values()),
                    "messages": merged,
                }, f, ensure_ascii=False)
            tmp_path.replace(merged_path)
            logger.debug(f"merged_data.json 已写入: {len(merged)} 条消息")

            # pickle 缓存（下次启动加速）
            pickle_path = merged_path.with_suffix(".json.pickle")
            try:
                with open(pickle_path, "wb") as f:
                    pickle.dump({
                        "session": {"nickname": group["name"], "wxid": chatroom_id,
                                    "messageCount": len(merged)},
                        "senders": list({
                            s["wxid"]: s for s in
                            (new_senders + _load_existing_senders(merged_path))
                        }.values()),
                        "messages": merged,
                        "_by_date": None,
                    }, f, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception as e:
                logger.warning(f"pickle 缓存写入失败: {e}")
        except Exception as e:
            logger.error(f"写入 merged_data.json 失败: {e}")
            raise

    # 7. 更新 DB 元数据
    from models.database import get_conn
    dates = [m.get("formattedTime", "")[:10] for m in merged
             if m.get("formattedTime")]
    new_date_end = max(dates) if dates else ""

    if new_date_end:
        conn = None
        try:
            conn = get_conn()
            conn.execute(
                "UPDATE chat_groups SET message_count=?, date_range_end=MAX(COALESCE(date_range_end,''),?), "
                "date_range_start=CASE WHEN date_range_start IS NULL OR date_range_start='' THEN ? "
                "ELSE MIN(date_range_start, ?) END WHERE id=?",
                (len(merged), new_date_end, min(dates), min(dates), group_id)
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    # 更新成员表
    if weflow_members:
        senders_for_db = []
        for wm in weflow_members:
            senders_for_db.append({
                "senderID": 0,  # 不重要，upsert 会按 wxid 更新
                "wxid": wm.get("wxid", ""),
                "displayName": wm.get("groupNickname") or wm.get("nickname") or wm.get("remark") or wm.get("displayName") or "",
                "nickname": wm.get("nickname") or "",
                "remark": wm.get("remark") or "",
                "groupNickname": wm.get("groupNickname") or "",
                "avatar": wm.get("avatarUrl") or "",
            })
        upsert_members(group_id, senders_for_db)

    # 8. 清除内存缓存（下次请求时重新加载）
    try:
        from routers.groups import _chat_cache
        _chat_cache.pop(group_id, None)
    except Exception as e:
        logger.debug("清除内存缓存失败: %s", e)

    if task:
        task.finish(success=True,
                    step=f"同步完成：+{len(added)} 条新消息 (跳过 {skipped} 条重复)")

    return {
        "added": len(added),
        "skipped": skipped,
        "total_pulled": total_pulled,
        "new_date_range_end": new_date_end,
    }


def _load_existing_senders(merged_path: Path) -> list[dict]:
    """从已有 merged_data.json 加载 senders"""
    try:
        with open(merged_path, "r", encoding="utf-8") as f:
            return json.load(f).get("senders", [])
    except Exception as e:
        logger.debug("读取已有发送者列表失败: %s", e)
        return []


def link_group_to_weflow(group_id: int, chatroom_id: str,
                          client: WeFlowClient) -> dict:
    """关联已有群到 WeFlow 会话

    1. 更新 chat_groups.wxid（确保与 WeFlow session_id 一致）
    2. 从 WeFlow 拉取群成员，更新 DB
    """
    from models.database import get_conn, upsert_members

    # 更新群 wxid
    conn = None
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE chat_groups SET wxid=? WHERE id=?",
            (chatroom_id, group_id)
        )
        conn.commit()
    finally:
        if conn:
            conn.close()

    # 拉取并更新成员
    try:
        member_resp = client.get_group_members(chatroom_id)
        weflow_members = member_resp.get("members", [])
        senders = []
        for wm in weflow_members:
            senders.append({
                "senderID": 0,
                "wxid": wm.get("wxid", ""),
                "displayName": wm.get("groupNickname") or wm.get("nickname") or wm.get("remark") or wm.get("displayName") or "",
                "nickname": wm.get("nickname") or "",
                "remark": wm.get("remark") or "",
                "groupNickname": wm.get("groupNickname") or "",
                "avatar": wm.get("avatarUrl") or "",
            })
        upsert_members(group_id, senders)
        logger.info(f"[WeFlow Link] group_id={group_id} → {chatroom_id}, "
                    f"成员 {len(senders)} 人")
    except Exception as e:
        logger.warning(f"[WeFlow Link] 获取成员失败: {e}")

    return {"success": True, "group_id": group_id, "chatroom_id": chatroom_id}
