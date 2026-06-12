"""
模型配置解析层 v0.12.0
合并数据库配置与 .env 兜底，提供统一的模型解析接口。

优先级：DB is_default=1 > DB 同类型首个 > .env 构造的兜底 dict
"""
import json
import logging
from models.database import get_default_model, get_model_config, list_model_configs
from config import config

logger = logging.getLogger(__name__)


def _build_env_fallback(model_type: str) -> dict:
    """从 .env 构造兜底模型 dict（用于 DB 无配置时）"""
    if model_type == "local":
        return {
            "id": None,
            "name": "Ollama (.env)",
            "model_type": "local",
            "endpoint": config.OLLAMA_HOST,
            "api_key": "",
            "model_name": config.OLLAMA_MODEL,
            "is_db_config": False,
            "extra_params": {},
        }
    else:
        return {
            "id": None,
            "name": "DeepSeek (.env)",
            "model_type": "online",
            "endpoint": config.DEEPSEEK_API_URL,
            "api_key": config.DEEPSEEK_API_KEY,
            "model_name": config.DEEPSEEK_MODEL,
            "is_db_config": False,
            "extra_params": {},
        }


def _row_to_config(row: dict) -> dict:
    """将 DB 行转为统一模型配置 dict"""
    extra = {}
    if row.get("extra_params"):
        try:
            extra = json.loads(row["extra_params"])
        except json.JSONDecodeError:
            pass
    return {
        "id": row["id"],
        "name": row["name"],
        "model_type": row["model_type"],
        "endpoint": row["endpoint"],
        "api_key": row["api_key"],
        "model_name": row["model_name"],
        "is_db_config": True,
        "extra_params": extra,
        "is_enabled": row.get("is_enabled", 1),
    }


def get_effective_model(model_type: str) -> dict:
    """
    获取某类型的"生效模型"配置。
    优先 DB 默认 → DB 同类型首个 → .env 兜底。
    v0.13.3: 单次查询，避免 N+1。
    """
    # 1. 一次查询获取所有启用的同类型配置（按 is_default desc, id asc 排序）
    all_configs = list_model_configs()
    for c in all_configs:
        if c["model_type"] == model_type and c.get("is_enabled", 1):
            if c.get("is_default"):
                return _row_to_config(c)
    # 2. 同类型任意第一条（无默认时取首个）
    for c in all_configs:
        if c["model_type"] == model_type and c.get("is_enabled", 1):
            logger.warning(f"模型类型 {model_type} 无默认配置，使用首个可用配置: {c['name']}")
            return _row_to_config(c)

    # 3. .env 兜底
    logger.info(f"模型类型 {model_type} 无数据库配置，使用 .env 兜底")
    return _build_env_fallback(model_type)


def resolve_model_for_report(model_type: str, requested_model_id: int | None = None) -> dict:
    """
    根据可选的 model_id 解析报告生成使用的模型。

    Args:
        model_type: 期望的模型类型 ('local' | 'online')
        requested_model_id: 前端传入的模型 ID（None 表示用默认）

    Returns:
        统一模型配置 dict

    Raises:
        ValueError: model_id 无效或类型不匹配
    """
    if requested_model_id is not None:
        db_config = get_model_config(requested_model_id)
        if not db_config:
            raise ValueError(f"模型配置 ID={requested_model_id} 不存在")
        if not db_config.get("is_enabled", 1):
            raise ValueError(f"模型 '{db_config['name']}' 已禁用")
        if db_config["model_type"] != model_type:
            raise ValueError(
                f"模型 '{db_config['name']}' 类型为 '{db_config['model_type']}'，"
                f"不支持 {model_type} 类型的报告"
            )
        return _row_to_config(db_config)

    # 未指定 model_id，使用默认
    return get_effective_model(model_type)


def resolve_model_with_fallback(
    model_type: str, requested_model_id: int | None = None
) -> tuple[dict, dict | None]:
    """
    解析主模型 + 兜底模型。

    返回值: (主模型, 兜底模型或None)

    兜底策略：
    - local: .env OLLAMA_MODEL_FALLBACK 或同类型下一个 DB 配置
    - online: local 默认模型（跨类型兜底）
    """
    primary = resolve_model_for_report(model_type, requested_model_id)

    fallback = None
    if model_type == "local":
        # 同类型兜底：优先 .env fallback 模型
        if config.OLLAMA_MODEL_FALLBACK and primary["model_name"] != config.OLLAMA_MODEL_FALLBACK:
            fallback = {
                "id": None,
                "name": "Ollama Fallback (.env)",
                "model_type": "local",
                "endpoint": config.OLLAMA_HOST,
                "api_key": "",
                "model_name": config.OLLAMA_MODEL_FALLBACK,
                "is_db_config": False,
                "extra_params": {},
            }
        # 再找 DB 中同类型非当前的其他启用模型
        if not fallback:
            all_configs = list_model_configs()
            for c in all_configs:
                if (c["model_type"] == "local" and c.get("is_enabled", 1)
                        and c["id"] != primary.get("id")):
                    fallback = _row_to_config(c)
                    break
    elif model_type == "online":
        # 跨类型兜底：local 默认模型
        try:
            fallback = get_effective_model("local")
        except Exception:
            fallback = _build_env_fallback("local")

    return primary, fallback


def is_online_available() -> bool:
    """检查是否有可用的在线模型配置（有 API Key 即可用）"""
    effective = get_effective_model("online")
    return bool(effective.get("api_key"))


# v0.13.0: API Key 脱敏
def mask_api_key(key: str) -> str:
    """脱敏 API Key，保留前后各 3 字符"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***" if len(key) > 2 else key
    return key[:3] + "***" + key[-4:]


def _row_to_response(row: dict) -> dict:
    """DB 行转前端安全响应（API Key 脱敏）"""
    cfg = _row_to_config(row)
    cfg["api_key"] = mask_api_key(cfg["api_key"])
    return cfg
