"""
Chat-Miner 配置模块 v1.0
所有配置硬编码默认值，用户可通过 Web UI 修改模型配置。
"""
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    """获取应用根目录。兼容开发模式和 PyInstaller one-folder 打包。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = _get_base_dir()


class Config:
    # Ollama（本地模型，可选）
    OLLAMA_HOST = "http://localhost:11434"
    OLLAMA_MODEL = "qwen2.5:14b"
    OLLAMA_MODEL_FALLBACK = "qwen3.5:9b"
    OLLAMA_TIMEOUT = 120

    # 服务
    HOST = "0.0.0.0"
    PORT = 8856
    RELOAD = False

    # 数据目录（exe 同级，便携设计）
    DATA_DIR = BASE_DIR / "data"
    DATABASE_PATH = BASE_DIR / "data" / "chat_miner.db"

    # GPU 分布式锁（桌面单用户，默认关闭）
    GPU_LOCK_ENABLED = False
    GPU_LOCK_URL = "http://localhost:8850"
    GPU_LOCK_WHO = "chat-miner"
    GPU_LOCK_RETRY_INTERVAL = 5
    GPU_LOCK_MAX_RETRIES = 24

    # DeepSeek 在线模型
    DEEPSEEK_API_KEY = ""  # 用户在设置页填写
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL = "deepseek-v4-flash"
    DEEPSEEK_REASONER_MODEL = "deepseek-v4-flash"
    DEEPSEEK_TIMEOUT = 120
    WEEKLY_TEMPERATURE = 0.8
    MONTHLY_TEMPERATURE = 0.6
    DEEPSEEK_MAX_TOKENS_WEEKLY = 4096
    DEEPSEEK_MAX_TOKENS_MONTHLY = 8192

    # 画像刷新阈值
    PORTRAIT_REFRESH_DAYS = 7

    # 日志
    LOG_DIR = BASE_DIR / "logs"
    LOG_LEVEL = "INFO"

    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)


config = Config
