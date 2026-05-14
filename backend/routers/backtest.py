from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import traceback

from backend.services.backtest_service import run_prediction_validation
from backend.utils import sanitize_for_json

router = APIRouter()


class BacktestRequest(BaseModel):
    stock_code: str


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    try:
        result = run_prediction_validation(req.stock_code)
        return sanitize_for_json(result)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
