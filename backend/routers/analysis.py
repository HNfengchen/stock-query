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


@router.post("/analysis/batch-quick")
async def batch_quick_analyze(req: BatchAnalysisRequest):
    """批量快速分析，并发执行，SSE流式返回进度"""
    from sse_starlette.sse import EventSourceResponse
    import json
    import asyncio

    total = len(req.stocks)
    completed = {"count": 0}
    progress_queue: asyncio.Queue = asyncio.Queue()

    async def run_single(i: int, stock_req: AnalysisRequest):
        loop = asyncio.get_event_loop()
        try:
            def _run(sr=stock_req):
                return run_analysis(sr.stock_input, sr.position_status, sr.cost_price)

            result = await loop.run_in_executor(_executor, _run)
            signal = result.get("trading_signal", {})
            summary = {
                "stock_code": result.get("stock_code", stock_req.stock_input),
                "stock_name": result.get("stock_name", ""),
                "signal_text": signal.get("signal_text", ""),
                "score": signal.get("score", 0),
                "action_gate": signal.get("action_gate", ""),
                "recommendation": result.get("analysis", {}).get("recommendation", ""),
                "index": i,
            }
            completed["count"] += 1
            await progress_queue.put({"current": completed["count"], "total": total, "summary": summary})
        except Exception as e:
            err = {"stock_input": stock_req.stock_input, "error": str(e), "index": i}
            completed["count"] += 1
            await progress_queue.put({"current": completed["count"], "total": total, "error": err})

    async def event_generator():
        tasks = [asyncio.create_task(run_single(i, sr)) for i, sr in enumerate(req.stocks)]

        while completed["count"] < total:
            event_data = await progress_queue.get()
            yield {"event": "progress", "data": json.dumps(event_data, ensure_ascii=False)}

        await asyncio.gather(*tasks, return_exceptions=True)
        yield {"event": "complete", "data": json.dumps({"total": total}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
