import uuid
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')
span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('span_id', default='')
stock_code_var: contextvars.ContextVar[str] = contextvars.ContextVar('stock_code', default='')

TRACE_ID_HEADER = 'X-Trace-Id'
SPAN_ID_HEADER = 'X-Span-Id'


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def generate_span_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return trace_id_var.get('')


def get_span_id() -> str:
    return span_id_var.get('')


def set_trace_id(tid: str) -> None:
    trace_id_var.set(tid)


def set_span_id(sid: str) -> None:
    span_id_var.set(sid)


def get_stock_code() -> str:
    return stock_code_var.get('')


def set_stock_code(code: str) -> None:
    stock_code_var.set(code)


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_trace = request.headers.get(TRACE_ID_HEADER, '')
        trace_id = incoming_trace if incoming_trace else generate_trace_id()
        span_id = generate_span_id()

        # 通过 request.state 传递，以兼容 Starlette BaseHTTPMiddleware 中 contextvar 不自动传播的问题
        request.state.trace_id = trace_id
        request.state.span_id = span_id

        set_trace_id(trace_id)
        set_span_id(span_id)

        response = await call_next(request)

        response.headers[TRACE_ID_HEADER] = trace_id
        response.headers[SPAN_ID_HEADER] = span_id

        return response
