"""
消息解析模块：JSON 文件解析 + 按天分块 + 数据合并
处理微信聊天记录导出的 JSON 格式
"""
import json
import re
import io
import logging
import zipfile
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

# 有文本内容的消息类型
TEXT_TYPES = {"文本消息", "引用消息", "视频消息"}
# 画像分析专用：只用纯文本消息，排除引用（引用内容是别人的话）
PORTRAIT_TEXT_TYPES = {"文本消息"}
# 无文本但可统计的类型
STAT_TYPES = {"图片消息", "表情消息", "语音消息", "文件消息", "位置消息",
              "视频消息", "名片消息", "小程序消息", "系统消息", "聊天记录",
              "语音记录", "红包消息"}


# 消息中只需保留这些字段（其他 6 个字段解析后即无用，删掉省内存）
_KEEP_MESSAGE_KEYS = {"wxid", "senderID", "createTime", "formattedTime", "type", "content"}

def _trim_message_fields(messages: list[dict]):
    """删除消息中下游不需要的字段，节省 ~40MB 内存（180K 条消息）"""
    removed = 0
    for m in messages:
        for key in list(m.keys()):
            if key not in _KEEP_MESSAGE_KEYS:
                del m[key]
                removed += 1
    if removed:
        logger.info(f"消息字段精简: 删除 {removed} 个无用字段 (保留 {_KEEP_MESSAGE_KEYS})")


# ---- QQ 聊天记录格式适配 (v0.8) ----
# QQChatExporter V5 导出 JSON 与微信格式完全不同，在 load() 入口归一化

_QQ_TYPE_MAP = {
    # Single-JSON 格式 (v0.8, QQChatExporter V5 私聊导出)
    "type_1": "文本消息",    # 文本消息（图片/表情内嵌在 elements 中）
    "type_3": "引用消息",    # 引用回复
    "type_7": "系统消息",    # JSON/卡片/小程序消息
    "type_8": "文件消息",    # 文件
    "type_9": "视频消息",    # 视频
    "type_11": "聊天记录",   # 合并转发
    # type_21/27/31 等未知类型 → 系统消息（default）
    # Chunked-JSONL 格式 (v0.8.2, QQChatExporter V5 群聊导出)
    "text": "文本消息",
    "reply": "引用消息",
    "system": "系统消息",
    "forward": "聊天记录",
    "video": "视频消息",
    "json": "系统消息",
    "file": "文件消息",
}


def _detect_qq_format(raw: dict) -> bool:
    """检测是否为 QQChatExporter V5 导出的 JSON 格式

    微信 JSON 顶层为 session + senders + messages，
    QQ JSON 顶层为 metadata + chatInfo + messages，两者互斥。
    """
    return (
        isinstance(raw, dict)
        and "metadata" in raw
        and "chatInfo" in raw
        and "QQChatExporter" in raw.get("metadata", {}).get("name", "")
    )


