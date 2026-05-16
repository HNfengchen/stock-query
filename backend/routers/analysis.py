from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import traceback
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from backend.services.analysis_service import run_analysis, run_analysis_staged
from backend.utils import sanitize_for_json

router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=8)

logger = logging.getLogger("stock_query")

BATCH_CONCURRENCY = 5


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
    from sse_starlette.sse import EventSourceResponse

    if not req.stocks:
        raise HTTPException(status_code=400, detail="股票列表不能为空")

    total = len(req.stocks)
    progress_queue: asyncio.Queue = asyncio.Queue()
    completed_count = 0
    all_errors: List[dict] = []
    all_summaries: List[dict] = []
    lock = asyncio.Lock()

    async def run_single(i: int, stock_req: AnalysisRequest):
        nonlocal completed_count
        loop = asyncio.get_event_loop()
        try:
            await progress_queue.put({
                "type": "analyzing",
                "current": i,
                "total": total,
                "stock_input": stock_req.stock_input,
                "index": i,
            })

            def _run(sr=stock_req):
                return run_analysis(sr.stock_input, sr.position_status, sr.cost_price, skip_signal_cache=True)

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
            async with lock:
                completed_count += 1
                all_summaries.append(summary)
            await progress_queue.put({
                "type": "completed",
                "current": completed_count,
                "total": total,
                "summary": summary,
            })
        except Exception as e:
            err = {"stock_input": stock_req.stock_input, "error": str(e), "index": i}
            async with lock:
                completed_count += 1
                all_errors.append(err)
            await progress_queue.put({
                "type": "error",
                "current": completed_count,
                "total": total,
                "error": err,
            })

    async def event_generator():
        semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)
        cancel_event = asyncio.Event()

        async def limited_run(i: int, sr: AnalysisRequest):
            async with semaphore:
                if cancel_event.is_set():
                    return
                await run_single(i, sr)

        tasks = [asyncio.create_task(limited_run(i, sr)) for i, sr in enumerate(req.stocks)]

        try:
            sent_completed = 0
            while sent_completed < total:
                event_data = await progress_queue.get()
                yield {"event": "progress", "data": json.dumps(event_data, ensure_ascii=False)}
                if event_data.get("type") in ("completed", "error"):
                    sent_completed += 1

            await asyncio.gather(*tasks, return_exceptions=True)
        except (asyncio.CancelledError, GeneratorExit):
            cancel_event.set()
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return

        try:
            from backend.services.history_service import batch_update_signal_cache
            cache_updates = []
            stock_map = {sr.stock_input: sr for sr in req.stocks}
            for summary in all_summaries:
                sr = stock_map.get(summary.get("stock_code", ""))
                if sr is None:
                    for s in req.stocks:
                        if s.stock_input in (summary.get("stock_code", ""), summary.get("stock_name", "")):
                            sr = s
                            break
                cache_updates.append({
                    "stock_code": summary.get("stock_code", ""),
                    "trading_signal": {
                        "signal_text": summary.get("signal_text", ""),
                        "score": summary.get("score", 0),
                    },
                    "position_status": sr.position_status if sr else None,
                    "cost_price": sr.cost_price if sr else None,
                })
            batch_update_signal_cache(cache_updates)
        except Exception as e:
            logger.warning(f"批量更新信号缓存失败: {e}")

        yield {
            "event": "complete",
            "data": json.dumps({
                "total": total,
                "success_count": total - len(all_errors),
                "error_count": len(all_errors),
                "errors": all_errors,
                "summaries": sorted(all_summaries, key=lambda x: x.get("index", 0)),
            }, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())


@router.get("/analysis/stream")
async def analysis_stream(stock_input: str, position_status: str = "未持有", cost_price: Optional[float] = None):
    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        stage_queue: asyncio.Queue = asyncio.Queue()

        def stage_callback(stage: str, data):
            asyncio.run_coroutine_threadsafe(
                stage_queue.put({"stage": stage, "data": data}),
                asyncio.get_event_loop(),
            )

        loop = asyncio.get_event_loop()

        def _run_staged():
            try:
                run_analysis_staged(stock_input, position_status, cost_price, stage_callback=stage_callback)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    stage_queue.put({"stage": "error", "data": {"error": str(e)}}),
                    asyncio.get_event_loop(),
                )

        task = loop.run_in_executor(_executor, _run_staged)

        try:
            while True:
                try:
                    event_data = await asyncio.wait_for(stage_queue.get(), timeout=600)
                    stage = event_data.get("stage")
                    data = event_data.get("data", {})

                    if stage == "stage_complete":
                        yield {"event": "stage_complete", "data": json.dumps(sanitize_for_json(data), ensure_ascii=False)}
                        break
                    elif stage == "error":
                        yield {"event": "error", "data": json.dumps(sanitize_for_json(data), ensure_ascii=False)}
                        break
                    else:
                        yield {"event": stage, "data": json.dumps(sanitize_for_json(data), ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": ""}
        except (asyncio.CancelledError, GeneratorExit):
            return
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(event_generator())
