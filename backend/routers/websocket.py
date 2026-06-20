# DEPRECATED: This WebSocket endpoint is not used. Progress updates are handled via SSE.
# This module will be removed in a future version.

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging
import uuid
from typing import Dict, Set

logger = logging.getLogger("stock_query.websocket")

router = APIRouter()

active_connections: Dict[str, Set[WebSocket]] = {}


@router.websocket("/ws/progress/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    if task_id not in active_connections:
        active_connections[task_id] = set()
    active_connections[task_id].add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back or handle client messages if needed
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket异常断开 (task_id={task_id}): {e}")
    finally:
        active_connections[task_id].discard(websocket)
        if not active_connections[task_id]:
            del active_connections[task_id]
        try:
            await websocket.close()
        except Exception:
            # 连接已断开或关闭失败，忽略以避免影响清理流程
            pass


async def broadcast_progress(task_id: str, message: dict):
    if task_id not in active_connections:
        return
    disconnected = set()
    for ws in active_connections[task_id]:
        try:
            await ws.send_json(message)
        except Exception:
            logger.warning(f"WebSocket广播失败 (task_id={task_id})", exc_info=True)
            disconnected.add(ws)
    for ws in disconnected:
        active_connections[task_id].discard(ws)
    if not active_connections[task_id]:
        del active_connections[task_id]
