from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional
import traceback
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from backend.exceptions import InvalidStockCodeError, DataInsufficientError, AnalysisFailedError, StockQueryException
from backend.services.analysis_service import run_analysis, run_analysis_staged, AnalysisLogger, _result_cache, _cache_lock
from backend.utils import sanitize_for_json


router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=8)

logger = logging.getLogger("stock_query.sse")

BATCH_CONCURRENCY = 5
SINGLE_STOCK_TIMEOUT = 90  # 单只股票分析超时(秒)
BATCH_TOTAL_TIMEOUT_PER_STOCK = 60  # 批量分析中每只股票分配的总超时(秒)


class AnalysisRequest(BaseModel):
    stock_input: str
    position_status: str = "未持有"
    cost_price: Optional[float] = None


class BatchAnalysisRequest(BaseModel):
    stocks: List[AnalysisRequest] = Field(..., max_length=50)


@router.post("/analysis")
async def analyze(req: AnalysisRequest):
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, run_analysis, req.stock_input, req.position_status, req.cost_price
        )
        return sanitize_for_json(result)
    except ValueError as e:
        msg = str(e)
        if "无效的股票代码" in msg:
            raise InvalidStockCodeError(msg)
        if "无法获取" in msg or "数据不足" in msg:
            raise DataInsufficientError(msg)
        raise StockQueryException(msg)
    except Exception as e:
        traceback.print_exc()
        raise AnalysisFailedError(str(e))


@router.get("/analysis/cache")
async def get_cached_analysis(stock_input: str, position_status: str = "未持有", cost_price: Optional[float] = None):
    """查询分析结果缓存 — 双写缓存确保通过原始输入或解析后代码都能命中"""
    from datetime import datetime
    cache_key = (stock_input, position_status, cost_price)
    with _cache_lock:
        if cache_key in _result_cache:
            cached_result, cached_time = _result_cache[cache_key]
            age_seconds = (datetime.now() - cached_time).total_seconds()
            if age_seconds < 600:
                logger.info(f"缓存命中: {stock_input}, age={age_seconds:.0f}s")
                return {"cached": True, "age_seconds": int(age_seconds), "result": sanitize_for_json(cached_result)}
    logger.info(f"缓存未命中: {stock_input}, key={cache_key}")
    return {"cached": False}


