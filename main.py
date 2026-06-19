"""
Chat-Miner — 群聊内容分析应用 v1.4.0
FastAPI 入口，端口 8856
"""
import os
import logging
import sys

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import config
from models.database import init_db
from routers import groups, report, portrait, stats, tasks, fish_pond, settings, weflow, persona, events


# --- PyInstaller 兼容：获取静态资源路径 ---
def _get_dist_path() -> str:
    """获取前端 dist 目录路径。兼容开发模式和 PyInstaller one-folder 打包。"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "frontend", "dist")
    return os.path.join(os.path.dirname(__file__), "frontend", "dist")


def _get_asset_path(filename: str) -> str:
    """获取资源文件路径，兼容开发模式和 PyInstaller frozen 模式"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "assets", filename)
    return os.path.join(os.path.dirname(__file__), "assets", filename)


# --- 日志配置 ---
def setup_logging():
    config.ensure_dirs()
    log_file = config.LOG_DIR / "chat_miner.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")

    # v1.4.0: frozen 模式用 GUI 窗口，开发模式用控制台
    frozen = getattr(sys, 'frozen', False)
    if frozen:
        # console=False 时 stdout/stderr 为 None
        if sys.stdout is None:
            sys.stdout = open(os.devnull, 'w')
        if sys.stderr is None:
            sys.stderr = open(os.devnull, 'w')
        # 先用文件 handler，GUI 窗口创建后再重定向
        handlers = [file_handler, logging.StreamHandler(sys.stdout)]
    else:
        handlers = [file_handler, logging.StreamHandler(sys.stdout)]

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, "INFO"),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=handlers,
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
    # 日志清理在 load_from_db() 之后，确保用户配置的保留策略生效
    from models.database import cleanup_old_logs
    cleanup_old_logs()
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

        # 启动 WeFlow 定时调度
    try:
        from services.scheduler import init_scheduler
        init_scheduler()
    except Exception as e:
        logger.warning(f"WeFlow 调度器初始化失败: {e}")
    # v1.16.1: 启动静默鱼塘调度器
    try:
        from services.scheduler import init_pond_scheduler
        init_pond_scheduler()
    except Exception as e:
        logger.warning(f"鱼塘调度器初始化失败: {e}")

    logger.info("=" * 50)
    yield
    # 关闭调度器
    try:
        from services.scheduler import shutdown_scheduler, shutdown_pond_scheduler
        shutdown_pond_scheduler()
        shutdown_scheduler()
    except Exception as e:
        logger.debug("关闭调度器失败: %s", e)
    logger.info("Chat-Miner 已关闭")


# --- FastAPI 应用 ---
app = FastAPI(
    title="Chat-Miner",
    description="微信群聊内容分析 — 基于 AI 大模型",
    version=config.VERSION,
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


# v1.5.5: Cache-Control 中间件：防止浏览器将 API 响应写入磁盘缓存
# 同时为静态资源设置合理的浏览器内存缓存时间
from starlette.middleware.base import BaseHTTPMiddleware

class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/"):
            # API 响应禁止缓存，防止浏览器写入磁盘缓存
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith("/assets/") or any(
            path.endswith(ext) for ext in (".js", ".css", ".svg", ".ico", ".png", ".jpg", ".woff2")
        ):
            # 静态资源允许浏览器内存缓存 1 小时，避免重复下载
            response.headers["Cache-Control"] = "public, max-age=3600, immutable"
        return response

app.add_middleware(CacheControlMiddleware)

# 版本/健康检查
@app.get("/api/health")
async def api_health():
    return {"code": 200, "message": "ok", "data": {"version": config.VERSION}}

# 路由注册（API 必须在静态文件之前注册）
app.include_router(groups.router)
app.include_router(report.router)
app.include_router(portrait.router)
app.include_router(stats.router)
app.include_router(tasks.router)
app.include_router(fish_pond.router)
app.include_router(settings.router)
app.include_router(weflow.router)
app.include_router(persona.router)
app.include_router(events.router)

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

    frozen = getattr(sys, 'frozen', False)

    def _open_browser():
        time.sleep(2.0)
        try:
            webbrowser.open(f"http://localhost:{config.PORT}")
        except Exception as e:
            logger.debug("浏览器打开失败: %s", e)

    if frozen:
        # v1.4.1: GUI 模式 — uvicorn 后台线程，LogWindow 主线程
        import traceback

        def _run_server():
            uvicorn.run(
                "main:app",
                host=config.HOST,
                port=config.PORT,
                reload=False,
                log_level="warning",
            )

        server_thread = threading.Thread(target=_run_server, daemon=True)
        server_thread.start()

        try:
            logger.info("正在启动 GUI 窗口...")
            from services.log_window import LogWindow
            lw = LogWindow(title="Chat-Miner", port=config.PORT)
            lw._log_path = str(config.LOG_DIR / "chat_miner.log")
            logger.info("GUI 窗口已创建，进入事件循环...")
            lw.start()  # 阻塞，窗口关闭才返回；启动完成后自动打开浏览器
            logger.info("GUI 窗口已关闭")
        except Exception as e:
            logger.error(f"GUI 启动失败: {e}\n{traceback.format_exc()}")
            # fallback: 阻塞主线程不退出
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass

    else:
        # 开发模式：普通控制台
        threading.Thread(target=_open_browser, daemon=True).start()
        uvicorn.run(
            "main:app",
            host=config.HOST,
            port=config.PORT,
            reload=config.RELOAD,
            log_level=config.LOG_LEVEL.lower(),
        )
