"""SmartPrice market state endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import RedisDep, SettingsDep
from app.models.smartprice import MarketState
from app.services.smartprice_service import get_all_prosumers

router = APIRouter(prefix="/api", tags=["smartprice"])


@router.get(
    "/smartprice/market",
    response_model=MarketState,
    summary="Get current SmartPrice market state",
    description="Returns prosumer states, current pricing, and cooperation metrics.",
)
async def get_market_state(
    redis: RedisDep,
    settings: SettingsDep,
) -> MarketState:
    """Return the current SmartPrice Stackelberg game market snapshot."""
    prosumers = await get_all_prosumers(redis, settings)

    coop_prices = [p.variable_price for p in prosumers if p.cooperation_index > 0.6]
    hoard_prices = [p.variable_price for p in prosumers if p.cooperation_index <= 0.4]

    avg_coop = sum(coop_prices) / len(coop_prices) if coop_prices else 0.0
    avg_hoard = sum(hoard_prices) / len(hoard_prices) if hoard_prices else 0.0

    reduction = 0.0
    if avg_hoard > 0:
        reduction = round((1 - avg_coop / avg_hoard) * 100, 2)

    return MarketState(
        prosumers=prosumers,
        avg_cooperative_price=round(avg_coop, 4),
        avg_hoarding_price=round(avg_hoard, 4),
        price_reduction_pct=reduction,
    )
