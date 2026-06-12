"""
设置 API v1.0.2：模型配置 CRUD + 应用设置 + 停用词管理
"""
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from config import config
from models.database import (
    list_model_configs, get_model_config, create_model_config,
    update_model_config, delete_model_config,
    get_all_app_settings, upsert_app_setting, upsert_app_settings_batch,
    get_stopwords_text,
)
from services.model_config import _row_to_config, _row_to_response, get_effective_model, mask_api_key
from services.online_model import check_online_model_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["设置"])


# ==================== Pydantic 模型 ====================

class ModelConfigCreate(BaseModel):
    name: str
    model_type: str = "local"
    endpoint: str = ""
    api_key: str = ""
    model_name: str = ""
    is_default: bool = False
    extra_params: str = ""

    @field_validator("model_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("local", "online"):
            raise ValueError("model_type 必须为 'local' 或 'online'")
        return v


class ModelConfigUpdate(BaseModel):
    name: str | None = None
    model_type: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_default: bool | None = None
    extra_params: str | None = None
    is_enabled: bool | None = None

    @field_validator("model_type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ("local", "online"):
            raise ValueError("model_type 必须为 'local' 或 'online'")
        return v


# ==================== API 端点 ====================

@router.get("/models")
async def api_list_models():
    """列出所有模型配置"""
    configs = list_model_configs()
    return {
        "code": 200,
        "message": "获取成功",
        "data": [_row_to_response(c) for c in configs],
    }


@router.get("/models/{config_id}")
async def api_get_model(config_id: int):
    """获取单个模型配置"""
    cfg = get_model_config(config_id)
    if not cfg:
        raise HTTPException(404, detail="模型配置不存在")
    return {
        "code": 200,
        "message": "获取成功",
        "data": _row_to_response(cfg),
    }


@router.post("/models")
async def api_create_model(body: ModelConfigCreate):
    """新增模型配置"""
    try:
        new_id = create_model_config(
            name=body.name,
            model_type=body.model_type,
            endpoint=body.endpoint,
            api_key=body.api_key,
            model_name=body.model_name,
            is_default=body.is_default,
            extra_params=body.extra_params,
        )
        cfg = get_model_config(new_id)
        return {
            "code": 200,
            "message": f"模型 '{body.name}' 创建成功",
            "data": _row_to_response(cfg),
        }
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(400, detail=f"模型名称 '{body.name}' 已存在")
        raise HTTPException(500, detail=str(e))


@router.put("/models/{config_id}")
async def api_update_model(config_id: int, body: ModelConfigUpdate):
    """更新模型配置"""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, detail="没有要更新的字段")

    success = update_model_config(config_id, **updates)
    if not success:
        raise HTTPException(404, detail="模型配置不存在")

    cfg = get_model_config(config_id)
    return {
        "code": 200,
        "message": "更新成功",
        "data": _row_to_response(cfg),
    }


@router.delete("/models/{config_id}")
async def api_delete_model(config_id: int):
    """删除模型配置"""
    success = delete_model_config(config_id)
    if not success:
        raise HTTPException(404, detail="模型配置不存在")
    return {
        "code": 200,
        "message": "删除成功",
        "data": None,
    }


@router.post("/models/{config_id}/set-default")
async def api_set_default(config_id: int):
    """设为默认模型（自动清除同类型旧默认）"""
    cfg = get_model_config(config_id)
    if not cfg:
        raise HTTPException(404, detail="模型配置不存在")

    success = update_model_config(config_id, is_default=True)
    if not success:
        raise HTTPException(500, detail="设置默认失败")

    return {
        "code": 200,
        "message": f"'{cfg['name']}' 已设为 {cfg['model_type']} 类型默认模型",
        "data": None,
    }


@router.get("/models/{config_id}/health")
async def api_check_health(config_id: int):
    """测试模型连通性"""
    cfg = get_model_config(config_id)
    if not cfg:
        raise HTTPException(404, detail="模型配置不存在")

    model_cfg = _row_to_config(cfg)  # 需要真实 API Key 做连通测试

    if model_cfg["model_type"] == "local":
        # Ollama: 检查 /api/tags
        endpoint = model_cfg["endpoint"]
        try:
            async with httpx.AsyncClient(timeout=config.OLLAMA_TIMEOUT) as client:
                resp = await client.get(f"{endpoint}/api/tags")
                if resp.status_code == 200:
                    tags_data = resp.json()
                    models = [m.get("name", "") for m in tags_data.get("models", [])]
                    model_exists = model_cfg["model_name"] in models
                    return {
                        "code": 200,
                        "message": "连通成功" if model_exists else "Ollama在线但模型未找到",
                        "data": {
                            "online": True,
                            "model_found": model_exists,
                            "available_models": models[:10],
                            "duration_ms": 0,
                            "error": None if model_exists else f"模型 '{model_cfg['model_name']}' 不在可用列表中",
                        },
                    }
                else:
                    return {
                        "code": 200,
                        "message": "Ollama 不可达",
                        "data": {"online": False, "error": f"HTTP {resp.status_code}"},
                    }
        except Exception as e:
            return {
                "code": 200,
                "message": "连通失败",
                "data": {"online": False, "error": str(e)},
            }
    else:
        # Online: 发送最小 chat 请求
        result = await check_online_model_health(model_cfg)
        return {
            "code": 200,
            "message": "连通成功" if result["online"] else "连通失败",
            "data": result,
        }


@router.get("/defaults")
async def api_get_defaults():
    """获取当前各类型的默认模型（用于前端初始化）"""
    local = get_effective_model("local")
    online = get_effective_model("online")
    # v0.13.0: 返回时脱敏 API Key
    local["api_key"] = mask_api_key(local.get("api_key", ""))
    online["api_key"] = mask_api_key(online.get("api_key", ""))
    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "local": local,
            "online": online,
        },
    }


# ==================== 应用设置 v1.0.2 ====================

class AppSettingUpdate(BaseModel):
    key: str
    value: str


class AppSettingsBatchUpdate(BaseModel):
    updates: dict[str, str]


@router.get("/app-settings")
async def api_get_app_settings():
    """获取所有应用设置（敏感字段自动脱敏）"""
    settings = get_all_app_settings()
    return {
        "code": 200,
        "message": "获取成功",
        "data": settings,
    }


@router.put("/app-settings")
async def api_update_app_setting(body: AppSettingUpdate):
    """更新单个应用设置，即时生效"""
    upsert_app_setting(body.key, body.value)
    config.load_from_db()
    return {
        "code": 200,
        "message": f"设置 '{body.key}' 已更新，即时生效",
        "data": None,
    }


@router.put("/app-settings/batch")
async def api_update_app_settings_batch(body: AppSettingsBatchUpdate):
    """批量更新应用设置，即时生效"""
    upsert_app_settings_batch(body.updates)
    config.load_from_db()
    return {
        "code": 200,
        "message": f"已更新 {len(body.updates)} 项设置",
        "data": None,
    }


# ==================== 停用词管理 v1.0.2 ====================

class StopwordsUpdate(BaseModel):
    text: str


@router.get("/stopwords")
async def api_get_stopwords():
    """获取停用词文本"""
    text = get_stopwords_text()
    return {
        "code": 200,
        "message": "获取成功",
        "data": {"text": text},
    }


@router.put("/stopwords")
async def api_update_stopwords(body: StopwordsUpdate):
    """更新停用词文本（下次分析时生效）"""
    upsert_app_setting("stopwords_text", body.text)
    return {
        "code": 200,
        "message": "停用词已更新，下次分析时生效",
        "data": None,
    }
