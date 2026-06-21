"""共享脱敏模块 — PII 过滤 + senderID↔昵称 还原

发送给 AI：senderID 数字（非实名）+ PII 过滤后的消息内容
AI 返回后：将 AI 输出中的 [senderID] 还原为昵称再存储

名称降级优先级：displayName → nickname → str(senderID)
"""

import re
import logging

logger = logging.getLogger(__name__)

# 敏感信息正则（隐私过滤）
# 注意：顺序很重要！更具体的模式必须放在前面，避免被宽泛模式误匹配
_PII_PATTERNS = [
    (re.compile(r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]'), '[身份证]'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[邮箱]'),
    (re.compile(r'1[3-9]\d{9}'), '[手机号]'),
    (re.compile(r'\d{3,4}-\d{7,8}'), '[电话号码]'),
]

# senderID → 昵称 替换正则
_SID_BRACKET = re.compile(r'\[(\d+)\]')   # [13]
_SID_HAO = re.compile(r'\b(\d+)号\b')      # 13号（中文语境常见）


def _resolve_all(text: str, name_map: dict[int, str]) -> str:
    """将文本中所有 [N]、N号 格式替换为昵称"""
    if not text or not name_map:
        return text

    def _by_bracket(match):
        sid = int(match.group(1))
        return name_map.get(sid, match.group(0))

    def _by_hao(match):
        sid = int(match.group(1))
        name = name_map.get(sid)
        return name if name else match.group(0)

    text = _SID_BRACKET.sub(_by_bracket, text)
    text = _SID_HAO.sub(_by_hao, text)
    return text


def filter_pii(content: str) -> str:
    """对单条消息内容做 PII 正则过滤"""
    if not content:
        return content
    for pattern, replacement in _PII_PATTERNS:
        content = pattern.sub(replacement, content)
    return content


def filter_pii_batch(messages: list[dict]) -> list[dict]:
    """批量过滤消息列表，原地修改 content 字段"""
    for m in messages:
        content = (m.get("content") or "").strip()
        if content:
            m["content"] = filter_pii(content)
    return messages


def build_sender_name_map(senders: list[dict]) -> dict[int, str]:
    """从 chat.senders 构建 {senderID: 显示名} 映射表

    降级优先级：displayName → nickname → str(senderID)
    注意：senderID 在 JSON 导入和 WeFlow 合并时可能变化，跨数据源不一致。
    如需稳定映射请用 build_stable_id_map。
    """
    name_map = {}
    for s in senders:
        sid = s.get("senderID", 0)
        if sid:
            name = s.get("displayName", "") or s.get("nickname", "") or str(sid)
            name_map[sid] = name
    return name_map


def build_wxid_to_stable_id(senders: list[dict]) -> dict[str, int]:
    """基于 wxid 排序生成 {wxid: stable_id} 映射（v1.18.5 权威实现）

    所有需要 wxid→stable_id 映射的代码（prompt 构建、摘要提取等）
    必须调用此函数，确保发信人编号全局一致。

    Returns:
        {wxid: stable_id}，stable_id 从 1 开始按 wxid 字母序编号
    """
    wxids = sorted(set(
        s.get("wxid", "") for s in senders if s.get("wxid", "")
    ))
    return {wxid: i for i, wxid in enumerate(wxids, 1)}


def build_stable_id_map(senders: list[dict]) -> tuple[dict[str, int], dict[int, str]]:
    """基于 wxid 排序生成稳定的短数字 ID，确保跨数据源一致。

    解决 senderID 在 JSON 导入 vs WeFlow 合并时被重新分配导致的不稳定问题。
    wxid 是跨平台的唯一标识（如 wxid_xxx、u_xxx），排序后序号稳定。

    Returns:
        (wxid_to_stable: {wxid: stable_id}, stable_to_name: {stable_id: 显示名})
        降级优先级：displayName → nickname → str(stable_id)
    """
    # v1.18.5: 复用权威函数
    wxid_to_stable = build_wxid_to_stable_id(senders)

    # 构建 {wxid: name} 用于降级
    wxid_to_name = {}
    for s in senders:
        wxid = s.get("wxid", "")
        if wxid:
            name = s.get("displayName", "") or s.get("nickname", "") or ""
            if name:
                wxid_to_name[wxid] = name

    stable_to_name = {}
    for wxid, sid in wxid_to_stable.items():
        name = wxid_to_name.get(wxid, "") or wxid[:20]
        stable_to_name[sid] = name

    return wxid_to_stable, stable_to_name


def resolve_sender_ids(text: str, name_map: dict[int, str]) -> str:
    """将文本中的 [123]、123号 格式替换为对应昵称"""
    return _resolve_all(text, name_map)


def _try_resolve_digit(val: str, name_map: dict[int, str]) -> str:
    """如果 val 是纯数字字符串，映射为昵称；否则原样返回"""
    if isinstance(val, str) and val.strip().isdigit():
        sid = int(val.strip())
        return name_map.get(sid, val)
    return val


def resolve_sender_ids_deep(data, name_map: dict[int, str]):
    """递归遍历 dict/list/str，将所有 senderID 引用替换为昵称

    处理格式：[N]、N号、participant.name 裸数字、sender_id 字段、
    member_details 的 digit key、top5/night_owl_names 的 digit 列表项。
    """
    if not name_map:
        return data
    if isinstance(data, str):
        return _try_resolve_digit(_resolve_all(data, name_map), name_map)
    if isinstance(data, dict):
        # 处理 sender_id / name 等字段的值（裸数字 → 昵称）
        for key in ("sender_id", "name", "alias"):
            if key in data and isinstance(data[key], str):
                data[key] = _try_resolve_digit(
                    _resolve_all(data[key], name_map), name_map)
        # 递归处理所有键值，同时处理 digit key 的映射
        result = {}
        for k, v in data.items():
            new_key = _try_resolve_digit(k, name_map) if isinstance(k, str) else k
            result[new_key] = resolve_sender_ids_deep(v, name_map)
        return result
    if isinstance(data, list):
        return [resolve_sender_ids_deep(item, name_map) for item in data]
    return data


def build_meme_prefix(group_id: int) -> str:
    """构建梗百科注入前缀。仅取已审核通过的梗。群无梗时返回空字符串。"""
    try:
        from models.database import get_group_memes
        # v1.18.8: 只取 approved，pending/rejected 不参与报告注入
        memes = get_group_memes(group_id, status="approved")
        if not memes:
            return ""
        lines = ["【群梗百科】以下为群内约定俗成的表达，供你理解消息上下文："]
        for m in memes:
            t = (m.get("term") or "").strip()
            d = (m.get("description") or "").strip()
            if t and d:
                lines.append(f'- "{t}"：{d}')
        return "\n".join(lines) + "\n" if len(lines) > 1 else ""
    except Exception:
        return ""
