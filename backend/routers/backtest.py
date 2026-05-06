from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import traceback

from backend.services.backtest_service import run_builtin_backtest, run_custom_backtest
from backend.utils import sanitize_for_json

router = APIRouter()


class BacktestRequest(BaseModel):
    stock_code: str
    mode: str = "builtin"
    params: Optional[Dict] = None
    algorithm_code: Optional[str] = None
    algorithm_name: Optional[str] = None


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        if req.mode == "custom":
            if not req.algorithm_code:
                raise HTTPException(status_code=400, detail="自定义算法需要提供 algorithm_code")
            result = run_custom_backtest(req.stock_code, req.algorithm_code, req.algorithm_name or "custom")
        else:
            result = run_builtin_backtest(req.stock_code, req.params)
        return sanitize_for_json(result)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/backtest/custom")
async def backtest_custom(req: BacktestRequest):
    try:
        if not req.algorithm_code:
            raise HTTPException(status_code=400, detail="自定义算法需要提供 algorithm_code")
        result = run_custom_backtest(req.stock_code, req.algorithm_code, req.algorithm_name or "custom")
        return sanitize_for_json(result)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
