import os
import sys
import traceback
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from contextlib import asynccontextmanager

from backend.exceptions import StockQueryException, AnalysisFailedError
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
    try:
        from backend.routers.analysis import _executor
        _executor.shutdown(wait=True)
        logger.info("ThreadPoolExecutor 已关闭")
    except Exception as e:
        logger.warning(f"ThreadPoolExecutor 关闭失败: {e}")


app = FastAPI(title="Stock Query API", lifespan=lifespan)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
origins_list = [o.strip() for o in cors_origins.split(",")]
allow_credentials = True

if "*" in origins_list:
    allow_credentials = False
    logger.warning("CORS allow_origins 包含通配符 '*'，已自动禁用 allow_credentials 以防止 CSRF 攻击")

if cors_origins == "*":
    logger.warning("生产环境不应使用 CORS_ORIGINS='*'，请设置具体的允许源列表")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_body_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"请求体过大，最大允许 {self.max_body_size // (1024*1024)}MB"}
                )
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware)

app.include_router(analysis.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(websocket.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.exception_handler(StockQueryException)
async def stock_query_exception_handler(request: Request, exc: StockQueryException):
    logger.warning(f"Business error: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(AnalysisFailedError)
async def analysis_failed_exception_handler(request: Request, exc: AnalysisFailedError):
    logger.error(f"Analysis failed: {exc.detail}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "分析引擎内部错误，请稍后重试"})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})
