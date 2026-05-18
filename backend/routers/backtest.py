from fastapi import APIRouter
from pydantic import BaseModel
import traceback

from backend.exceptions import InvalidStockCodeError, DataInsufficientError, AnalysisFailedError, StockQueryException
from backend.services.backtest_service import run_prediction_validation, run_walk_forward_validation, BacktestTimeoutError
from backend.utils import sanitize_for_json

router = APIRouter()


class BacktestRequest(BaseModel):
    stock_code: str


class WalkForwardRequest(BaseModel):
    stock_code: str
    train_window: int = 60
    test_window: int = 20
    step: int = 20


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        result = run_prediction_validation(req.stock_code)
        return sanitize_for_json(result)
    except BacktestTimeoutError as e:
        raise StockQueryException(str(e))
    except ValueError as e:
        msg = str(e)
        if "无效的股票代码" in msg:
            raise InvalidStockCodeError(msg)
        if "暂无预测数据" in msg or "数据不足" in msg:
            raise DataInsufficientError(msg)
        raise StockQueryException(msg)
    except Exception as e:
        traceback.print_exc()
        raise AnalysisFailedError(str(e))


@router.post("/backtest/walk-forward")
async def walk_forward(req: WalkForwardRequest):
    try:
        result = run_walk_forward_validation(
            stock_code=req.stock_code,
            train_window=req.train_window,
            test_window=req.test_window,
            step=req.step,
        )
        return sanitize_for_json(result)
    except BacktestTimeoutError as e:
        raise StockQueryException(str(e))
    except ValueError as e:
        msg = str(e)
        if "无效的股票代码" in msg:
            raise InvalidStockCodeError(msg)
        if "暂无预测数据" in msg or "数据不足" in msg:
            raise DataInsufficientError(msg)
        raise StockQueryException(msg)
    except Exception as e:
        traceback.print_exc()
        raise AnalysisFailedError(str(e))
