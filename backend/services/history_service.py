import json
import os
import fcntl
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
WATCHLIST_PATH = DATA_DIR / "watchlist.json"
LOCK_PATH = DATA_DIR / "watchlist.lock"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _acquire_lock():
    _ensure_data_dir()
    lock_fd = open(LOCK_PATH, "w")
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd


def _release_lock(lock_fd):
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()


def load_watchlist() -> List[Dict]:
    _ensure_data_dir()
    if not WATCHLIST_PATH.exists():
        return []
    lock_fd = _acquire_lock()
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        _release_lock(lock_fd)


def save_watchlist(data: List[Dict]):
    _ensure_data_dir()
    lock_fd = _acquire_lock()
    try:
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    finally:
        _release_lock(lock_fd)


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
