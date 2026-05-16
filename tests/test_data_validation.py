import time
import threading
import pytest

from scripts.core.xtquant_adapter import DataValidator
from scripts.core.circuit_breaker import CircuitBreaker


class TestValidateConsistency:
    def setup_method(self):
        self.validator = DataValidator()

    def test_consistent_data_both_sources(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.005, "volume": 105000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["is_consistent"] is True
        assert result["price_diff_pct"] < 0.01
        assert result["volume_diff_pct"] < 0.20
        assert result["details"]["price"]["within_threshold"] is True
        assert result["details"]["volume"]["within_threshold"] is True

    def test_inconsistent_price(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.50, "volume": 105000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["is_consistent"] is False
        assert result["price_diff_pct"] > 0.01
        assert result["details"]["price"]["within_threshold"] is False
        assert result["details"]["volume"]["within_threshold"] is True

    def test_inconsistent_volume(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.005, "volume": 150000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["is_consistent"] is False
        assert result["volume_diff_pct"] > 0.20
        assert result["details"]["price"]["within_threshold"] is True
        assert result["details"]["volume"]["within_threshold"] is False

    def test_both_inconsistent(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 11.00, "volume": 200000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["is_consistent"] is False
        assert result["price_diff_pct"] > 0.01
        assert result["volume_diff_pct"] > 0.20

    def test_chinese_key_names(self):
        source_a = {"最新价": 10.00, "成交量": 100000}
        source_b = {"最新价": 10.005, "成交量": 105000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["is_consistent"] is True

    def test_mixed_key_names(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"最新价": 10.005, "成交量": 105000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["is_consistent"] is True

    def test_missing_price_in_one_source(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"volume": 105000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["details"]["price"]["within_threshold"] is True
        assert result["is_consistent"] is True

    def test_missing_volume_in_one_source(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.005}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["details"]["volume"]["within_threshold"] is True
        assert result["is_consistent"] is True

    def test_custom_thresholds(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.03, "volume": 130000}

        result_strict = self.validator.validate_consistency(
            source_a, source_b, price_threshold=0.001, volume_threshold=0.10,
        )
        assert result_strict["is_consistent"] is False

        result_loose = self.validator.validate_consistency(
            source_a, source_b, price_threshold=0.05, volume_threshold=0.50,
        )
        assert result_loose["is_consistent"] is True

    def test_zero_close_price(self):
        source_a = {"close": 0, "volume": 100000}
        source_b = {"close": 10.00, "volume": 105000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert result["details"]["price"]["within_threshold"] is True

    def test_result_structure(self):
        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.50, "volume": 150000}

        result = self.validator.validate_consistency(source_a, source_b)

        assert "is_consistent" in result
        assert "price_diff_pct" in result
        assert "volume_diff_pct" in result
        assert "details" in result
        assert "price" in result["details"]
        assert "volume" in result["details"]
        assert "source_a" in result["details"]["price"]
        assert "source_b" in result["details"]["price"]
        assert "diff_pct" in result["details"]["price"]
        assert "within_threshold" in result["details"]["price"]


class TestCircuitBreaker:
    def test_initial_state_healthy(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare"])

        assert cb.is_healthy("xtquant") is True
        assert cb.is_healthy("akshare") is True
        assert cb.get_healthy_sources() == ["xtquant", "akshare"]

    def test_mark_unhealthy(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare"])

        cb.mark_unhealthy("xtquant", "价格偏差过大")

        assert cb.is_healthy("xtquant") is False
        assert cb.is_healthy("akshare") is True
        assert cb.get_healthy_sources() == ["akshare"]

    def test_mark_multiple_unhealthy(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare", "efinance"])

        cb.mark_unhealthy("xtquant", "价格偏差")
        cb.mark_unhealthy("akshare", "成交量偏差")

        assert cb.get_healthy_sources() == ["efinance"]

    def test_timeout_recovery(self):
        cb = CircuitBreaker(timeout=1, source_priority=["xtquant", "akshare"])

        cb.mark_unhealthy("xtquant", "临时故障")

        assert cb.is_healthy("xtquant") is False

        time.sleep(1.1)

        assert cb.is_healthy("xtquant") is True
        assert cb.get_healthy_sources() == ["xtquant", "akshare"]

    def test_get_status(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare"])

        cb.mark_unhealthy("xtquant", "价格偏差")

        status = cb.get_status()

        assert "xtquant" in status
        assert status["xtquant"]["healthy"] is False
        assert status["xtquant"]["reason"] == "价格偏差"
        assert status["xtquant"]["remaining_timeout"] > 0
        assert "akshare" in status
        assert status["akshare"]["healthy"] is True

    def test_get_status_includes_non_priority_sources(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant"])

        cb.mark_unhealthy("unknown_source", "未知原因")

        status = cb.get_status()
        assert "unknown_source" in status
        assert status["unknown_source"]["healthy"] is False

    def test_healthy_sources_priority_order(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare", "efinance"])

        cb.mark_unhealthy("akshare", "故障")

        healthy = cb.get_healthy_sources()
        assert healthy == ["xtquant", "efinance"]

    def test_all_unhealthy(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare"])

        cb.mark_unhealthy("xtquant", "故障A")
        cb.mark_unhealthy("akshare", "故障B")

        assert cb.get_healthy_sources() == []

    def test_unknown_source_is_healthy(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant"])

        assert cb.is_healthy("unknown") is True

    def test_thread_safety(self):
        cb = CircuitBreaker(timeout=300, source_priority=["xtquant", "akshare", "efinance"])
        errors = []

        def mark_sources():
            try:
                for _ in range(100):
                    cb.mark_unhealthy("xtquant", "并发测试")
                    cb.is_healthy("xtquant")
                    cb.get_healthy_sources()
                    cb.get_status()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mark_sources) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestCircuitBreakerRecovery:
    def test_recovery_after_timeout_clears_state(self):
        cb = CircuitBreaker(timeout=1, source_priority=["xtquant"])

        cb.mark_unhealthy("xtquant", "临时故障")
        assert cb.is_healthy("xtquant") is False

        time.sleep(1.1)

        assert cb.is_healthy("xtquant") is True
        status = cb.get_status()
        assert status["xtquant"]["healthy"] is True
        assert status["xtquant"]["remaining_timeout"] == 0

    def test_re_mark_after_recovery(self):
        cb = CircuitBreaker(timeout=1, source_priority=["xtquant"])

        cb.mark_unhealthy("xtquant", "第一次故障")
        time.sleep(1.1)
        assert cb.is_healthy("xtquant") is True

        cb.mark_unhealthy("xtquant", "第二次故障")
        assert cb.is_healthy("xtquant") is False


class TestDataFetcherIntegration:
    def test_validate_consistency_disabled(self):
        from scripts.core.data_fetcher import DataFetcher

        config = {"data_validation": {"enabled": False}}
        fetcher = DataFetcher(config)

        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 11.00, "volume": 200000}

        result = fetcher.validate_consistency(source_a, source_b)
        assert result["is_consistent"] is True

    def test_validate_consistency_with_circuit_breaker(self):
        from scripts.core.data_fetcher import DataFetcher

        config = {
            "data_validation": {
                "enabled": True,
                "price_diff_threshold": 0.01,
                "volume_diff_threshold": 0.20,
                "circuit_breaker_timeout": 300,
            },
        }
        fetcher = DataFetcher(config)

        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.50, "volume": 105000}

        result = fetcher.validate_consistency(
            source_a, source_b, source_a_name="xtquant", source_b_name="akshare",
        )

        assert result["is_consistent"] is False
        if fetcher._circuit_breaker:
            assert fetcher._circuit_breaker.is_healthy("xtquant") is False

    def test_validate_consistency_healthy_source_selected(self):
        from scripts.core.data_fetcher import DataFetcher

        config = {
            "data_validation": {
                "enabled": True,
                "price_diff_threshold": 0.01,
                "volume_diff_threshold": 0.20,
                "circuit_breaker_timeout": 300,
            },
        }
        fetcher = DataFetcher(config)

        source_a = {"close": 10.00, "volume": 100000}
        source_b = {"close": 10.50, "volume": 105000}

        fetcher.validate_consistency(
            source_a, source_b, source_a_name="xtquant", source_b_name="akshare",
        )

        if fetcher._circuit_breaker:
            healthy = fetcher._circuit_breaker.get_healthy_sources()
            assert "akshare" in healthy
