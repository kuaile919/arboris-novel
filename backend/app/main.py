# AIMETA P=FastAPI应用入口_装配路由依赖和生命周期管理|R=应用启动_路由注册_中间件配置|NR=不含业务逻辑实现|E=uvicorn_app.main:app|X=http|A=FastAPI_app实例|D=fastapi,uvicorn|S=net,db|RD=./README.ai
"""FastAPI 应用入口，负责装配路由、依赖与生命周期管理。"""

import logging
import sys
from logging.config import dictConfig
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .db.init_db import init_db
from .services.prompt_service import PromptService
from .db.session import AsyncSessionLocal
from .api.routers import api_router

# 确保日志目录存在
LOG_DIR = Path(__file__).parent.parent / "storage" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "filename": str(LOG_FILE),
                "maxBytes": settings.log_file_max_mb * 1024 * 1024,
                "backupCount": settings.log_file_backup_count,
                "encoding": "utf-8",
            }
        },
        "loggers": {
            "backend": {
                "level": settings.logging_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "app": {
                "level": settings.logging_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "backend.app": {
                "level": settings.logging_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "backend.api": {
                "level": settings.logging_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "backend.services": {
                "level": settings.logging_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
        },
    }
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时初始化数据库，并预热提示词缓存
    await init_db()
    async with AsyncSessionLocal() as session:
        prompt_service = PromptService(session)
        await prompt_service.preload()

    # 初始化定时任务调度器
    scheduler = None
    try:
        from .services.trend.scheduled_tasks import init_scheduler, start_scheduler, shutdown_scheduler
        scheduler = init_scheduler(AsyncSessionLocal)
        if scheduler:
            start_scheduler()
    except Exception as e:
        logging.getLogger(__name__).warning(f"定时任务初始化失败: {e}")

    yield

    # 应用关闭时清理资源
    if scheduler:
        try:
            shutdown_scheduler()
        except Exception:
            pass


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置，生产环境建议改为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# 健康检查接口（用于 Docker 健康检查和监控）
@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
async def health_check():
    """健康检查接口，返回应用状态。"""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
    }
