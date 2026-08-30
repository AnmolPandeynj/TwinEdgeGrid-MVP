"""FastAPI dependency injection providers.

Provides Redis connection pool and Settings as async-safe singletons.
Uses the Annotated pattern per FastAPI best practices.
"""

from __future__ import annotations

from typing import Annotated, AsyncIterator

from fastapi import Depends
from redis.asyncio import Redis, ConnectionPool

from app.config import Settings, get_settings

# ── Module-level singletons (set during lifespan) ───────
_redis_pool: ConnectionPool | None = None


async def init_redis_pool(settings: Settings) -> None:
    """Initialize the global Redis connection pool. Called once at startup."""
    global _redis_pool
    _redis_pool = ConnectionPool.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=20,
    )


async def close_redis_pool() -> None:
    """Gracefully close the Redis pool. Called at shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


async def get_redis() -> AsyncIterator[Redis]:
    """Yield a Redis client from the connection pool."""
    if _redis_pool is None:
        raise RuntimeError("Redis pool not initialized — call init_redis_pool() first")
    client = Redis(connection_pool=_redis_pool)
    try:
        yield client
    finally:
        await client.aclose()


# ── Annotated dependency shortcuts ──────────────────────
SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]
