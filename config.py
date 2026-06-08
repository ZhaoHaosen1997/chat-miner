"""
Chat-Miner 配置模块
读取 .env 配置文件，提供全局配置访问
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # Ollama
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    OLLAMA_MODEL_FALLBACK = os.getenv("OLLAMA_MODEL_FALLBACK", "qwen3.5:9b")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

    # 服务
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8856"))
    RELOAD = os.getenv("RELOAD", "false").lower() == "true"

    # 数据目录
    DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
    DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/chat_miner.db")

    # GPU 分布式锁
    GPU_LOCK_ENABLED = os.getenv("GPU_LOCK_ENABLED", "true").lower() == "true"
    GPU_LOCK_URL = os.getenv("GPU_LOCK_URL", "http://192.168.x.x:8850")
    GPU_LOCK_WHO = os.getenv("GPU_LOCK_WHO", "chat-miner")
    GPU_LOCK_RETRY_INTERVAL = int(os.getenv("GPU_LOCK_RETRY_INTERVAL", "5"))
    GPU_LOCK_MAX_RETRIES = int(os.getenv("GPU_LOCK_MAX_RETRIES", "24"))

    # DeepSeek 在线模型（用于周报/月报的深度推理）
    # v0.7.2: 统一升级为 deepseek-v4-flash，通过 thinking 参数控制推理深度
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_REASONER_MODEL = os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-v4-flash")
    DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "120"))
    # 周报/月报温度参数（V4 Flash 默认 1.0，降低获得更稳定输出）
    WEEKLY_TEMPERATURE = float(os.getenv("WEEKLY_TEMPERATURE", "0.8"))
    MONTHLY_TEMPERATURE = float(os.getenv("MONTHLY_TEMPERATURE", "0.6"))
    # V4 Flash 最大输出 token（周报/月报内容丰富，需更大输出空间）
    DEEPSEEK_MAX_TOKENS_WEEKLY = int(os.getenv("DEEPSEEK_MAX_TOKENS_WEEKLY", "4096"))
    DEEPSEEK_MAX_TOKENS_MONTHLY = int(os.getenv("DEEPSEEK_MAX_TOKENS_MONTHLY", "8192"))

    # 画像刷新阈值
    PORTRAIT_REFRESH_DAYS = int(os.getenv("PORTRAIT_REFRESH_DAYS", "7"))

    # 日志
    LOG_DIR = BASE_DIR / os.getenv("LOG_DIR", "logs")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)


config = Config
