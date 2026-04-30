from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.routers import analysis, backtest, history, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Stock Query API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
async def global_exception_handler(request, exc):
    import traceback
    traceback.print_exc()
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"detail": str(exc)})
