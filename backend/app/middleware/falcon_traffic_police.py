"""FALCON SDN traffic policing middleware.

Intercepts incoming data ingestion requests and enforces bandwidth limits
using atomic Redis Lua scripts that simulate OpenFlow meter table behavior.
This replaces physical SDN switches (Ryu controller + OpenFlow TCAM) with
software-defined rate limiting for the MVP.

Each incoming payload is classified by traffic type (video/voip/data) and
checked against the corresponding Redis meter hash. If capacity is exceeded,
the request is rejected with HTTP 429, simulating a packet drop.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("falcon.middleware")

# ── Atomic Lua script for meter-table traffic policing ──
# Executes in a single Redis transaction — zero race conditions.
TRAFFIC_POLICE_LUA = """
local meter_key = KEYS[1]
local payload_size = tonumber(ARGV[1])

local allocated = tonumber(redis.call('HGET', meter_key, 'allocated_bandwidth') or '0')
local current = tonumber(redis.call('HGET', meter_key, 'current_usage') or '0')

-- Always track attempted usage so the new deficit formula works
redis.call('HINCRBY', meter_key, 'current_usage', payload_size)

if (current + payload_size) > allocated then
    redis.call('HINCRBY', meter_key, 'packet_drop_count', 1)
    return 0
else
    return 1
end
"""

# Traffic type → Redis meter hash key mapping
TRAFFIC_TYPE_TO_METER = {
    "video": "meter:qos1",
    "voip": "meter:qos2",
    "data": "meter:qos3",
}


class FalconTrafficPoliceMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces SDN bandwidth slicing on ingestion requests.

    Only intercepts POST requests to /api/ingest. All other routes pass through.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._lua_sha: str | None = None

    async def _ensure_script_loaded(self, redis) -> str:
        """Load the Lua script into Redis (cached via EVALSHA)."""
        if self._lua_sha is None:
            self._lua_sha = await redis.script_load(TRAFFIC_POLICE_LUA)
        return self._lua_sha

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercept ingestion requests and apply traffic policing."""
        # Only police the ingestion endpoint
        if request.url.path != "/api/ingest" or request.method != "POST":
            return await call_next(request)

        # Extract traffic type from header or default to "data"
        traffic_type = request.headers.get("X-Traffic-Type", "data").lower()
        if traffic_type not in TRAFFIC_TYPE_TO_METER:
            traffic_type = "data"

        meter_key = TRAFFIC_TYPE_TO_METER[traffic_type]

        # Use simulated Mbps if provided, otherwise estimate from content length
        try:
            simulated_mbps = int(request.headers.get("X-Simulated-Mbps", 0))
        except ValueError:
            simulated_mbps = 0

        if simulated_mbps <= 0:
            content_length = int(request.headers.get("content-length", "256"))
            simulated_mbps = max(1, content_length // 100)

        try:
            # Get Redis client from app state
            redis = request.app.state.redis
            sha = await self._ensure_script_loaded(redis)

            # Execute atomic Lua script
            result = await redis.evalsha(sha, 1, meter_key, str(simulated_mbps))

            if result == 0:
                # Packet dropped — bandwidth exceeded
                logger.info(
                    "FALCON DROP: type=%s meter=%s size=%d",
                    traffic_type, meter_key, content_length
                )
                return Response(
                    content='{"detail":"Bandwidth exceeded — packet dropped (FALCON)"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"X-Falcon-Drop": "true", "X-Traffic-Type": traffic_type},
                )
        except Exception:
            # If Redis is down, let request through (fail-open for MVP)
            logger.warning("FALCON middleware Redis error — failing open", exc_info=True)

        return await call_next(request)