@router.post("/analysis/batch")
async def batch_analyze(req: BatchAnalysisRequest):
    loop = asyncio.get_running_loop()

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
        raise StockQueryException("股票列表不能为空")

    total = len(req.stocks)
    progress_queue: asyncio.Queue = asyncio.Queue()
    completed_count = 0
    all_errors: List[dict] = []
    all_summaries: List[dict] = []
    lock = asyncio.Lock()

    async def run_single(i: int, stock_req: AnalysisRequest):
        nonlocal completed_count
        loop = asyncio.get_running_loop()
        try:
            logger.info(f"BatchQuick: 开始分析 {stock_req.stock_input}")
            await progress_queue.put({
                "type": "analyzing",
                "current": i,
                "total": total,
                "stock_input": stock_req.stock_input,
                "index": i,
            })

            def _run(sr=stock_req):
                return run_analysis(sr.stock_input, sr.position_status, sr.cost_price, skip_signal_cache=True)

            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(_executor, _run),
                    timeout=BATCH_TOTAL_TIMEOUT_PER_STOCK,
                )
            except asyncio.TimeoutError:
                logger.warning(f"BatchQuick: 分析超时 {stock_req.stock_input} ({BATCH_TOTAL_TIMEOUT_PER_STOCK}s)")
                err = {"stock_input": stock_req.stock_input, "error": f"分析超时({BATCH_TOTAL_TIMEOUT_PER_STOCK}s)", "index": i}
                async with lock:
                    completed_count += 1
                    all_errors.append(err)
                await progress_queue.put({
                    "type": "error",
                    "current": completed_count,
                    "total": total,
                    "error": err,
                })
                return
            signal = result.get("trading_signal", {})
            signal_text = signal.get("signal_text", "")
            summary = {
                "stock_code": result.get("stock_code", stock_req.stock_input),
                "stock_name": result.get("stock_name", ""),
                "signal_text": signal_text,
                "score": signal.get("score", 0),
                "action_gate": signal.get("action_gate", ""),
                "recommendation": result.get("analysis", {}).get("recommendation", ""),
                "index": i,
            }
            async with lock:
                completed_count += 1
                all_summaries.append(summary)
            logger.info(f"BatchQuick: 分析完成 {stock_req.stock_input}, signal={signal_text}")
            await progress_queue.put({
                "type": "completed",
                "current": completed_count,
                "total": total,
                "summary": summary,
            })
        except Exception as e:
            logger.warning(f"BatchQuick: 分析失败 {stock_req.stock_input}: {e}")
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
        logger.info(f"BatchQuick: 开始批量分析，共 {total} 只")
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
            batch_deadline = asyncio.get_event_loop().time() + total * BATCH_TOTAL_TIMEOUT_PER_STOCK + 30
            while sent_completed < total:
                remaining = batch_deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning(f"BatchQuick: 批量分析总超时，已完成 {sent_completed}/{total}")
                    break
                try:
                    event_data = await asyncio.wait_for(progress_queue.get(), timeout=min(remaining, 15))
                except asyncio.TimeoutError:
                    # 发送心跳，防止前端超时断开
                    yield {"event": "heartbeat", "data": ""}
                    continue
                evt_type = event_data.get("type", "")
                logger.info(f"BatchQuick: 发送SSE事件 type={evt_type}, current={event_data.get('current')}/{event_data.get('total')}, sent_completed={sent_completed}/{total}")
                yield {"event": "progress", "data": json.dumps(event_data, ensure_ascii=False)}
                if evt_type in ("completed", "error"):
                    sent_completed += 1

            logger.info(f"BatchQuick: 所有进度事件已发送，等待任务完成")
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"BatchQuick: 所有任务已完成，开始更新缓存")
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

        success_count = total - len(all_errors)
        logger.info(f"BatchQuick: 批量分析完成，成功 {success_count}，失败 {len(all_errors)}")

        yield {
            "event": "complete",
            "data": json.dumps({
                "total": total,
                "success_count": success_count,
                "error_count": len(all_errors),
                "errors": all_errors,
                "summaries": sorted(all_summaries, key=lambda x: x.get("index", 0)),
            }, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())


@router.get("/analysis/stream")
async def analysis_stream(stock_input: str, position_status: str = "未持有", cost_price: Optional[float] = None):
    from sse_starlette.sse import EventSourceResponse

    logger.info(f"SSE流: 连接建立, stock_input={stock_input}")

    async def event_generator():
        stage_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        analysis_logger = AnalysisLogger()

        def log_callback(entry):
            asyncio.run_coroutine_threadsafe(
                stage_queue.put({"stage": "log", "data": entry}),
                loop,
            )

        analysis_logger.set_callback(log_callback)

        def stage_callback(stage: str, data):
            asyncio.run_coroutine_threadsafe(
                stage_queue.put({"stage": stage, "data": data}),
                loop,
            )

        def _run_staged():
            try:
                stock_code = stock_input  # 供日志使用
                logger.info(f"SSE流: 开始分析 {stock_code}, position={position_status}")
                logger.info("SSE流: 开始执行分析线程")
                run_analysis_staged(stock_input, position_status, cost_price, stage_callback=stage_callback, logger=analysis_logger)
            except Exception as e:
                logger.error(f"SSE流: 分析线程异常: {e}")
                asyncio.run_coroutine_threadsafe(
                    stage_queue.put({"stage": "error", "data": {"error": str(e)}}),
                    loop,
                )

        task = loop.run_in_executor(_executor, _run_staged)

        try:
            while True:
                try:
                    event_data = await asyncio.wait_for(stage_queue.get(), timeout=120)
                    stage = event_data.get("stage")
                    data = event_data.get("data", {})
                    logger.info(f"SSE流: 收到事件 stage={stage}")

                    if stage == "stage_complete":
                        yield {"event": "stage_complete", "data": json.dumps(sanitize_for_json(data), ensure_ascii=False)}
                        logger.info("SSE流: 发送 stage_complete，分析完成")

                        from backend.services.analysis_service import get_analyzer
                        analyzer = get_analyzer()
                        pending = getattr(analyzer, '_pending_stress_test', None)
                        if pending:
                            analyzer._pending_stress_test = None

                            def _run_stress_test(p=pending):
                                try:
                                    from scripts.core.stress_test import MonteCarloStressTest
                                    n_sim = analyzer._stress_test_config.get("n_simulations", 200)
                                    mc = MonteCarloStressTest(n_simulations=n_sim, config=analyzer._stress_test_config)
                                    return mc.run(p["analyzer"], p["history_df"], p["indicators"])
                                except Exception as e:
                                    logger.warning(f"异步压力测试执行失败: {e}")
                                    return None

                            stress_task = loop.run_in_executor(_executor, _run_stress_test)
                            try:
                                stress_result = await asyncio.wait_for(stress_task, timeout=120)
                                if stress_result:
                                    yield {"event": "stress_test_result", "data": json.dumps(sanitize_for_json(stress_result), ensure_ascii=False)}
                            except asyncio.TimeoutError:
                                logger.warning("异步压力测试超时")
                        break
                    elif stage == "error":
                        yield {"event": "error", "data": json.dumps(sanitize_for_json(data), ensure_ascii=False)}
                        logger.info("SSE流: 发送 error 事件")
                        break
                    else:
                        yield {"event": stage, "data": json.dumps(sanitize_for_json(data), ensure_ascii=False)}
                except asyncio.TimeoutError:
                    logger.info("SSE流: 等待事件超时，发送心跳")
                    yield {"event": "heartbeat", "data": ""}
        except (asyncio.CancelledError, GeneratorExit):
            return
        finally:
            logger.info("SSE流: 连接关闭")
            if not task.done():
                task.cancel()

    return EventSourceResponse(event_generator())
