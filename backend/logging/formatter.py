import json
import traceback
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str = 'stock-query', environment: str = 'production'):
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'service': self.service_name,
            'module': record.name,
            'trace_id': getattr(record, 'trace_id', ''),
            'span_id': getattr(record, 'span_id', ''),
            'message': record.getMessage(),
            'environment': self.environment,
        }

        extra_fields = getattr(record, 'log_extra', {})
        if extra_fields and isinstance(extra_fields, dict):
            log_entry.update(extra_fields)

        log_category = getattr(record, 'log_category', '')
        if log_category:
            log_entry['category'] = log_category

        if record.exc_info and record.exc_info[1] is not None:
            log_entry['error'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else 'Unknown',
                'message': str(record.exc_info[1]),
                'stack_trace': traceback.format_exception(*record.exc_info),
            }

        if record.stack_info:
            log_entry['stack_trace'] = self.formatStack(record.stack_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        'TRACE': '\033[90m',
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARN': '\033[33m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'FATAL': '\033[35m',
        'CRITICAL': '\033[35m',
    }
    RESET = '\033[0m'

    def __init__(self, service_name: str = 'stock-query'):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        trace_id = getattr(record, 'trace_id', '')
        trace_str = f' [{trace_id[:8]}]' if trace_id else ''
        category = getattr(record, 'log_category', '')
        category_str = f' <{category}>' if category else ''

        msg = record.getMessage()

        formatted = (
            f'{color}{record.levelname:<8}{self.RESET} '
            f'{self.formatTime(record, "%Y-%m-%d %H:%M:%S.%f")[:-3]} '
            f'{record.name}{trace_str}{category_str} '
            f'{msg}'
        )

        if record.exc_info and record.exc_info[1] is not None:
            formatted += '\n' + ''.join(traceback.format_exception(*record.exc_info))

        return formatted
