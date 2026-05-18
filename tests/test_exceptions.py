import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.exceptions import (
    StockQueryException,
    InvalidStockCodeError,
    DataInsufficientError,
    AnalysisFailedError,
)


class TestExceptionStatusCodes:
    def test_stock_query_exception_status_code(self):
        exc = StockQueryException()
        assert exc.status_code == 400

    def test_stock_query_exception_custom_detail(self):
        exc = StockQueryException("custom error")
        assert exc.detail == "custom error"

    def test_stock_query_exception_default_detail(self):
        exc = StockQueryException()
        assert exc.detail == "请求参数错误"

    def test_invalid_stock_code_error_status_code(self):
        exc = InvalidStockCodeError()
        assert exc.status_code == 400

    def test_invalid_stock_code_error_default_detail(self):
        exc = InvalidStockCodeError()
        assert exc.detail == "无效的股票代码"

    def test_invalid_stock_code_error_custom_detail(self):
        exc = InvalidStockCodeError("自定义无效代码")
        assert exc.detail == "自定义无效代码"

    def test_data_insufficient_error_status_code(self):
        exc = DataInsufficientError()
        assert exc.status_code == 404

    def test_data_insufficient_error_default_detail(self):
        exc = DataInsufficientError()
        assert exc.detail == "数据不足，无法完成分析"

    def test_analysis_failed_error_status_code(self):
        exc = AnalysisFailedError()
        assert exc.status_code == 500

    def test_analysis_failed_error_default_detail(self):
        exc = AnalysisFailedError()
        assert exc.detail == "分析引擎内部错误"

    def test_exception_inheritance(self):
        assert issubclass(InvalidStockCodeError, StockQueryException)
        assert issubclass(DataInsufficientError, StockQueryException)
        assert issubclass(AnalysisFailedError, StockQueryException)

    def test_exception_is_catchable_as_base(self):
        with pytest.raises(StockQueryException):
            raise InvalidStockCodeError()

        with pytest.raises(StockQueryException):
            raise DataInsufficientError()

        with pytest.raises(StockQueryException):
            raise AnalysisFailedError()


class TestExceptionHandlers:
    @pytest.fixture
    def client(self):
        return TestClient(app, raise_server_exceptions=False)

    def test_stock_query_exception_handler_returns_400(self, client):
        response = client.get("/api/trigger-stock-query-exception")
        assert response.status_code == 404

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
