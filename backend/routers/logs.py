import os
import json
import gzip
import logging
from fastapi import APIRouter, Query, Request
from typing import Optional, List

router = APIRouter(tags=["logs"])

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')

LOG_FILES = {
    'app': 'app.log',
    'request': 'request.log',
    'business': 'business.log',
    'system': 'system.log',
}


def _parse_log_line(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return {
            'raw': line,
            'level': 'UNKNOWN',
            'timestamp': '',
        }


def _read_log_file(
    file_path: str,
    level: Optional[str] = None,
    trace_id: Optional[str] = None,
    keyword: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    entries = []

    if not os.path.exists(file_path):
        return entries

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return entries

    for line in reversed(lines):
        entry = _parse_log_line(line)
        if entry is None:
            continue

        if level and entry.get('level', '').upper() != level.upper():
            continue
        if trace_id and entry.get('trace_id', '') != trace_id:
            continue
        if keyword and keyword.lower() not in json.dumps(entry, ensure_ascii=False, default=str).lower():
            continue
        if start_time and entry.get('timestamp', '') < start_time:
            continue
        if end_time and entry.get('timestamp', '') > end_time:
            continue

        entries.append(entry)
        if len(entries) >= offset + limit:
            break

    if offset > 0:
        entries = entries[offset:]
    return entries[:limit]


@router.get("/logs")
async def query_logs(
    log_type: str = Query('app', description='日志类型: app, request, business, system'),
    level: Optional[str] = Query(None, description='日志级别过滤'),
    trace_id: Optional[str] = Query(None, description='跟踪ID'),
    keyword: Optional[str] = Query(None, description='关键词搜索'),
    start_time: Optional[str] = Query(None, description='开始时间 (ISO格式)'),
    end_time: Optional[str] = Query(None, description='结束时间 (ISO格式)'),
    limit: int = Query(100, ge=1, le=1000, description='返回条数'),
    offset: int = Query(0, ge=0, description='偏移量'),
):
    filename = LOG_FILES.get(log_type)
    if not filename:
        return {"error": f"未知日志类型: {log_type}", "available_types": list(LOG_FILES.keys())}

    file_path = os.path.join(LOG_DIR, filename)
    entries = _read_log_file(
        file_path,
        level=level,
        trace_id=trace_id,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    return {
        "log_type": log_type,
        "total_returned": len(entries),
        "offset": offset,
        "limit": limit,
        "entries": entries,
    }


@router.get("/logs/trace/{trace_id}")
async def query_by_trace_id(
    trace_id: str,
    limit: int = Query(200, ge=1, le=1000),
):
    all_entries = []
    for log_type, filename in LOG_FILES.items():
        file_path = os.path.join(LOG_DIR, filename)
        entries = _read_log_file(file_path, trace_id=trace_id, limit=limit)
        for entry in entries:
            entry['_source'] = log_type
        all_entries.extend(entries)

    all_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return {
        "trace_id": trace_id,
        "total": len(all_entries),
        "entries": all_entries[:limit],
    }


_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
}


@router.post("/logs")
async def receive_logs(request: Request):
    """接收前端上报的日志"""
    error_logger = logging.getLogger("stock_query.error")
    try:
        body = await request.json()
        logs = body.get("logs", [])
        for entry in logs:
            level_str = entry.get("level", "ERROR").upper()
            level = _LEVEL_MAP.get(level_str, logging.ERROR)
            module = entry.get("module", "frontend")
            message = entry.get("message", "")
            timestamp = entry.get("timestamp", "")

            log_entry = f"[FRONTEND][{module}] {message}" + (f" (at {timestamp})" if timestamp else "")

            error_logger.log(level, log_entry)

        return {"status": "ok", "count": len(logs)}
    except Exception as e:
        error_logger.error(f"接收前端日志失败: {e}")
        return {"status": "error", "message": str(e)}
