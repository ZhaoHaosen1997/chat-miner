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
    list_prompt_profiles, get_prompt_profile, create_prompt_profile,
    update_prompt_profile, delete_prompt_profile,
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
            logger.warning("Ollama 健康检查失败: %s", e)
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


def _reload_weflow_scheduler():
    """WeFlow 设置变更后重载调度器"""
    try:
        from services.scheduler import reload_scheduler
        reload_scheduler()
    except Exception as e:
        logger.debug("WeFlow 调度器重载跳过: %s", e)


def _reload_pond_scheduler():
    """鱼塘设置变更后重载调度器"""
    try:
        from services.scheduler import reload_pond_scheduler
        reload_pond_scheduler()
    except Exception as e:
        logger.debug("鱼塘调度器重载跳过: %s", e)


@router.put("/app-settings")
async def api_update_app_setting(body: AppSettingUpdate):
    """更新单个应用设置，即时生效"""
    upsert_app_setting(body.key, body.value)
    config.load_from_db()
    _reload_weflow_scheduler()
    _reload_pond_scheduler()
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
    _reload_weflow_scheduler()
    _reload_pond_scheduler()
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


# ---- v1.5.4: 提示词管理 ----

class PromptCreate(BaseModel):
    name: str
    analysis_type: str
    system_prompt: str = ""
    is_default: bool = False

class PromptUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    is_default: bool | None = None


@router.get("/prompts")
async def api_list_prompts(analysis_type: str = ""):
    """列出提示词配置"""
    profiles = list_prompt_profiles(analysis_type)
    return {"code": 200, "message": "ok", "data": profiles}


@router.post("/prompts")
async def api_create_prompt(body: PromptCreate):
    if not body.name.strip():
        raise HTTPException(400, "名称不能为空")
    if not body.analysis_type:
        raise HTTPException(400, "分析类型不能为空")
    pid = create_prompt_profile(body.name.strip(), body.analysis_type,
                                 body.system_prompt, body.is_default)
    profile = get_prompt_profile(pid)
    return {"code": 200, "message": "创建成功", "data": profile}


@router.put("/prompts/{profile_id}")
async def api_update_prompt(profile_id: int, body: PromptUpdate):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.system_prompt is not None:
        updates["system_prompt"] = body.system_prompt
    if body.is_default is not None:
        updates["is_default"] = body.is_default
    if not updates:
        raise HTTPException(400, "无更新字段")
    if not update_prompt_profile(profile_id, **updates):
        raise HTTPException(404, "配置不存在")
    profile = get_prompt_profile(profile_id)
    return {"code": 200, "message": "更新成功", "data": profile}


@router.delete("/prompts/{profile_id}")
async def api_delete_prompt(profile_id: int):
    if not delete_prompt_profile(profile_id):
        raise HTTPException(404, "配置不存在")
    return {"code": 200, "message": "已删除", "data": None}


@router.put("/prompts/{profile_id}/default")
async def api_set_default_prompt(profile_id: int):
    """设为默认"""
    if not update_prompt_profile(profile_id, is_default=True):
        raise HTTPException(404, "配置不存在")
    profile = get_prompt_profile(profile_id)
    return {"code": 200, "message": "已设为默认", "data": profile}


# v1.5.4: 各分析类型的硬编码默认 system prompt（供前端预填参考）
_DEFAULT_SYSTEM_PROMPTS = {
    "daily": "你是一个群聊观察者，善于从对话中提取关键信息。请用简洁有趣的方式总结。",
    "portrait": "你是一个性格分析师，善于从聊天记录中洞察说话者的性格特征和语言风格。",
    "weekly": "你是一位喜剧作家+人类学家+小说家。请用幽默深刻的笔触撰写群聊周报。",
    "monthly": "你是一位人类学家+社区分析师+电影预告片编剧。请用宏大叙事撰写群聊月报。",
    "annual": "你是一位颁奖典礼主持人+群聊人类学家。请用典礼风格撰写年度报告。",
    "comprehensive": "你是一位跨群人格分析专家。同一个人在不同群里可能展现不同侧面，你的任务是综合所有群的表现，提炼出核心人格特质和群际差异。",
}


@router.get("/prompts/default")
async def api_get_default_prompt(analysis_type: str):
    """获取某分析类型的系统默认提示词（供新建时参考）"""
    prompt = _DEFAULT_SYSTEM_PROMPTS.get(analysis_type, "")
    return {"code": 200, "message": "ok", "data": {"analysis_type": analysis_type, "system_prompt": prompt}}
