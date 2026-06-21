import time
import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.logging.trace import get_trace_id, get_span_id, generate_trace_id, generate_span_id, set_trace_id, set_span_id
from backend.logging.sensitive import sanitize_data


logger = logging.getLogger('stock_query.request')


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, skip_paths: set = None, log_body: bool = False):
        super().__init__(app)
        self.skip_paths = skip_paths or {'/health', '/favicon.ico'}
        self.log_body = log_body

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.skip_paths:
            return await call_next(request)

        start_time = time.monotonic()
        # 优先从 request.state 读取（TraceMiddleware 写入），兼容 BaseHTTPMiddleware 中 contextvar 不自动传播
        trace_id = getattr(request.state, 'trace_id', '') or get_trace_id() or generate_trace_id()
        span_id = getattr(request.state, 'span_id', '') or get_span_id() or generate_span_id()
        set_trace_id(trace_id)
        set_span_id(span_id)

        request_info = {
            'method': request.method,
            'url': str(request.url),
            'path': request.url.path,
            'query_params': dict(request.query_params) if request.query_params else {},
            'client_ip': self._get_client_ip(request),
            'user_agent': request.headers.get('user-agent', ''),
            'content_type': request.headers.get('content-type', ''),
            'trace_id': trace_id,
            'span_id': span_id,
        }

        if self.log_body and request.method in ('POST', 'PUT', 'PATCH'):
            try:
                body = await request.body()
                if body:
                    try:
                        body_data = json.loads(body)
                        request_info['body'] = sanitize_data(body_data)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        request_info['body'] = f'<binary {len(body)} bytes>'
            except Exception:
                logger.warning("请求体读取失败", exc_info=True)
                request_info['body'] = '<unreadable>'

        auth_header = request.headers.get('authorization', '')
        if auth_header:
            request_info['auth_type'] = auth_header.split(' ')[0] if ' ' in auth_header else 'unknown'

        response = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = (time.monotonic() - start_time) * 1000

            log_data = {
                **request_info,
                'status_code': status_code,
                'duration_ms': round(duration_ms, 2),
            }

            extra = {
                'log_extra': log_data,
                'log_category': 'request',
                'trace_id': trace_id,
                'span_id': span_id,
            }

            if status_code >= 500:
                logger.error('API Request', extra=extra)
            elif status_code >= 400:
                logger.warning('API Request', extra=extra)
            else:
                logger.info('API Request', extra=extra)

        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            return forwarded.split(',')[0].strip()
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        client = request.client
        return client.host if client else 'unknown'
