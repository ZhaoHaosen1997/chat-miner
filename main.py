"""
Chat-Miner — 群聊内容分析应用 v1.0
FastAPI 入口，端口 8856
"""
import os
import logging
import sys

# PyInstaller console=False 兼容：重定向 None 流到 devnull
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import config
from models.database import init_db
from routers import groups, report, portrait, stats, tasks, fish_pond, settings


# --- PyInstaller 兼容：获取静态资源路径 ---
def _get_dist_path() -> str:
    """获取前端 dist 目录路径。兼容开发模式和 PyInstaller one-folder 打包。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller: 资源在 _MEIPASS
        return os.path.join(sys._MEIPASS, "frontend", "dist")
    return os.path.join(os.path.dirname(__file__), "frontend", "dist")


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
    config.load_from_db()  # v1.0.2: 从 DB 加载可热更新配置
    logger.info(f"数据库: {config.DATABASE_PATH}")
    if config.GPU_LOCK_ENABLED:
        logger.info(f"Ollama: {config.OLLAMA_HOST} | 模型: {config.OLLAMA_MODEL}")
    else:
        logger.info("GPU 锁已禁用（单机模式）")
    logger.info(f"端口: {config.PORT}")

    # 预加载群数据到内存，避免首次请求等待（使用 pickle 缓存加速）
    try:
        from models.database import list_groups
        from routers.groups import get_chat_cache
        groups = list_groups()
        if groups:
            logger.info(f"预加载 {len(groups)} 个群数据...")
            for g in groups:
                get_chat_cache(g["id"])
            logger.info("预加载完成")
    except Exception as e:
        logger.warning(f"预加载失败（不影响正常使用）: {e}")

    logger.info("=" * 50)
    yield
    logger.info("Chat-Miner 已关闭")


# --- FastAPI 应用 ---
app = FastAPI(
    title="Chat-Miner",
    description="微信群聊内容分析 — 基于 AI 大模型",
    version="1.0.4",
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

# 路由注册（API 必须在静态文件之前注册）
app.include_router(groups.router)
app.include_router(report.router)
app.include_router(portrait.router)
app.include_router(stats.router)
app.include_router(tasks.router)
app.include_router(fish_pond.router)
app.include_router(settings.router)

# 挂载前端静态文件（API 路由优先，未匹配的走静态文件）
dist_path = _get_dist_path()
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="frontend")


# --- 入口 ---
if __name__ == "__main__":
    import uvicorn
    import threading
    import webbrowser
    import time

    def _open_browser():
        """服务启动后自动打开浏览器"""
        time.sleep(1.5)
        try:
            webbrowser.open(f"http://localhost:{config.PORT}")
        except Exception:
            pass  # 无浏览器也不崩溃

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        log_level=config.LOG_LEVEL.lower(),
    )
