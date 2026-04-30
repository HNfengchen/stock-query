from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import traceback
import json

from backend.services.analysis_service import run_analysis

router = APIRouter()


class AnalysisRequest(BaseModel):
    stock_input: str
    position_status: str = "未持有"
    cost_price: Optional[float] = None


class BatchAnalysisRequest(BaseModel):
    stocks: List[AnalysisRequest]


def _sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj or obj == float('inf') or obj == float('-inf'):
            return None
        return obj
    return obj


@router.post("/analysis")
async def analyze(req: AnalysisRequest):
    try:
        result = run_analysis(req.stock_input, req.position_status, req.cost_price)
        result = _sanitize_for_json(result)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analysis/batch")
async def batch_analyze(req: BatchAnalysisRequest):
    results = []
    errors = []
    for stock in req.stocks:
        try:
            result = run_analysis(stock.stock_input, stock.position_status, stock.cost_price)
            result = _sanitize_for_json(result)
            results.append(result)
        except Exception as e:
            errors.append({"stock_input": stock.stock_input, "error": str(e)})
    return {"results": results, "errors": errors}
