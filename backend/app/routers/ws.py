"""WebSocket endpoint for real-time dashboard telemetry.

Broadcasts DashboardUpdate payloads at ~2 Hz (configurable via
EDGE_WS_UPDATE_HZ). The frontend establishes a persistent connection
and renders live updates without HTTP polling overhead.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.dependencies import get_redis, get_settings
from app.services.orchestrator import get_latest_dashboard_update

logger = logging.getLogger("ws.dashboard")

router = APIRouter(tags=["websocket"])

# Track active connections for monitoring
_active_connections: list[WebSocket] = []


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    """Persistent WebSocket connection for the Digital Twin dashboard.

    Streams DashboardUpdate JSON payloads at a configurable rate.
    Handles disconnection gracefully and supports auto-reconnect.
    """
    await websocket.accept()
    _active_connections.append(websocket)
    logger.info("Dashboard WS connected (total=%d)", len(_active_connections))

    settings = get_settings()
    update_interval = 1.0 / settings.edge_ws_update_hz
    sequence = 0

    try:
        # Get a Redis client for this connection
        async for redis in get_redis():
            while True:
                try:
                    update = await get_latest_dashboard_update(redis, settings)
                    payload = {
                        "type": "update",
                        "sequence": sequence,
                        "data": json.loads(
                            json.dumps(update.model_dump(mode="json"), default=str)
                        ),
                    }
                    await websocket.send_json(payload)
                    sequence += 1
                except WebSocketDisconnect:
                    raise
                except Exception:
                    logger.error("WS broadcast error", exc_info=True)
                    # Send error message but keep connection alive
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "sequence": sequence,
                            "data": "Internal telemetry error",
                        })
                    except Exception:
                        break

                await asyncio.sleep(update_interval)

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _active_connections:
            _active_connections.remove(websocket)
        logger.info("Dashboard WS disconnected (remaining=%d)", len(_active_connections))


@router.get("/api/ws/status", tags=["websocket"])
async def ws_status() -> dict:
    """Return the number of active WebSocket connections."""
    return {"active_connections": len(_active_connections)}
