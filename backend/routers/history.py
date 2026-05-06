from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.services.history_service import (
    load_watchlist,
    add_to_watchlist,
    update_watchlist,
    delete_from_watchlist,
)
from backend.services.analysis_service import get_fetcher

router = APIRouter()


class WatchlistRequest(BaseModel):
    stock_input: str
    position_status: str = "未持有"
    cost_price: Optional[float] = None


class WatchlistUpdateRequest(BaseModel):
    position_status: Optional[str] = None
    cost_price: Optional[float] = None


@router.get("/watchlist")
async def get_watchlist():
    return load_watchlist()


@router.post("/watchlist")
async def create_watchlist_item(req: WatchlistRequest):
    try:
        fetcher = get_fetcher()
        stock_code, stock_name, _ = fetcher.resolve_stock_code(req.stock_input)
        item = add_to_watchlist(stock_code, stock_name, req.position_status, req.cost_price)
        return item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/watchlist/{stock_code}")
async def update_watchlist_item(stock_code: str, req: WatchlistUpdateRequest):
    try:
        item = update_watchlist(stock_code, req.position_status, req.cost_price)
        return item
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/watchlist/{stock_code}")
async def delete_watchlist_item(stock_code: str):
    delete_from_watchlist(stock_code)
    return {"message": "deleted"}
