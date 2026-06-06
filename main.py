"""
Chat-Miner — 群聊内容分析应用
FastAPI 入口，端口 8856
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import config
from models.database import init_db
from routers import groups, report, portrait, stats


# --- 日志配置 ---
def setup_logging():
    config.ensure_dirs()
    log_file = config.LOG_DIR / "chat_miner.log"
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, "INFO"),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


setup_logging()
logger = logging.getLogger(__name__)


# --- 生命周期 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭"""
    logger.info("=" * 50)
    logger.info("Chat-Miner 启动中...")
    config.ensure_dirs()
    init_db()
    logger.info(f"数据库: {config.DATABASE_PATH}")
    logger.info(f"Ollama: {config.OLLAMA_HOST} | 模型: {config.OLLAMA_MODEL}")
    logger.info(f"端口: {config.PORT}")
    logger.info("=" * 50)
    yield
    logger.info("Chat-Miner 已关闭")


# --- FastAPI 应用 ---
app = FastAPI(
    title="Chat-Miner",
    description="微信群聊内容分析 — 基于本地 Ollama AI",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS（允许前端开发服务器）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(groups.router)
app.include_router(report.router)
app.include_router(portrait.router)
app.include_router(stats.router)


# 根路由
@app.get("/")
async def root():
    return {
        "code": 200,
        "message": "Chat-Miner API 服务运行中",
        "data": {
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/health",
        },
    }


# --- 入口 ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        log_level=config.LOG_LEVEL.lower(),
    )