def _normalize_qq(raw: dict) -> tuple[dict, list[dict], list[dict]]:
    """将 QQ JSON 归一化为微信格式 (session, senders, messages)

    分三步：构建 session → 从消息去重提取 senders → 逐条转换消息
    """
    chat_info = raw["chatInfo"]
    stats = raw.get("statistics", {})
    qq_messages = raw.get("messages", [])

    # Step 1: 构建 session
    if chat_info.get("type") == "private":
        # 私聊：双方 UID 拼接作为群标识（确定性唯一）
        all_uids = sorted(set(
            m.get("sender", {}).get("uid", "")
            for m in qq_messages
            if m.get("sender", {}).get("uid")
        ))
        group_wxid = "_".join(all_uids)
    else:
        group_wxid = chat_info.get("groupUid") or chat_info.get("selfUid") or ""

    session = {
        "nickname": chat_info.get("name", ""),
        "wxid": group_wxid,
        "messageCount": stats.get("totalMessages", len(qq_messages)),
    }

    # Step 2: 构建 senders（从消息中提取去重 UID，按首次出现顺序分配 senderID）
    uid_to_sid: dict[str, int] = {}
    sid_to_info: dict[int, dict] = {}
    next_sid = 1

    for m in qq_messages:
        sender = m.get("sender", {})
        uid = sender.get("uid", "")
        if not uid or uid in uid_to_sid:
            continue
        uid_to_sid[uid] = next_sid
        uin = sender.get("uin", "")
        sid_to_info[next_sid] = {
            "senderID": next_sid,
            "wxid": uid,
            "displayName": sender.get("remark") or sender.get("groupCard") or sender.get("name") or sender.get("nickname") or "",
            "nickname": sender.get("nickname") or "",
            "uin": uin,
        }
        next_sid += 1

    # Step 2.5: 从 avatars 字典匹配头像（key 为 uin/QQ号）
    avatars = raw.get("avatars", {})
    if avatars:
        for info in sid_to_info.values():
            uin = info.get("uin", "")
            if uin and uin in avatars:
                info["avatar"] = avatars[uin]

    senders = list(sid_to_info.values())

    # Step 3: 转换消息
    messages = []
    for m in qq_messages:
        # 跳过撤回消息和系统消息
        if m.get("recalled"):
            continue
        if m.get("system"):
            continue

        sender = m.get("sender", {})
        uid = sender.get("uid", "")
        sid = uid_to_sid.get(uid, 0)

        qq_type = m.get("type", "")
        internal_type = _QQ_TYPE_MAP.get(qq_type, "系统消息")

        content_text = (m.get("content", {}).get("text") or "").strip()
        # 无文本内容的消息（纯图片/文件等）跳过，不参与 AI 分析
        if not content_text:
            continue

        messages.append({
            "wxid": uid,
            "senderID": sid,
            "createTime": m.get("timestamp", 0) // 1000,   # 毫秒 → 秒
            "formattedTime": m.get("time", ""),
            "type": internal_type,
            "content": content_text,
            "platformMessageId": m.get("id", ""),
        })

    # 按时间排序
    messages.sort(key=lambda x: x.get("createTime", 0))

    return session, senders, messages


# ---- QQ 群聊 chunked-jsonl 格式适配 (v0.8.2) ----
# QQChatExporter V5 群聊导出为 ZIP 包，内含 manifest.json + JSONL 分块消息文件

def _detect_qq_chunked(file_path: Path) -> bool:
    """检测是否为 QQChatExporter V5 chunked-jsonl 格式（群聊导出 ZIP）

    特征：
    1. 文件扩展名为 .zip
    2. ZIP 内包含 manifest.json
    3. manifest.json 的 metadata.name 包含 "QQChatExporter"
    """
    if file_path.suffix.lower() != ".zip":
        return False
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            # 查找 manifest.json（可能在一层子目录下）
            for name in zf.namelist():
                if name.endswith("/manifest.json") or name == "manifest.json":
                    manifest_bytes = zf.read(name)
                    manifest = json.loads(manifest_bytes.decode("utf-8"))
                    meta = manifest.get("metadata", {})
                    return "QQChatExporter" in meta.get("name", "")
            return False
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
        return False


