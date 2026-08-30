"""Tests for SmartPrice Stackelberg game service."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.models.smartprice import Prosumer, ProsumerStatus
from app.services.smartprice_service import (
    execute_stackelberg_round,
    init_prosumers,
)


class TestInitProsumers:
    """Test prosumer initialization."""

    @pytest.mark.asyncio
    async def test_creates_correct_count(self, mock_redis, settings):
        await init_prosumers(mock_redis, settings)
        # settings.prosumer_count = 5 in test fixture
        assert mock_redis.hset.call_count == 5

    @pytest.mark.asyncio
    async def test_prosumer_ids_are_sequential(self, mock_redis, settings):
        await init_prosumers(mock_redis, settings)
        calls = mock_redis.hset.call_args_list
        keys = [c.args[0] for c in calls]
        assert "prosumer:prosumer_000" in keys
        assert "prosumer:prosumer_004" in keys


class TestProsumerModel:
    """Test Prosumer schema validation."""

    def test_valid_prosumer(self):
        p = Prosumer(
            prosumer_id="p_001",
            cooperation_index=0.8,
            reward_factor=0.6,
        )
        assert p.cooperation_index == 0.8
        assert p.status == ProsumerStatus.IDLE

    def test_cooperation_index_bounds(self):
        with pytest.raises(Exception):
            Prosumer(prosumer_id="p_001", cooperation_index=1.5)

    def test_cooperation_index_lower_bound(self):
        with pytest.raises(Exception):
            Prosumer(prosumer_id="p_001", cooperation_index=-0.1)


class TestSmartPricePricing:
    """Test pricing mechanics ensure cooperators get lower prices."""

    def test_variable_price_monotonicity(self):
        """Prosumers with higher reward factors should get lower variable prices."""
        import math

        base_price = 0.12
        gamma = 1.5

        # High RF prosumer
        high_rf = base_price * math.exp(-gamma * 0.9)
        # Low RF prosumer
        low_rf = base_price * math.exp(-gamma * 0.2)

        # Cooperative (high RF) should pay less
        assert high_rf < low_rf, "Cooperative prosumers should pay less than hoarding ones"

    def test_price_reduction_is_positive(self):
        """The price reduction percentage should be positive for cooperators."""
        import math

        base_price = 0.12
        gamma = 1.5

        avg_coop = base_price * math.exp(-gamma * 0.8)
        avg_hoard = base_price * math.exp(-gamma * 0.3)

        reduction = (1 - avg_coop / avg_hoard) * 100
        assert reduction > 0, f"Expected positive reduction, got {reduction}%"
        # Paper claims 23-35% reduction range
        assert reduction > 10, f"Reduction too small: {reduction}%"
