"""
Chat-Miner 配置模块 v1.0.2
三层配置体系：config.json（启动关键参数）→ config.py（硬编码默认值）→ DB app_settings（可热更新）
"""
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_base_dir() -> Path:
    """获取应用根目录。兼容开发模式和 PyInstaller one-folder 打包。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = _get_base_dir()


class Config:
    # ==================== 基础路径 ====================
    BASE_DIR = _get_base_dir()

    # ==================== 版本号（唯一版本源，发版时只需改此处） ====================
    VERSION = "1.18.3"

    # ==================== Ollama（本地模型 fallback） ====================
    OLLAMA_HOST = "http://localhost:11434"
    OLLAMA_MODEL = "qwen2.5:14b"
    OLLAMA_MODEL_FALLBACK = "qwen3.5:9b"
    OLLAMA_TIMEOUT = 120

    # ==================== 服务（启动关键参数，可由 config.json 覆盖） ====================
    HOST = "0.0.0.0"
    PORT = 8856
    RELOAD = False

    # ==================== 数据目录 ====================
    DATA_DIR = BASE_DIR / "data"
    DATABASE_PATH = BASE_DIR / "data" / "chat_miner.db"

    # ==================== GPU 分布式锁 ====================
    GPU_LOCK_ENABLED = False
    GPU_LOCK_URL = "http://localhost:8850"
    GPU_LOCK_WHO = "chat-miner"
    GPU_LOCK_RETRY_INTERVAL = 5
    GPU_LOCK_MAX_RETRIES = 24

    # ==================== DeepSeek 在线模型（fallback，实际由 model_configs 表管理） ====================
    DEEPSEEK_API_KEY = ""
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL = "deepseek-v4-flash"
    DEEPSEEK_REASONER_MODEL = "deepseek-v4-flash"
    DEEPSEEK_TIMEOUT = 120
    ONLINE_RETRY_COUNT = 2  # v1.0.3: 在线模型失败后重试次数（总计 1+N 次尝试）
    WEEKLY_TEMPERATURE = 0.8
    MONTHLY_TEMPERATURE = 0.6
    DEEPSEEK_MAX_TOKENS_WEEKLY = 4096
    DEEPSEEK_MAX_TOKENS_MONTHLY = 8192

    # ==================== 周期报告可用性阈值（可在设置-高级选项配置） ====================
    WEEKLY_MIN_DAYS = 3
    WEEKLY_MIN_MSGS = 50
    MONTHLY_MIN_DAYS = 5
    MONTHLY_MIN_MSGS = 100
    ANNUAL_MIN_DAYS = 30
    ANNUAL_MIN_MSGS = 300

    # ==================== 事件探测 (v1.18.0) ====================
    # v1.18.1: EVENT_WINDOW_SIZE/OVERLAP 已废弃，替换为自适应切分配置
    EVENT_WINDOW_SIZE = 200          # deprecated — 不再使用
    EVENT_WINDOW_OVERLAP = 20        # deprecated — 不再使用
    EVENT_AI_CONCURRENCY = 3
    EVENT_ACTIVE_GROUP_THRESHOLD = 30
    EVENT_ACTIVE_PEAK_ABSOLUTE = 80
    EVENT_QUIET_PEAK_MULTIPLIER = 3
    # v1.18.1 自适应切分
    EVENT_MIN_GAP_MINUTES = 15       # 事件组最小时间间隙(分钟)
    EVENT_MIN_GROUP_SIZE = 10        # 事件组最小消息数
    EVENT_MAX_GROUP_SIZE = 500       # 事件组最大消息数

    # ==================== 画像刷新阈值 ====================
    PORTRAIT_REFRESH_DAYS = 7

    # ==================== 本地大模型全局开关（v1.17.0） ====================
    LOCAL_LLM_ENABLED = False
    LOCAL_LLM_HOST = "http://localhost:11434"
    LOCAL_LLM_FALLBACK_MODEL = "qwen3.5:9b"

    # ==================== 管道执行参数（v1.17.0） ====================
    PIPELINE_MAX_RETRIES = 3
    PIPELINE_STEP_TIMEOUT = 90
    PIPELINE_CIRCUIT_BREAKER_THRESHOLD = 5
    PIPELINE_CIRCUIT_BREAKER_COOLDOWN = 30

    # ==================== WeFlow 增量同步 ====================
    WEFLOW_ENABLED = False
    WEFLOW_BASE_URL = "http://127.0.0.1:5031"
    WEFLOW_ACCESS_TOKEN = ""
    WEFLOW_SYNC_INTERVAL_HOURS = 24

    # ==================== 日志 ====================
    # v1.16.0: 鱼塘精力系统
    POND_ENERGY_REGEN_AMOUNT = 5       # 精力每轮恢复量
    POND_TOUCH_DAILY_LIMIT = 5       # 摸鱼每日次数上限
    # v1.16.1: 鱼塘自动化被动事件 + 金库
    POND_AUTO_EVENTS_ENABLED = False   # 全局开关，默认关闭
    POND_EVENT_INTERVAL_MINUTES = 30   # 事件间隔(分钟)
    POND_TREASURY_TAX_RATE = 5         # 金库税率(%)
    # v1.16.4: 公告牌 + 创意工坊
    POND_BULLETIN_BOARD = ""           # 鱼塘公告牌内容
    CUSTOM_FLAVOR_TEXTS = "[]"         # 用户自定义风味文本
    CUSTOM_LAST_WORDS = "[]"           # 用户自定义鱼遗言
    CUSTOM_DAILY_STATUS = "[]"         # 用户自定义状态语
    # v1.16.5: 作弊模式 + 天气覆盖
    POND_CHEAT_MODE = False            # 允许作弊开关
    POND_CHEAT_WEATHER_OVERRIDE = ""   # 调试天气覆盖（空=不覆盖）

    LOG_DIR = BASE_DIR / "logs"
    LOG_LEVEL = "INFO"
    LOG_RETENTION_DAYS = 90     # 分析日志保留天数
    LOG_MAX_RECORDS = 500       # 任务记录最多保留条数

    # ==================== 默认停用词（v1.0.2：从此常量初始化 DB，不再读取 stopwords.txt） ====================
    DEFAULT_STOPWORDS = """# 用户自定义过滤词
