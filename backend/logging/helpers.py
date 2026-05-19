import logging
from typing import Optional, Any

from backend.logging.trace import get_trace_id, get_span_id
from backend.logging.sensitive import sanitize_data


def log_business(
    action: str,
    operator: str = '',
    target_type: str = '',
    target_id: str = '',
    before_data: Any = None,
    after_data: Any = None,
    extra: dict = None,
    level: str = 'INFO',
):
    logger = logging.getLogger('stock_query.business')

    log_data = {
        'action': action,
        'operator': operator,
        'target_type': target_type,
        'target_id': target_id,
    }

    if before_data is not None:
        log_data['before'] = sanitize_data(before_data)
    if after_data is not None:
        log_data['after'] = sanitize_data(after_data)
    if extra:
        log_data['extra'] = sanitize_data(extra)

    trace_id = get_trace_id()
    span_id = get_span_id()

    extra_fields = {
        'log_extra': log_data,
        'log_category': 'business',
        'trace_id': trace_id,
        'span_id': span_id,
    }

    level_map = {
        'TRACE': logging.DEBUG - 5,
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARN': logging.WARNING,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'FATAL': logging.CRITICAL,
    }

    log_level = level_map.get(level.upper(), logging.INFO)
    logger.log(log_level, f'Business: {action}', extra=extra_fields)


def log_system(
    event: str,
    detail: str = '',
    extra: dict = None,
    level: str = 'INFO',
):
    logger = logging.getLogger('stock_query.system')

    log_data = {
        'event': event,
        'detail': detail,
    }

    if extra:
        log_data['data'] = sanitize_data(extra)

    trace_id = get_trace_id()
    span_id = get_span_id()

    extra_fields = {
        'log_extra': log_data,
        'log_category': 'system',
        'trace_id': trace_id,
        'span_id': span_id,
    }

    level_map = {
        'TRACE': logging.DEBUG - 5,
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARN': logging.WARNING,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'FATAL': logging.CRITICAL,
    }

    log_level = level_map.get(level.upper(), logging.INFO)
    logger.log(log_level, f'System: {event}', extra=extra_fields)
