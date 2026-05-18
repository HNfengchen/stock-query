import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.history_service import (
    add_to_watchlist,
    delete_from_watchlist,
    load_watchlist,
    save_watchlist,
    update_watchlist,
    update_signal_cache,
    batch_update_signal_cache,
)


@pytest.fixture
def temp_data_dir(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    lock_path = tmp_path / "watchlist.lock"
    with patch("backend.services.history_service.DATA_DIR", tmp_path), \
         patch("backend.services.history_service.WATCHLIST_PATH", watchlist_path), \
         patch("backend.services.history_service.LOCK_PATH", lock_path):
        yield tmp_path, watchlist_path


class TestAddToWatchlist:
    def test_add_item_successfully(self, temp_data_dir):
        _, watchlist_path = temp_data_dir
        item = add_to_watchlist("000001", "平安银行", "已持有", 15.5)
        assert item["stock_code"] == "000001"
        assert item["stock_name"] == "平安银行"
        assert item["position_status"] == "已持有"
        assert item["cost_price"] == 15.5
        assert "added_at" in item

    def test_add_item_without_cost_price(self, temp_data_dir):
        item = add_to_watchlist("000002", "万科A", "未持有")
        assert item["cost_price"] is None

    def test_add_duplicate_raises_value_error(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        with pytest.raises(ValueError, match="已在列表中"):
            add_to_watchlist("000001", "平安银行", "未持有")

    def test_add_duplicate_different_name_still_raises(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        with pytest.raises(ValueError, match="已在列表中"):
            add_to_watchlist("000001", "其他名称", "未持有")

    def test_add_multiple_items(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        add_to_watchlist("000002", "万科A", "未持有")
        wl = load_watchlist()
        assert len(wl) == 2

    def test_persists_to_file(self, temp_data_dir):
        _, watchlist_path = temp_data_dir
        add_to_watchlist("000001", "平安银行", "已持有")
        assert watchlist_path.exists()
        with open(watchlist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["stock_code"] == "000001"


class TestDeleteFromWatchlist:
    def test_delete_existing_item(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        add_to_watchlist("000002", "万科A", "未持有")
        delete_from_watchlist("000001")
        wl = load_watchlist()
        assert len(wl) == 1
        assert wl[0]["stock_code"] == "000002"

    def test_delete_nonexistent_item_no_error(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        delete_from_watchlist("999999")
        wl = load_watchlist()
        assert len(wl) == 1

    def test_delete_from_empty_watchlist(self, temp_data_dir):
        delete_from_watchlist("000001")
        wl = load_watchlist()
        assert wl == []

    def test_delete_all_items(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        add_to_watchlist("000002", "万科A", "未持有")
        delete_from_watchlist("000001")
        delete_from_watchlist("000002")
        wl = load_watchlist()
        assert wl == []


class TestLoadWatchlist:
    def test_load_empty_returns_empty_list(self, temp_data_dir):
        wl = load_watchlist()
        assert wl == []

    def test_load_returns_saved_items(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        wl = load_watchlist()
        assert len(wl) == 1
        assert wl[0]["stock_code"] == "000001"


class TestSaveWatchlist:
    def test_save_and_load_roundtrip(self, temp_data_dir):
        data = [
            {"stock_code": "000001", "stock_name": "平安银行", "position_status": "已持有", "cost_price": 15.5},
        ]
        save_watchlist(data)
        loaded = load_watchlist()
        assert loaded == data


class TestUpdateWatchlist:
    def test_update_position_status(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有", 15.5)
        item = update_watchlist("000001", position_status="未持有")
        assert item["position_status"] == "未持有"
        assert item["cost_price"] is None

    def test_update_cost_price(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有", 15.5)
        item = update_watchlist("000001", cost_price=16.0)
        assert item["cost_price"] == 16.0

    def test_update_nonexistent_raises_value_error(self, temp_data_dir):
        with pytest.raises(ValueError, match="不在列表中"):
            update_watchlist("999999", position_status="已持有")

    def test_update_sets_updated_at(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "未持有")
        item = update_watchlist("000001", position_status="已持有")
        assert "updated_at" in item


class TestUpdateSignalCache:
    def test_update_signal_cache(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        signal = {"signal_text": "买入", "score": 85}
        update_signal_cache("000001", "已持有", signal, cost_price=16.0)
        wl = load_watchlist()
        assert wl[0]["cached_signal"] == "买入"
        assert wl[0]["cached_signal_score"] == 85
        assert "cached_signal_time" in wl[0]

    def test_update_signal_cache_nonexistent_no_error(self, temp_data_dir):
        signal = {"signal_text": "买入", "score": 85}
        update_signal_cache("999999", "已持有", signal)


class TestBatchUpdateSignalCache:
    def test_batch_update(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        add_to_watchlist("000002", "万科A", "未持有")
        updates = [
            {"stock_code": "000001", "trading_signal": {"signal_text": "买入", "score": 80}},
            {"stock_code": "000002", "trading_signal": {"signal_text": "卖出", "score": 30}},
        ]
        batch_update_signal_cache(updates)
        wl = load_watchlist()
        assert wl[0]["cached_signal"] == "买入"
        assert wl[1]["cached_signal"] == "卖出"

    def test_batch_update_empty_list(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        batch_update_signal_cache([])
        wl = load_watchlist()
        assert "cached_signal" not in wl[0]

    def test_batch_update_ignores_nonexistent(self, temp_data_dir):
        add_to_watchlist("000001", "平安银行", "已持有")
        updates = [
            {"stock_code": "999999", "trading_signal": {"signal_text": "买入", "score": 80}},
        ]
        batch_update_signal_cache(updates)
        wl = load_watchlist()
        assert len(wl) == 1
