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
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_REASONER_MODEL = os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner")
    DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "90"))

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