def _normalize_qq_chunked(file_path: Path) -> tuple[dict, list[dict], list[dict]]:
    """将 QQ chunked-jsonl ZIP 归一化为微信格式 (session, senders, messages)

    流程：解压ZIP → 读 manifest.json → 读各 chunk JSONL → 逐条转换消息
    """
    with zipfile.ZipFile(file_path, "r") as zf:
        namelist = zf.namelist()

        # 1. 找 manifest.json
        manifest_path = None
        for name in namelist:
            if name.endswith("/manifest.json") or name == "manifest.json":
                manifest_path = name
                break
        if not manifest_path:
            raise ValueError("ZIP 中未找到 manifest.json")

        manifest = json.loads(zf.read(manifest_path).decode("utf-8"))
        logger.info(f"QQ chunked-jsonl manifest: {manifest_path}")

        # 确定 base_dir（manifest 所在的目录层级）
        base_dir = manifest_path.rsplit("/", 1)[0] + "/" if "/" in manifest_path else ""

        # 2. 读取 chunk 文件列表
        chunk_info = manifest.get("chunked", {})
        chunks_dir = chunk_info.get("chunksDir", "chunks")
        chunk_files = [c["relativePath"] for c in chunk_info.get("chunks", [])]

        # 如果 manifest 没列 chunk（兼容），则自动扫描
        if not chunk_files:
            chunk_prefix = f"{base_dir}{chunks_dir}/"
            chunk_files = sorted(
                n for n in namelist
                if n.startswith(chunk_prefix) and n.endswith(".jsonl")
            )
            logger.info(f"manifest 未列 chunk，自动扫描到 {len(chunk_files)} 个文件")

        chat_info = manifest.get("chatInfo", {})
        stats = manifest.get("statistics", {})

        # 3. 构建 session
        if chat_info.get("type") == "group":
            # 群聊：从目录名提取群号作为 wxid
            # 目录名格式: group_{群号}_{timestamp}_chunked_jsonl
            dir_name = base_dir.strip("/")
            group_code = ""
            m = re.search(r"group_(\d+)", dir_name)
            if m:
                group_code = m.group(1)
            group_wxid = group_code or chat_info.get("selfUid") or ""
        else:
            # 按理说 chunked-jsonl 只用于群聊，但保持兼容
            group_wxid = chat_info.get("selfUid") or ""

        session = {
            "nickname": chat_info.get("name", ""),
            "wxid": group_wxid,
            "messageCount": stats.get("totalMessages", 0),
        }

        # 4. 逐 chunk 读取消息（JSONL 格式），一边读一边构建 senders
        uid_to_sid: dict[str, int] = {}
        sid_to_info: dict[int, dict] = {}
        next_sid = 1
        all_messages: list[dict] = []

        for chunk_rel_path in chunk_files:
            # 兼容：chunk 路径可能带或不带 base_dir
            possible_paths = [chunk_rel_path]
            if base_dir and not chunk_rel_path.startswith(base_dir):
                possible_paths.insert(0, base_dir + chunk_rel_path)

            chunk_data = None
            for path in possible_paths:
                try:
                    chunk_data = zf.read(path).decode("utf-8")
                    break
                except KeyError:
                    continue
            if chunk_data is None:
                logger.warning(f"chunk 文件未找到: {chunk_rel_path}")
                continue

            # 逐行解析 JSONL
            for line in chunk_data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"JSONL 解析失败: {line[:100]}...")
                    continue

                # 跳过撤回消息和纯系统消息
                if m.get("recalled"):
                    continue
                if m.get("system"):
                    continue

                sender = m.get("sender", {})
                uid = sender.get("uid", "")
                if not uid:
                    continue

                # 构建 sender（首次遇到时登记）
                if uid not in uid_to_sid:
                    uid_to_sid[uid] = next_sid
                    uin = sender.get("uin", "")
                    sid_to_info[next_sid] = {
                        "senderID": next_sid,
                        "wxid": uid,
                        "displayName": (
                            sender.get("remark")
                            or sender.get("groupCard")
                            or sender.get("name")
                            or sender.get("nickname")
                            or ""
                        ),
                        "nickname": sender.get("nickname") or "",
                        "uin": uin,
                    }
                    next_sid += 1

                sid = uid_to_sid[uid]
                qq_type = m.get("type", "")
                internal_type = _QQ_TYPE_MAP.get(qq_type, "系统消息")

                content_text = (m.get("content", {}).get("text") or "").strip()
                # 无文本内容的消息（纯图片/文件/视频占位符）跳过
                if not content_text:
                    continue

                all_messages.append({
                    "wxid": uid,
                    "senderID": sid,
                    "createTime": m.get("timestamp", 0) // 1000,   # 毫秒 → 秒
                    "formattedTime": m.get("time", ""),
                    "type": internal_type,
                    "content": content_text,
                    "platformMessageId": m.get("id", ""),
                })

    # 按时间排序
    all_messages.sort(key=lambda x: x.get("createTime", 0))

    # 头像匹配：优先 manifest.avatars，其次 ZIP 内 avatars.json
    chunked_avatars = manifest.get("avatars", {})
    if not chunked_avatars:
        for name in namelist:
            if name.endswith("/avatars.json") or name == "avatars.json":
                try:
                    chunked_avatars = json.loads(zf.read(name).decode("utf-8"))
                    if isinstance(chunked_avatars, dict):
                        logger.info(f"从 {name} 加载了 {len(chunked_avatars)} 个头像")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                break
    if chunked_avatars:
        for info in sid_to_info.values():
            uin = info.get("uin", "")
            if uin and uin in chunked_avatars:
                info["avatar"] = chunked_avatars[uin]

    senders = list(sid_to_info.values())
    logger.info(f"QQ chunked-jsonl 解析完成: 群={session['nickname']}, "
                f"消息={len(all_messages)}, 成员={len(senders)}, "
                f"chunks={len(chunk_files)}")

    return session, senders, all_messages


