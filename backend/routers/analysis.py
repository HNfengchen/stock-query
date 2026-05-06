from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import traceback
import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.services.analysis_service import run_analysis
from backend.utils import sanitize_for_json

router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=5)


class AnalysisRequest(BaseModel):
    stock_input: str
    position_status: str = "未持有"
    cost_price: Optional[float] = None


class BatchAnalysisRequest(BaseModel):
    stocks: List[AnalysisRequest]


@router.post("/analysis")
async def analyze(req: AnalysisRequest):
    try:
        result = run_analysis(req.stock_input, req.position_status, req.cost_price)
        return sanitize_for_json(result)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/analysis/batch")
async def batch_analyze(req: BatchAnalysisRequest):
    loop = asyncio.get_event_loop()

    def _run_single(stock_req):
        try:
            result = run_analysis(stock_req.stock_input, stock_req.position_status, stock_req.cost_price)
            return sanitize_for_json(result)
        except Exception as e:
            return {"error": str(e), "stock_input": stock_req.stock_input}

    tasks = [loop.run_in_executor(_executor, _run_single, stock) for stock in req.stocks]
    results_raw = await asyncio.gather(*tasks)

    results = []
    errors = []
    for r in results_raw:
        if "error" in r and "stock_input" in r and len(r) == 2:
            errors.append(r)
        else:
            results.append(r)

    return {"results": results, "errors": errors}
