"""pytest configuration and shared fixtures."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client for unit testing without a live Redis instance."""
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hget = AsyncMock(return_value="0")
    redis.hincrby = AsyncMock()
    redis.evalsha = AsyncMock(return_value=1)
    redis.script_load = AsyncMock(return_value="test_sha")
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.lpush = AsyncMock()
    redis.ltrim = AsyncMock()
    return redis


@pytest.fixture
def settings():
    """Provide default test settings."""
    from app.config import Settings
    return Settings(
        redis_url="redis://localhost:6379/0",
        edge_cpu_threshold=80,
        global_bandwidth_limit=1000,
        video_slice_allocation=400,
        voip_slice_allocation=300,
        data_slice_allocation=300,
        prosumer_count=5,
        base_energy_cost=0.12,
    )
