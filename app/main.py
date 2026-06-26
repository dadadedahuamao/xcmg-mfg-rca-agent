"""FastAPI 应用入口。"""

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.chat_routes import router as chat_router
from app.api.routes import router as rca_router
from app.config import settings
from app.persistence.postgres import init_db

# 创建 logs 目录
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)

# 配置日志
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# 文件处理器（按天滚动，保留 30 天）
file_handler = TimedRotatingFileHandler(
    os.path.join(log_dir, "app.log"),
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
)
file_handler.suffix = "%Y-%m-%d"
file_handler.setFormatter(log_formatter)

# 配置根日志器
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    logger.info(f"启动 XCMG Manufacturing RCA Agent v{__version__}")
    init_db()
    yield
    logger.info("关闭 XCMG Manufacturing RCA Agent")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="XCMG Manufacturing RCA Agent",
        description="制造业根因分析智能体 - 基于官方 LangGraph 工作流",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(chat_router)
    app.include_router(rca_router)

    # 挂载静态文件（根路径，必须在 API 路由之后）
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app


app = create_app()


def main():
    """CLI 入口。"""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