# 每行一个词，# 开头的行为注释
# 这些词不会出现在高频词、性格分析、emoji 统计等任何分析结果中
# 修改后即时生效（下次分析时加载），无需重启服务

# === 常见无意义口语 ===
笑死
确实
牛逼
厉害
哈哈哈
哈哈哈哈
卧槽
我去
真的假的
不知道
不会吧
好吧
还行
可以可以
对对对
嗯嗯
哦哦
好家伙
绝了
太强了
我靠
牛啊
牛哇
离谱
离谱了
1

# === 引用/回复前缀 ===
引用
回复
图片
视频
语音
文件
链接
位置
名片
表情
消息
记录
聊天记录
小程序
红包

# === 群友昵称和历史昵称 ===
群友ID示例

# === 你自己添加的过滤词（每行一个） ===
"""

    # ==================== config.json 加载（v1.0.2） ====================

    # 可通过 config.json 覆盖的启动关键参数及其默认值
    _JSON_CONFIG_KEYS = {
        "host": ("HOST", "0.0.0.0"),
        "port": ("PORT", 8856),
        "data_dir": ("DATA_DIR", BASE_DIR / "data"),
        "log_dir": ("LOG_DIR", BASE_DIR / "logs"),
        "log_level": ("LOG_LEVEL", "INFO"),
    }

    @classmethod
    def _load_json_config(cls):
        """从 exe 同级 config.json 加载启动参数（可选文件）。
        文件不存在或解析失败时使用硬编码默认值，不阻止启动。
        """
        json_path = BASE_DIR / "config.json"
        if not json_path.exists():
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"config.json 解析失败，使用默认值: {e}")
            return

        if not isinstance(data, dict):
            logger.warning("config.json 格式错误（非对象），使用默认值")
            return

        # 检查并补充缺失字段（新版本新增的配置项）
        missing = [k for k in cls._JSON_CONFIG_KEYS if k not in data]
        if missing:
            for k in missing:
                _, default_val = cls._JSON_CONFIG_KEYS[k]
                if k in ("data_dir", "log_dir"):
                    data[k] = str(default_val)  # Path → 字符串
                else:
                    data[k] = default_val
                logger.info(f"config.json 补充缺失字段: {k} = {data[k]}")
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info("config.json 已更新（补充缺失字段）")
            except OSError as e:
                logger.warning(f"config.json 写入失败: {e}")

        for json_key, (attr_name, default_val) in cls._JSON_CONFIG_KEYS.items():
            if json_key in data:
                try:
                    val = data[json_key]
                    if json_key in ("data_dir", "log_dir"):
                        val = Path(str(val))
                        if not val.is_absolute():
                            val = BASE_DIR / val  # v1.5.7: 相对路径基于 EXE 目录解析
                    if json_key == "port":
                        val = int(val)
                    if json_key == "log_level":
                        val = str(val).upper()
                    setattr(cls, attr_name, val)
                    logger.info(f"config.json → {attr_name} = {val}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"config.json 字段 '{json_key}' 值无效: {e}，使用默认值 {default_val}")

        # 如果 data_dir 被 config.json 覆盖，同步更新 DATABASE_PATH
        if "data_dir" in data:
            cls.DATABASE_PATH = cls.DATA_DIR / "chat_miner.db"

    @classmethod
    def load_from_db(cls):
        """v1.0.2: 从数据库加载可热更新的配置项。init_db() 之后调用。"""
        try:
            from models.database import load_app_settings_to_config
            load_app_settings_to_config()
            logger.info("DB 应用设置已加载到 config")
        except Exception as e:
            logger.warning(f"从 DB 加载应用设置失败（使用默认值）: {e}")

    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)


# 模块导入时自动加载 config.json（在所有 import 之前执行）
Config._load_json_config()

config = Config
