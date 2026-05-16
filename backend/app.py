import os
import sys
import traceback
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from backend.routers import analysis, backtest, history, websocket

logger = logging.getLogger("stock_query")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from backend.celery_app import init_celery, is_celery_enabled
        init_celery()
        if is_celery_enabled():
            logger.info("Celery 异步任务功能已启用")
        else:
            logger.info("Celery 异步任务功能未启用，使用同步模式")
    except Exception as e:
        logger.warning(f"Celery 初始化失败: {e}，使用同步模式")
    yield


app = FastAPI(title="Stock Query API", lifespan=lifespan)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(websocket.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