class ParsedChat:
    """解析后的群聊数据"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.raw: dict = {}
        self.session: dict = {}
        self.senders: list[dict] = []
        self.messages: list[dict] = []
        self._by_date: Optional[dict[str, list[dict]]] = None

    @property
    def _pickle_path(self) -> Path:
        """pickle 缓存路径：<json_path>.pickle"""
        return self.file_path.with_suffix(self.file_path.suffix + ".pickle")

    def load(self):
        """加载并解析 JSON 文件，优先使用 pickle 缓存避免重复解析

        pickle 缓存加载速度比 JSON 解析快 10-50x，对于 75MB JSON 文件效果显著。
        只在 JSON 文件更新时重新解析（比对 mtime）。
        """
        import pickle
        json_mtime = self.file_path.stat().st_mtime

        # 尝试从 pickle 缓存加载
        if self._pickle_path.exists():
            try:
                pickle_mtime = self._pickle_path.stat().st_mtime
                if pickle_mtime >= json_mtime:
                    logger.debug(f"pickle 缓存命中: {self._pickle_path} "
                                f"({self._pickle_path.stat().st_size / 1024 / 1024:.1f} MB)")
                    with open(self._pickle_path, "rb") as f:
                        data = pickle.load(f)
                    self.session = data["session"]
                    self.senders = data["senders"]
                    self.messages = data["messages"]
                    self._by_date = data.get("_by_date")
                    # 兼容旧 pickle（可能还有多余字段）
                    _trim_message_fields(self.messages)
                    logger.debug(f"pickle 加载完成: 群={self.group_name}, "
                                f"消息={len(self.messages)}, 成员={len(self.senders)}")
                    return self
            except Exception as e:
                logger.warning(f"pickle 缓存损坏或版本不兼容，重新解析JSON: {e}")

        # 回退：从 JSON 完整解析
        # QQ chunked-jsonl 格式检测（v0.8.2，群聊 ZIP 导出）
        if self.file_path.suffix.lower() == ".zip":
            if _detect_qq_chunked(self.file_path):
                self.session, self.senders, self.messages = _normalize_qq_chunked(self.file_path)
                _trim_message_fields(self.messages)
                logger.info(f"QQ chunked-jsonl 解析完成: 群={self.group_name}, "
                            f"消息={len(self.messages)}, 成员={len(self.senders)}")
                # 写入 pickle 缓存
                try:
                    with open(self._pickle_path, "wb") as f:
                        pickle.dump({
                            "session": self.session,
                            "senders": self.senders,
                            "messages": self.messages,
                            "_by_date": self._by_date,
                        }, f, protocol=pickle.HIGHEST_PROTOCOL)
                    logger.debug(f"pickle 缓存已保存: {self._pickle_path} "
                                f"({self._pickle_path.stat().st_size / 1024 / 1024:.1f} MB)")
                except Exception as e:
                    logger.warning(f"保存 pickle 缓存失败: {e}")
                return self
            else:
                raise ValueError("不支持的 ZIP 文件格式，请上传 QQChatExporter V5 导出的群聊 ZIP 文件")

        logger.debug(f"JSON 解析: {self.file_path} ({self.file_path.stat().st_size / 1024 / 1024:.1f} MB)")
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.raw = json.load(f)

        # QQ 格式检测与归一化（v0.8）
        if _detect_qq_format(self.raw):
            self.session, self.senders, self.messages = _normalize_qq(self.raw)
            _trim_message_fields(self.messages)
            logger.info(f"QQ JSON 解析完成: 群={self.group_name}, "
                        f"消息={len(self.messages)}, 成员={len(self.senders)}")
            # 写入 pickle 缓存
            try:
                with open(self._pickle_path, "wb") as f:
                    pickle.dump({
                        "session": self.session,
                        "senders": self.senders,
                        "messages": self.messages,
                        "_by_date": self._by_date,
                    }, f, protocol=pickle.HIGHEST_PROTOCOL)
                logger.debug(f"pickle 缓存已保存: {self._pickle_path} "
                            f"({self._pickle_path.stat().st_size / 1024 / 1024:.1f} MB)")
            except Exception as e:
                logger.warning(f"保存 pickle 缓存失败: {e}")
            return self

        # ---- 微信格式解析 ----
        self.session = self.raw.get("session", {})
        self.senders = self.raw.get("senders", [])

        # 构建 senderID → (wxid, name) 映射
        sid_to_wxid: dict[int, str] = {}
        for s in self.senders:
            sid = s.get("senderID", 0)
            wxid = s.get("wxid", "") or f"unknown_{sid}"
            sid_to_wxid[sid] = wxid

        # 给每条消息注入 wxid（已有合法 wxid 则跳过，防止覆盖）
        self.messages = self.raw.get("messages", [])
        for m in self.messages:
            existing = m.get("wxid", "")
            if existing and not existing.startswith("unknown_"):
                continue  # 已有合法 wxid（如 merged_data.json 重加载场景）
            sid = m.get("senderID", 0)
            m["wxid"] = sid_to_wxid.get(sid, existing or f"unknown_{sid}")

        # 按时间排序
        self.messages.sort(key=lambda m: m.get("createTime", 0))

        # 删除解析后不再使用的字段，节省 ~40MB 内存（180K条消息×6字段）
        _trim_message_fields(self.messages)

        logger.debug(f"JSON 解析完成: 群={self.group_name}, 消息={len(self.messages)}, 成员={len(self.senders)}")

        # 写入 pickle 缓存（异步不阻塞，下次启动受益）
        try:
            with open(self._pickle_path, "wb") as f:
                pickle.dump({
                    "session": self.session,
                    "senders": self.senders,
                    "messages": self.messages,
                    "_by_date": self._by_date,
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.debug(f"pickle 缓存已保存: {self._pickle_path} "
                        f"({self._pickle_path.stat().st_size / 1024 / 1024:.1f} MB)")
        except Exception as e:
            logger.warning(f"保存 pickle 缓存失败: {e}")

        return self

    @property
    def group_name(self) -> str:
        return self.session.get("nickname", "") or self.session.get("displayName", "")

    @property
    def group_wxid(self) -> str:
        return self.session.get("wxid", "")

    @property
    def message_count(self) -> int:
        return self.session.get("messageCount", len(self.messages))

    def get_date_range(self) -> tuple[str, str]:
        """返回数据的日期范围 (start, end)"""
        dates = [m.get("formattedTime", "")[:10] for m in self.messages if m.get("formattedTime")]
        if not dates:
            return ("", "")
        return (min(dates), max(dates))

    def chunk_by_date(self) -> dict[str, list[dict]]:
        """按天分块：将消息按 formattedTime 的日期分组"""
        if self._by_date is not None:
            return self._by_date

        chunks: dict[str, list[dict]] = defaultdict(list)
        for msg in self.messages:
            ft = msg.get("formattedTime", "")
            if ft:
                date = ft[:10]  # "2025-09-01"
                chunks[date].append(msg)

        self._by_date = dict(sorted(chunks.items()))
        return self._by_date

    def get_text_messages_for_date(self, date: str) -> list[dict]:
        """获取某天的文本消息（用于日报分析，包含引用消息）"""
        day_msgs = self.chunk_by_date().get(date, [])
        return [m for m in day_msgs if m.get("type") in TEXT_TYPES and (m.get("content") or "").strip()]

    def get_portrait_messages_for_date(self, date: str) -> list[dict]:
        """获取某天的文本消息（用于画像分析，排除引用消息避免污染）"""
        day_msgs = self.chunk_by_date().get(date, [])
        return [m for m in day_msgs if m.get("type") in PORTRAIT_TEXT_TYPES and (m.get("content") or "").strip()]

    def get_analysis_messages(self, date: str, msg_types: set = None) -> list[dict]:
        """获取某天用于 AI 分析的消息（自动过滤 / 开头的游戏指令）"""
        if msg_types is None:
            msg_types = TEXT_TYPES
        day_msgs = self.chunk_by_date().get(date, [])
        return [
            m for m in day_msgs
            if m.get("type") in msg_types
            and (m.get("content") or "").strip()
            and not is_game_command(m.get("content", ""))
        ]

    def get_sender_name(self, sender_id: int) -> str:
        """通过 senderID 获取显示名（兼容旧代码）"""
        for s in self.senders:
            if s.get("senderID") == sender_id:
                return s.get("displayName", "") or s.get("nickname", "") or str(sender_id)
        return str(sender_id)

    def get_name_by_wxid(self, wxid: str) -> str:
        """通过 wxid 获取显示名"""
        for s in self.senders:
            sid = s.get("senderID", 0)
            swxid = s.get("wxid", "") or f"unknown_{sid}"
            if swxid == wxid:
                return s.get("displayName", "") or s.get("nickname", "") or wxid
        return wxid

    def all_dates(self) -> list[str]:
        """返回所有有消息的日期，降序"""
        return sorted(self.chunk_by_date().keys(), reverse=True)

    def stats_for_date(self, date: str) -> dict:
        """某天的基本统计（纯 Python，不调 AI）"""
        day_msgs = self.chunk_by_date().get(date, [])
        text_msgs = [m for m in day_msgs if m.get("type") in TEXT_TYPES and (m.get("content") or "").strip()]
        senders_set = {m.get("wxid") for m in day_msgs}

        # 消息类型分布
        type_counts = defaultdict(int)
        for m in day_msgs:
            type_counts[m.get("type", "未知")] += 1

        # 活跃时段
        hour_counts = defaultdict(int)
        for m in day_msgs:
            ft = m.get("formattedTime", "")
            if len(ft) >= 13:
                hour = ft[11:13]
                hour_counts[hour] += 1

        return {
            "date": date,
            "total_messages": len(day_msgs),
            "text_messages": len(text_msgs),
            "active_members": len(senders_set),
            "type_distribution": dict(type_counts),
            "hourly_distribution": {h: hour_counts.get(h, 0) for h in
                                    [f"{i:02d}" for i in range(24)]},
        }

    def sender_message_counts(self) -> dict[str, int]:
        """每个发送者（按wxid）的消息总数"""
        from collections import Counter
        return Counter(m.get("wxid") for m in self.messages)

    def sender_text_counts(self) -> dict[str, int]:
        """每个发送者（按wxid）的文本消息数"""
        from collections import Counter
        return Counter(
            m.get("wxid") for m in self.messages
            if m.get("type") in TEXT_TYPES and (m.get("content") or "").strip()
        )


def load_and_parse(file_path: Path) -> ParsedChat:
    """便捷函数：加载并解析文件"""
    return ParsedChat(file_path).load()


def merge_chat_data(existing_messages: list[dict],
                     new_messages: list[dict]) -> dict:
    """合并新导入的消息到已有数据中

    按 platformMessageId 去重，只保留新增的消息。
    如果消息没有 platformMessageId（老格式），则按 (createTime, senderID, content) 去重。

    Args:
        existing_messages: 已有的消息列表
        new_messages: 新导入的消息列表

    Returns:
        {
            "added": [新消息列表],
            "skipped": 跳过的重复消息数,
            "total_new": 新 JSON 中的消息总数
        }
    """
    # 构建已有消息的去重索引
    seen_ids = set()
    seen_fingerprints = set()
    for m in existing_messages:
        pid = m.get("platformMessageId", "")
        if pid:
            seen_ids.add(pid)
        else:
            # 老格式：用 (createTime, senderID, content[:50]) 作为指纹
            fp = (m.get("createTime", 0), m.get("senderID", 0),
                  (m.get("content") or "")[:50])
            seen_fingerprints.add(fp)

    added = []
    skipped = 0
    for m in new_messages:
        pid = m.get("platformMessageId", "")
        if pid and pid in seen_ids:
            skipped += 1
            continue
        if not pid:
            fp = (m.get("createTime", 0), m.get("senderID", 0),
                  (m.get("content") or "")[:50])
            if fp in seen_fingerprints:
                skipped += 1
                continue
            seen_fingerprints.add(fp)
        else:
            seen_ids.add(pid)
        added.append(m)

    logger.info(f"合并结果: {len(new_messages)} 条新消息中, 新增 {len(added)} 条, 跳过 {skipped} 条重复")
    return {
        "added": added,
        "skipped": skipped,
        "total_new": len(new_messages),
    }


# ---- 鱼塘游戏指令过滤 (v0.9) ----

def is_game_command(content: str) -> bool:
    """判断消息是否为鱼塘游戏指令（以 / 开头），这些消息不参与 AI 分析"""
    return (content or "").strip().startswith('/')


# ---- Token 估算 ----

def estimate_tokens(text: str) -> int:
    """简单估算 token 数（中文约 1 字符=1.5 token，英文约 4 字符=1 token）"""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.3)


def _has_meaningful_content(content: str, min_chinese_chars: int = 2) -> bool:
    """检查内容是否有足够的中文语义（过滤纯数字/纯符号/纯确认消息）

    Args:
        content: 消息内容
        min_chinese_chars: 最少中文字符数

    Returns:
        True 如果值得送给 AI 分析
    """
    if not content:
        return False
    # 纯数字确认：1, 2, 123 等
    if content.strip().isdigit():
        return False
    # 纯英文确认：ok, OK, okk, OKK 等
    if re.match(r'^[a-zA-Z]{1,5}$', content.strip()):
        return False
    # 至少要有几个中文字符才有分析价值
    chinese_count = len(re.findall(r'[一-鿿]', content))
    return chinese_count >= min_chinese_chars


def strip_mention_from_content(content: str, member_names: set[str] = None) -> str:
    """从单条消息内容中移除 @mention 文本

    处理：
    1. 显式 @：如 "@张三 你好" → "你好"
    2. 消息开头直接出现群友名字（回复/mention 格式）
    """
    if not content or not member_names:
        return content

    text = content.strip()

    # 1. 移除 "@名字" 模式
    text = re.sub(r'[@＠]\s*([^\s]{2,10})', '', text)

    # 2. 移除消息开头的群友名字（回复格式："张三 你说的对" → "你说的对"）
    for name in sorted(member_names, key=len, reverse=True):
        if text.startswith(name) and len(name) >= 3:
            rest = text[len(name):]
            if not rest or rest[0] in ' 　，。！？、：；""''）)】」:：\n':
                text = rest.lstrip(' 　，。！？、：；""''）)】」:：\n')
                break

    return text.strip()


def build_member_name_set(messages: list[dict], senders: list[dict] = None) -> set[str]:
    """从消息的 wxid + senders 列表中提取所有群成员名字，用于 @mention 过滤"""
    if not senders:
        return set()
    # 构建 wxid → name 映射
    wxid_to_name = {}
    for s in senders:
        wxid = s.get("wxid", "") or f"unknown_{s.get('senderID', 0)}"
        name = s.get("displayName", "") or s.get("nickname", "") or ""
        if name and len(name) >= 2:
            wxid_to_name[wxid] = name
    # 从消息中收集出现过的 wxid 对应的名字
    names = set()
    seen_wxids = set()
    for m in messages:
        wxid = m.get("wxid", "")
        if wxid and wxid not in seen_wxids:
            seen_wxids.add(wxid)
            name = wxid_to_name.get(wxid, "")
            if name:
                names.add(name)
    return names


# 模型上下文窗口（安全阈值，留 20% 给 prompt 模板和输出）
_MODEL_CONTEXT_LIMITS = {
    "14b": 100_000,   # qwen2.5:14b → 128K 上下文
    "9b": 25_000,     # qwen3.5:9b → 32K 上下文
    "7b": 25_000,
    "8b": 25_000,
    "default": 50_000,
}


def get_model_token_limit(model: str = "") -> int:
    """根据模型名估算安全的输入 token 上限"""
    model_lower = model.lower()
    for key, limit in _MODEL_CONTEXT_LIMITS.items():
        if key in model_lower:
            return limit
    return _MODEL_CONTEXT_LIMITS["default"]


def format_messages_for_prompt(messages: list[dict],
                                get_sender_name,
                                max_chars: int = 50000,
                                model: str = "",
                                member_names: set[str] = None,
                                senders: list[dict] = None) -> str:
    """将消息列表格式化为 AI prompt 的聊天记录文本

    Args:
        messages: 消息列表
        get_sender_name: 获取发言人名称的函数
        max_chars: 最大字符数限制
        model: 模型名，用于根据上下文窗口调整截断阈值
        member_names: 群成员名字集合（用于剥离 @mention）
        senders: sender 列表（用于自动构建 member_names）
    """
    if model:
        token_limit = get_model_token_limit(model)
        effective_token_limit = int(token_limit * 0.7)
        char_limit = int(effective_token_limit / 1.5)
        max_chars = min(max_chars, char_limit)

    if member_names is None and senders:
        member_names = build_member_name_set(messages, senders)

    lines = []
    total = 0
    truncated = False

    for msg in messages:
        # 跳过引用消息：content 是被引用者的原文，sender 却是引用者 → 张冠李戴
        if msg.get("type") == "引用消息":
            continue
        time_str = msg.get("formattedTime", "")[11:16]  # "HH:MM"
        sender = get_sender_name(msg.get("senderID", 0))
        raw_content = (msg.get("content") or "").strip()
        if not raw_content:
            continue
        content = strip_mention_from_content(raw_content, member_names)
        if not content or not _has_meaningful_content(content):
            continue

        line = f"[{time_str}] {sender}: {content}"
        total += len(line)
        if total > max_chars:
            truncated = True
            break
        lines.append(line)

    result = "\n".join(lines)
    if truncated:
        result += f"\n\n... (消息过多，已截断至 {len(lines)} 条)"
    return result


def format_sender_messages_for_portrait(messages: list[dict],
                                          sender_name: str,
                                          max_chars: int = 30000,
                                          member_names: set[str] = None) -> str:
    """将某个成员的发言格式化为画像分析的 prompt

    Args:
        messages: 目标成员的消息列表
        sender_name: 发言人名称
        max_chars: 最大字符数
        member_names: 群成员名字集合（用于剥离 @mention）
    """
    lines = [f"{sender_name} 的发言记录：", "---"]
    total = 0
    truncated = False

    for msg in messages:
        time_str = msg.get("formattedTime", "")[:16]  # "2025-09-01 14:30"
        raw_content = (msg.get("content") or "").strip()
        if not raw_content:
            continue
        content = strip_mention_from_content(raw_content, member_names) if member_names else raw_content
        if not content or not _has_meaningful_content(content):
            continue

        line = f"[{time_str}] {content}"
        total += len(line)
        if total > max_chars:
            truncated = True
            break
        lines.append(line)

    result = "\n".join(lines)
    if truncated:
        result += f"\n\n... (发言过多，已截断至 {len(lines) - 2} 条)"
    return result


# ---- 上下文安全分块工具 (v0.5) ----

def chunk_messages_by_month(messages: list[dict],
                             get_sender_name,
                             max_chars_per_chunk: int = 3000) -> list[tuple[str, str]]:
    """按月分块发言，每块不超过 max_chars

    用于深度画像的月度切片分析：每个月的发言单独给 AI 做轻量分析

    Args:
        messages: 目标成员的消息列表（已过滤 senderID）
        get_sender_name: 获取发言人名称的函数
        max_chars_per_chunk: 每块最大字符数

    Returns:
        [(month_label, chunk_text)] 按月份升序
    """
    from collections import defaultdict

    # 按月分组
    by_month: dict[str, list[dict]] = defaultdict(list)
    for msg in messages:
        ft = msg.get("formattedTime", "")
        if len(ft) >= 7:
            month = ft[:7]  # "2025-01"
            by_month[month].append(msg)

    chunks = []
    for month in sorted(by_month.keys()):
        month_msgs = by_month[month]
        lines = [f"{month} 的发言：", "---"]
        total = 0
        truncated = False
        for msg in month_msgs:
            time_str = msg.get("formattedTime", "")[:16]
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            line = f"[{time_str}] {content}"
            total += len(line)
            if total > max_chars_per_chunk:
                truncated = True
                break
            lines.append(line)

        text = "\n".join(lines)
        if truncated:
            text += f"\n... (本月发言过多，已截断)"

        # 最少 3 条消息才值得分析
        if len(lines) > 3:
            chunks.append((month, text))

    return chunks


def extract_interaction_context(messages: list[dict],
                                 wxid_a: str,
                                 wxid_b: str,
                                 get_name_fn,
                                 max_chars: int = 1000,
                                 window_size: int = 10) -> str:
    """提取两个成员互动的上下文片段

    Args:
        messages: 全部消息列表（按时间排序）
        wxid_a: 成员 A 的 wxid
        wxid_b: 成员 B 的 wxid
        get_name_fn: wxid → 名字 的映射函数
        max_chars: 返回文本的最大字符数
        window_size: 以目标为中心扩展的窗口大小
    """
    all_msgs = sorted(messages, key=lambda m: m.get("createTime", 0))
    n = len(all_msgs)

    # 找两人先后发言的"接触点"
    contact_indices = set()
    for i, msg in enumerate(all_msgs):
        mwxid = msg.get("wxid", "")
        if mwxid != wxid_a and mwxid != wxid_b:
            continue
        ts = msg.get("createTime", 0)
        other_wxid = wxid_b if mwxid == wxid_a else wxid_a
        for j in range(max(0, i - 50), min(n, i + 50)):
            if j == i:
                continue
            other = all_msgs[j]
            if other.get("wxid") == other_wxid:
                if abs(other.get("createTime", 0) - ts) <= 300:
                    contact_indices.add(i)
                    contact_indices.add(j)

    if not contact_indices:
        return ""

    # 取接触点周围的窗口
    window_indices = set()
    for idx in contact_indices:
        for w in range(max(0, idx - window_size), min(n, idx + window_size + 1)):
            window_indices.add(w)

    sorted_indices = sorted(window_indices)

    # 格式化为文本
    lines = []
    total = 0
    for idx in sorted_indices:
        msg = all_msgs[idx]
        sender = get_name_fn(msg.get("wxid", ""))
        time_str = msg.get("formattedTime", "")[11:16]
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        line = f"[{time_str}] {sender}: {content}"
        total += len(line)
        if total > max_chars:
            break
        lines.append(line)

    return "\n".join(lines)

