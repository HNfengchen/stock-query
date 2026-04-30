from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import traceback
import json
import numpy as np

from backend.services.backtest_service import run_builtin_backtest, run_custom_backtest

router = APIRouter()


class BacktestRequest(BaseModel):
    stock_code: str
    mode: str = "builtin"
    params: Optional[Dict] = None
    algorithm_code: Optional[str] = None
    algorithm_name: Optional[str] = None


def _sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        if obj != obj or obj == float('inf') or obj == float('-inf'):
            return None
        return obj
    return obj


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        if req.mode == "custom":
            if not req.algorithm_code:
                raise HTTPException(status_code=400, detail="自定义算法需要提供 algorithm_code")
            result = run_custom_backtest(req.stock_code, req.algorithm_code, req.algorithm_name or "custom")
        else:
            result = run_builtin_backtest(req.stock_code, req.params)
        result = _sanitize_for_json(result)
        return result
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
        result = _sanitize_for_json(result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
