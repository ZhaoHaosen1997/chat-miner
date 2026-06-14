"""
v1.4.1 版本更新检查 — GitHub 主源 + Gitee 备源
"""
import json
import urllib.request
import logging

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/repos/ZhaoHaosen1997/chat-miner/releases/latest"
GITEE_API  = "https://gitee.com/api/v5/repos/ZhaoHaosen1997/chat-miner/releases/latest"
TIMEOUT = 5


class UpdateResult:
    def __init__(self, has_update: bool = False, latest: str = "",
                 current: str = "", url: str = "", error: str = ""):
        self.has_update = has_update
        self.latest = latest
        self.current = current
        self.url = url
        self.error = error


def check_update(current_version: str, custom_url: str = "") -> UpdateResult:
    """检查更新，返回 UpdateResult。先 GitHub，失败则 Gitee。"""
    urls = [GITHUB_API, GITEE_API]
    if custom_url:
        urls.insert(0, custom_url)

    for url in urls:
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "chat-miner-updater/1.0")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest = str(data.get("tag_name", "")).lstrip("v")
                release_url = data.get("html_url", "")
                if not latest:
                    continue
                has = _compare_versions(latest, current_version)
                return UpdateResult(
                    has_update=has, latest=f"v{latest}",
                    current=f"v{current_version}", url=release_url)
        except Exception as e:
            logger.debug(f"更新检查失败 ({url}): {e}")
            continue

    return UpdateResult(error="无法连接更新服务器，请手动检查 releases 页面")


def _compare_versions(latest: str, current: str) -> bool:
    """简单语义版本比较：1.5.0 > 1.4.1"""
    try:
        l = tuple(int(x) for x in latest.split("."))
        c = tuple(int(x) for x in current.split("."))
        return l > c
    except Exception:
        return latest != current
