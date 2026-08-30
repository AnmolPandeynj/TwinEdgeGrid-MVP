"""Tests for FALCON traffic policing middleware and D-FALCON service."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.models.falcon import MeterSlice
from app.services.falcon_service import (
    d_falcon_reallocation,
    get_all_meter_slices,
    init_meter_tables,
)


class TestMeterSliceModel:
    """Test MeterSlice computed properties."""

    def test_utilization_normal(self):
        s = MeterSlice(name="data", allocated_bandwidth=300, current_usage=150)
        assert s.utilization == 0.5

    def test_utilization_zero_allocation(self):
        s = MeterSlice(name="data", allocated_bandwidth=0, current_usage=0)
        assert s.utilization == 0.0

    def test_utilization_overloaded(self):
        s = MeterSlice(name="video", allocated_bandwidth=400, current_usage=500)
        assert s.utilization == 1.25

    def test_drop_rate_with_drops(self):
        s = MeterSlice(name="voip", allocated_bandwidth=300, current_usage=80, packet_drop_count=20)
        assert s.drop_rate == 0.2

    def test_drop_rate_zero_traffic(self):
        s = MeterSlice(name="data", allocated_bandwidth=300, current_usage=0, packet_drop_count=0)
        assert s.drop_rate == 0.0

    def test_surplus_underutilized(self):
        s = MeterSlice(name="voip", allocated_bandwidth=300, current_usage=100)
        assert s.surplus == 200

    def test_surplus_overloaded(self):
        s = MeterSlice(name="video", allocated_bandwidth=400, current_usage=500)
        assert s.surplus == 0

    def test_deficit_overloaded(self):
        s = MeterSlice(name="video", allocated_bandwidth=400, current_usage=500)
        assert s.deficit == 100

    def test_deficit_underutilized(self):
        s = MeterSlice(name="data", allocated_bandwidth=300, current_usage=100)
        assert s.deficit == 0


class TestInitMeterTables:
    """Test Redis meter table initialization."""

    @pytest.mark.asyncio
    async def test_init_creates_three_hashes(self, mock_redis, settings):
        await init_meter_tables(mock_redis, settings)
        assert mock_redis.hset.call_count == 3

    @pytest.mark.asyncio
    async def test_init_allocations_match_settings(self, mock_redis, settings):
        await init_meter_tables(mock_redis, settings)
        calls = mock_redis.hset.call_args_list

        # Check video (QoS1) allocation
        video_call = calls[0]
        assert video_call.kwargs["mapping"]["allocated_bandwidth"] == 400

        # Check voip (QoS2) allocation
        voip_call = calls[1]
        assert voip_call.kwargs["mapping"]["allocated_bandwidth"] == 300


class TestDFalconReallocation:
    """Test D-FALCON heuristic bandwidth reallocation."""

    @pytest.mark.asyncio
    async def test_no_reallocation_when_balanced(self, mock_redis, settings):
        """No reallocation should occur when all slices are balanced."""
        mock_redis.hgetall = AsyncMock(side_effect=[
            {"allocated_bandwidth": "400", "current_usage": "200", "packet_drop_count": "0"},
            {"allocated_bandwidth": "300", "current_usage": "150", "packet_drop_count": "0"},
            {"allocated_bandwidth": "300", "current_usage": "150", "packet_drop_count": "0"},
        ])
        events = await d_falcon_reallocation(mock_redis, settings)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_reallocation_on_empty_slices(self, mock_redis, settings):
        """No crash when Redis returns empty data."""
        mock_redis.hgetall = AsyncMock(return_value={})
        events = await d_falcon_reallocation(mock_redis, settings)
        assert len(events) == 0
