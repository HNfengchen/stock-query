from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import uuid
from typing import Dict, Set

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
        active_connections[task_id].discard(websocket)
        if not active_connections[task_id]:
            del active_connections[task_id]


async def broadcast_progress(task_id: str, message: dict):
    if task_id not in active_connections:
        return
    disconnected = set()
    for ws in active_connections[task_id]:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    for ws in disconnected:
        active_connections[task_id].discard(ws)
    if not active_connections[task_id]:
        del active_connections[task_id]
