import logging
import traceback

logger = logging.getLogger("stock_query.tasks")

_analyze_stock_task = None
_batch_analyze_task = None


def _analyze_stock_impl(stock_code: str, position_type: str = "未持有", cost_price: float = None) -> dict:
    from backend.services.analysis_service import run_analysis
    from backend.utils import sanitize_for_json

    result = run_analysis(stock_code, position_type, cost_price)
    return sanitize_for_json(result)


def _batch_analyze_impl(stock_codes: list, position_type: str = "未持有", cost_price: float = None) -> list:
    from backend.services.analysis_service import run_analysis
    from backend.utils import sanitize_for_json

    results = []
    for stock_code in stock_codes:
        try:
            result = run_analysis(stock_code, position_type, cost_price)
            results.append(sanitize_for_json(result))
        except Exception as e:
            logger.error(f"批量分析子任务失败 [{stock_code}]: {e}")
            results.append({
                "error": str(e),
                "stock_code": stock_code,
                "position_type": position_type,
            })
    return results


def register_tasks(app):
    global _analyze_stock_task, _batch_analyze_task

    @app.task(bind=True, name="backend.tasks.analyze_stock_task")
    def analyze_stock_task(self, stock_code: str, position_type: str = "未持有", cost_price: float = None) -> dict:
        try:
            self.update_state(state="RUNNING", meta={"stock_code": stock_code})
            return _analyze_stock_impl(stock_code, position_type, cost_price)
        except Exception as e:
            logger.error(f"分析任务失败 [{stock_code}]: {e}\n{traceback.format_exc()}")
            return {
                "error": str(e),
                "stock_code": stock_code,
                "position_type": position_type,
            }

    @app.task(bind=True, name="backend.tasks.batch_analyze_task")
    def batch_analyze_task(self, stock_codes: list, position_type: str = "未持有", cost_price: float = None) -> list:
        results = []
        total = len(stock_codes)
        for i, stock_code in enumerate(stock_codes):
            self.update_state(
                state="RUNNING",
                meta={"current": i + 1, "total": total, "stock_code": stock_code},
            )
            try:
                result = _analyze_stock_impl(stock_code, position_type, cost_price)
                results.append(result)
            except Exception as e:
                logger.error(f"批量分析子任务失败 [{stock_code}]: {e}")
                results.append({
                    "error": str(e),
                    "stock_code": stock_code,
                    "position_type": position_type,
                })
        return results

    _analyze_stock_task = analyze_stock_task
    _batch_analyze_task = batch_analyze_task


def get_analyze_stock_task():
    if _analyze_stock_task is None:
        raise RuntimeError("Celery 未启用，无法执行异步分析任务")
    return _analyze_stock_task


def get_batch_analyze_task():
    if _batch_analyze_task is None:
        raise RuntimeError("Celery 未启用，无法执行批量异步分析任务")
    return _batch_analyze_task
