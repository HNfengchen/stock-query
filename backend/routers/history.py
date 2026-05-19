import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import asyncio

from backend.exceptions import InvalidStockCodeError, DataInsufficientError, StockQueryException
from backend.services.history_service import (
    load_watchlist,
    add_to_watchlist,
    update_watchlist,
    delete_from_watchlist,
)
from backend.services.analysis_service import get_fetcher

router = APIRouter()

logger = logging.getLogger("stock_query.history")


class WatchlistRequest(BaseModel):
    stock_input: str
    position_status: str = "未持有"
    cost_price: Optional[float] = None


class WatchlistUpdateRequest(BaseModel):
    position_status: Optional[str] = None
    cost_price: Optional[float] = None


@router.get("/watchlist")
async def get_watchlist():
    watchlist = load_watchlist()
    logger.info(f"Watchlist: 加载自选股列表, count={len(watchlist)}")
    return watchlist


@router.post("/watchlist")
async def create_watchlist_item(req: WatchlistRequest):
    try:
        fetcher = get_fetcher()
        loop = asyncio.get_running_loop()
        stock_code, stock_name, _ = await loop.run_in_executor(
            None, fetcher.resolve_stock_code, req.stock_input
        )
        item = add_to_watchlist(stock_code, stock_name, req.position_status, req.cost_price)
        return item
    except ValueError as e:
        msg = str(e)
        if "无效的股票代码" in msg:
            raise InvalidStockCodeError(msg)
        raise StockQueryException(msg)
    except Exception as e:
        msg = str(e)
        if "无法识别" in msg or "无效" in msg:
            raise InvalidStockCodeError(f"无法识别股票 '{req.stock_input}'，请检查输入")
        raise StockQueryException(f"添加股票失败: {msg}")


@router.put("/watchlist/{stock_code}")
async def update_watchlist_item(stock_code: str, req: WatchlistUpdateRequest):
    try:
        item = update_watchlist(stock_code, req.position_status, req.cost_price)
        logger.info(f"Watchlist: 更新股票 {stock_code}")
        return item
    except ValueError as e:
        raise DataInsufficientError(str(e))


@router.delete("/watchlist/{stock_code}")
async def delete_watchlist_item(stock_code: str):
    delete_from_watchlist(stock_code)
    logger.info(f"Watchlist: 删除股票 {stock_code}")
    return {"message": "deleted"}
