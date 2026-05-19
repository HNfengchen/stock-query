class StockQueryException(Exception):
    status_code = 400

    def __init__(self, detail: str = "请求参数错误"):
        self.detail = detail
        super().__init__(self.detail)


class InvalidStockCodeError(StockQueryException):
    status_code = 400

    def __init__(self, detail: str = "无效的股票代码"):
        super().__init__(detail)


class DataInsufficientError(StockQueryException):
    status_code = 404

    def __init__(self, detail: str = "数据不足，无法完成分析"):
        super().__init__(detail)


class AnalysisFailedError(StockQueryException):
    status_code = 500

    def __init__(self, detail: str = "分析引擎内部错误"):
        super().__init__(detail)


class RateLimitError(StockQueryException):
    status_code = 429

    def __init__(self, detail: str = "请求过于频繁"):
        super().__init__(detail)


class TimeoutError(StockQueryException):
    status_code = 408

    def __init__(self, detail: str = "请求超时"):
        super().__init__(detail)


class DatabaseError(StockQueryException):
    status_code = 503

    def __init__(self, detail: str = "数据库服务不可用"):
        super().__init__(detail)
