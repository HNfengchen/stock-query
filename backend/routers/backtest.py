from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
import traceback
import asyncio

from backend.exceptions import InvalidStockCodeError, DataInsufficientError, AnalysisFailedError, StockQueryException
from backend.services.backtest_service import run_prediction_validation, run_walk_forward_validation, BacktestTimeoutError
from backend.utils import sanitize_for_json

router = APIRouter()


class BacktestRequest(BaseModel):
    stock_code: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class WalkForwardRequest(BaseModel):
    stock_code: str
    train_window: int = 60
    test_window: int = 20
    step: int = 20


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            run_prediction_validation,
            req.stock_code,
            req.start_date,
            req.end_date,
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


@router.post("/backtest/walk-forward")
async def walk_forward(req: WalkForwardRequest):
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            run_walk_forward_validation,
            req.stock_code,
            req.train_window,
            req.test_window,
            req.step,
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
