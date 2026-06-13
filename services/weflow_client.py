"""
WeFlow HTTP API 客户端
封装 ChatLab Pull 格式的核心接口
"""
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# WCDB 消息类型 → chat-miner 中文类型名
WECHAT_TYPE_MAP = {
    0: "文本消息",
    1: "图片消息",
    3: "表情消息",
    5: "语音消息",
    8: "文件消息",
    24: "引用消息",
    25: "引用消息",
    34: "语音消息",
    43: "视频消息",
    47: "表情消息",
    49: "引用消息",   # 小程序/链接/引用回复
    80: "系统消息",
    99: "系统消息",
    10000: "系统消息",
    # 复合类型（本地有 localType 字段的场景，用于标准 API 的 localType 映射）
    244813135921: "引用消息",
}


class WeFlowClient:
    """WeFlow HTTP API 客户端"""

    def __init__(self, base_url: str = "http://127.0.0.1:5031",
                 access_token: str = "", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "chat-miner/1.0",
        })

    def _get(self, path: str, params: dict = None) -> dict:
        """GET 请求，自动处理错误"""
        url = f"{self.base_url}{path}"
        if params is None:
            params = {}
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise WeFlowError(f"无法连接 WeFlow ({self.base_url})，请确认 WeFlow 正在运行")
        except requests.exceptions.Timeout:
            raise WeFlowError(f"WeFlow 请求超时 ({url})")
        except requests.exceptions.HTTPError as e:
            raise WeFlowError(f"WeFlow HTTP {e.response.status_code}: {url}")
        except Exception as e:
            raise WeFlowError(f"WeFlow 请求失败: {e}")

    # ---- 健康检查 ----

    def health_check(self) -> bool:
        """检查 WeFlow 是否可用"""
        try:
            data = self._get("/health")
            return data.get("status") == "ok"
        except Exception:
            return False

    # ---- 会话列表 ----

    def list_sessions(self, keyword: str = "", limit: int = 200,
                      format: str = "chatlab") -> list[dict]:
        """获取会话列表（ChatLab 格式）"""
        params = {"limit": limit, "format": format}
        if keyword:
            params["keyword"] = keyword
        data = self._get("/api/v1/sessions", params)
        return data.get("sessions", [])

    # ---- ChatLab Pull 消息拉取 ----

    def get_session_messages(self, session_id: str, limit: int = 5000,
                              since: int = 0, offset: int = 0) -> dict:
        """拉取会话消息（ChatLab Pull 格式）

        Args:
            session_id: 会话 ID，群聊为 xxx@chatroom
            limit: 单次返回上限，默认 5000（最大值）
            since: 秒级时间戳，仅返回此时间之后的消息
            offset: 分页偏移

        Returns:
            ChatLab 格式: {meta, members, messages, sync}
        """
        params = {"limit": limit, "since": since, "offset": offset}
        return self._get(f"/api/v1/sessions/{session_id}/messages", params)

    # ---- 群成员 ----

    def get_group_members(self, chatroom_id: str,
                           include_counts: bool = True,
                           force_refresh: bool = False) -> dict:
        """获取群成员列表

        Returns:
            {success, chatroomId, count, members: [{wxid, displayName, ...}]}
        """
        params = {"chatroomId": chatroom_id}
        if include_counts:
            params["includeMessageCounts"] = "1"
        if force_refresh:
            params["forceRefresh"] = "1"
        return self._get("/api/v1/group-members", params)

    # ---- 标准消息 API（备用） ----

    def get_messages(self, talker: str, limit: int = 100,
                      start: str = "", end: str = "") -> dict:
        """获取消息（标准 JSON API，备用）

        Args:
            start/end: YYYYMMDD 或时间戳
        """
        params = {"talker": talker, "limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self._get("/api/v1/messages", params)

    def close(self):
        """关闭会话"""
        self._session.close()


class WeFlowError(Exception):
    """WeFlow 客户端异常"""
    pass
