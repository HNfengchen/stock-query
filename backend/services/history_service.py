import json
import os
import fcntl
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
WATCHLIST_PATH = DATA_DIR / "watchlist.json"
LOCK_PATH = DATA_DIR / "watchlist.lock"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def _watchlist_lock():
    _ensure_data_dir()
    lock_fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield lock_fd
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def _read_watchlist():
    if not WATCHLIST_PATH.exists():
        return []
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_watchlist(data):
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_watchlist() -> List[Dict]:
    with _watchlist_lock():
        return _read_watchlist()


def save_watchlist(data: List[Dict]):
    with _watchlist_lock():
        _write_watchlist(data)


def add_to_watchlist(stock_code: str, stock_name: str, position_status: str, cost_price: Optional[float] = None) -> Dict:
    with _watchlist_lock():
        wl = _read_watchlist()
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
        _write_watchlist(wl)
    return item


def update_watchlist(stock_code: str, position_status: Optional[str] = None, cost_price: Optional[float] = None) -> Dict:
    with _watchlist_lock():
        wl = _read_watchlist()
        for item in wl:
            if item["stock_code"] == stock_code:
                if position_status is not None:
                    item["position_status"] = position_status
                    if position_status == "未持有":
                        item["cost_price"] = None
                if cost_price is not None:
                    item["cost_price"] = cost_price
                item["updated_at"] = datetime.now().isoformat()
                _write_watchlist(wl)
                return item
    raise ValueError(f"{stock_code} 不在列表中")


def update_signal_cache(stock_code: str, position_status: str, trading_signal: Dict, cost_price: Optional[float] = None):
    with _watchlist_lock():
        wl = _read_watchlist()
        for item in wl:
            if item["stock_code"] == stock_code:
                item["cached_signal"] = trading_signal.get("signal_text", "")
                item["cached_signal_score"] = trading_signal.get("score", 0)
                item["cached_signal_time"] = datetime.now().isoformat()
                if position_status is not None:
                    item["position_status"] = position_status
                    if position_status == "未持有":
                        item["cost_price"] = None
                if cost_price is not None:
                    item["cost_price"] = cost_price
                _write_watchlist(wl)
                return


def batch_update_signal_cache(updates: List[Dict]):
    if not updates:
        return
    with _watchlist_lock():
        wl = _read_watchlist()
        now = datetime.now().isoformat()
        code_map = {item["stock_code"]: item for item in wl}
        changed = False
        for upd in updates:
            stock_code = upd.get("stock_code")
            trading_signal = upd.get("trading_signal", {})
            position_status = upd.get("position_status")
            cost_price = upd.get("cost_price")
            item = code_map.get(stock_code)
            if item:
                item["cached_signal"] = trading_signal.get("signal_text", "")
                item["cached_signal_score"] = trading_signal.get("score", 0)
                item["cached_signal_time"] = now
                if position_status is not None:
                    item["position_status"] = position_status
                    if position_status == "未持有":
                        item["cost_price"] = None
                if cost_price is not None:
                    item["cost_price"] = cost_price
                changed = True
        if changed:
            _write_watchlist(wl)


def delete_from_watchlist(stock_code: str):
    with _watchlist_lock():
        wl = _read_watchlist()
        wl = [item for item in wl if item["stock_code"] != stock_code]
        _write_watchlist(wl)
