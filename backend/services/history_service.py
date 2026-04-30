import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
WATCHLIST_PATH = DATA_DIR / "watchlist.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_watchlist() -> List[Dict]:
    _ensure_data_dir()
    if not WATCHLIST_PATH.exists():
        return []
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_watchlist(data: List[Dict]):
    _ensure_data_dir()
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_to_watchlist(stock_code: str, stock_name: str, position_status: str, cost_price: Optional[float] = None) -> Dict:
    wl = load_watchlist()
    if any(item["stock_code"] == stock_code for item in wl):
        raise ValueError(f"{stock_code} 已在列表中")
    item = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "position_status": position_status,
        "cost_price": cost_price,
        "added_at": datetime.now().isoformat(),
    }
    wl.append(item)
    save_watchlist(wl)
    return item


def update_watchlist(stock_code: str, position_status: Optional[str] = None, cost_price: Optional[float] = None) -> Dict:
    wl = load_watchlist()
    for item in wl:
        if item["stock_code"] == stock_code:
            if position_status is not None:
                item["position_status"] = position_status
            if cost_price is not None:
                item["cost_price"] = cost_price
            item["updated_at"] = datetime.now().isoformat()
            save_watchlist(wl)
            return item
    raise ValueError(f"{stock_code} 不在列表中")


def delete_from_watchlist(stock_code: str):
    wl = load_watchlist()
    wl = [item for item in wl if item["stock_code"] != stock_code]
    save_watchlist(wl)
