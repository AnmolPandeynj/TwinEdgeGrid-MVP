"""SmartPrice Stackelberg game-theoretic pricing service.

Implements the single-leader-multiple-followers Stackelberg game from the
SmartPrice paper. The micro-grid (leader) determines energy pricing while
prosumers (followers) decide whether to cooperate or hoard.

Key formulas:
- Reward Factor: RF_i(t) = α × CI_i(t) + (1-α) × RF_i(t-1)
- Variable Price: p_var(i) = p_base × exp(-γ × RF_i)
- Purchase Price: p_buy = optimized to incentivize prosumer energy release
"""

from __future__ import annotations

import json
import logging
import math
import random
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import Settings
from app.models.smartprice import (
    MarketState,
    PricingResult,
    Prosumer,
    ProsumerStatus,
)

logger = logging.getLogger("smartprice.service")

_round_number = 0
_total_revenue = 0.0


async def init_prosumers(redis: Redis, settings: Settings) -> None:
    """Seed virtual prosumers in Redis with randomized initial states.

    Creates `prosumer_count` prosumers with varied cooperation indices
    and stored energy levels to simulate a diverse community.
    """
    for i in range(settings.prosumer_count):
        prosumer = Prosumer(
            prosumer_id=f"prosumer_{i:03d}",
            cooperation_index=round(random.uniform(0.2, 0.9), 3),
            reward_factor=round(random.uniform(0.3, 0.7), 3),
            stored_energy_kwh=round(random.uniform(0.5, 3.0), 2), # Lowered to trigger deficit more frequently
            status=ProsumerStatus.IDLE,
        )
        await redis.hset(
            f"prosumer:{prosumer.prosumer_id}",
            mapping=prosumer.model_dump(mode="json"),
        )
    logger.info("Initialized %d virtual prosumers", settings.prosumer_count)


async def get_all_prosumers(redis: Redis, settings: Settings) -> list[Prosumer]:
    """Retrieve all prosumer states from Redis."""
    prosumers = []
    for i in range(settings.prosumer_count):
        pid = f"prosumer_{i:03d}"
        data = await redis.hgetall(f"prosumer:{pid}")
        if data:
            prosumers.append(Prosumer(
                prosumer_id=data.get("prosumer_id", pid),
                cooperation_index=float(data.get("cooperation_index", 0.5)),
                reward_factor=float(data.get("reward_factor", 0.5)),
                variable_price=float(data.get("variable_price", 0.0)),
                stored_energy_kwh=float(data.get("stored_energy_kwh", 5.0)),
                status=ProsumerStatus(data.get("status", "idle")),
                total_energy_sold=float(data.get("total_energy_sold", 0.0)),
                rounds_participated=int(data.get("rounds_participated", 0)),
            ))
    return prosumers


async def execute_stackelberg_round(
    predicted_load: float,
    actual_load: float,
    redis: Redis,
    settings: Settings,
) -> MarketState:
    """Execute one round of the Stackelberg pricing game.

    Pipeline:
    1. Recalculate reward factors for all prosumers
    2. Determine base and variable pricing
    3. Handle energy deficit (if applicable)
    4. Simulate prosumer follower responses
    5. Update state and return market snapshot
    """
    global _round_number, _total_revenue

    _round_number += 1
    prosumers = await get_all_prosumers(redis, settings)

    if not prosumers:
        return MarketState(round_number=_round_number)

    alpha = settings.smartprice_alpha
    gamma = settings.smartprice_decay_rate

    # ── Step 1: Reward Factor Recalculation & Battery Recharge ──
    for p in prosumers:
        p.reward_factor = round(
            alpha * p.cooperation_index + (1 - alpha) * p.reward_factor,
            4,
        )
        # Simulate solar generation / battery charging
        p.stored_energy_kwh = round(min(15.0, p.stored_energy_kwh + random.uniform(0.05, 0.2)), 2)

    # ── Step 2: Pricing Determination ────────────────────
    deviation = abs(predicted_load - actual_load) / max(actual_load, 1e-6)
    base_price = _calculate_base_price(actual_load, settings.base_energy_cost)

    for p in prosumers:
        # Cooperative prosumers (high RF) get lower prices
        p.variable_price = round(
            base_price * math.exp(-gamma * p.reward_factor),
            4,
        )

    # ── Step 3: Deficit Management ───────────────────────
    available_supply = sum(p.stored_energy_kwh for p in prosumers)
    deficit = max(0.0, predicted_load - available_supply)
    purchase_price = None

    if deficit > 0:
        purchase_price = _calculate_purchase_price(deficit, prosumers, base_price)

        # ── Step 4: Follower Response Simulation ─────────
        _simulate_follower_responses(prosumers, purchase_price, deficit)

    # ── Classify prosumers and compute stats ─────────────
    cooperative_count = 0
    hoarding_count = 0

    for p in prosumers:
        if p.status == ProsumerStatus.COOPERATIVE or p.status == ProsumerStatus.SELLING:
            cooperative_count += 1
        elif p.status == ProsumerStatus.HOARDING:
            hoarding_count += 1

    # ── Compute price reduction metrics ──────────────────
    coop_prices = [p.variable_price for p in prosumers if p.cooperation_index > 0.6]
    hoard_prices = [p.variable_price for p in prosumers if p.cooperation_index <= 0.4]

    avg_coop_price = sum(coop_prices) / len(coop_prices) if coop_prices else 0.0
    avg_hoard_price = sum(hoard_prices) / len(hoard_prices) if hoard_prices else 0.0

    price_reduction = 0.0
    if avg_hoard_price > 0:
        price_reduction = round((1 - avg_coop_price / avg_hoard_price) * 100, 2)

    total_supplied = sum(p.total_energy_sold for p in prosumers)
    _total_revenue += total_supplied * base_price

    # ── Save updated prosumer states to Redis ────────────
    for p in prosumers:
        p.rounds_participated += 1
        await redis.hset(
            f"prosumer:{p.prosumer_id}",
            mapping=p.model_dump(mode="json"),
        )

    pricing = PricingResult(
        base_price=round(base_price, 4),
        deviation_metric=round(deviation, 4),
        purchase_price=round(purchase_price, 4) if purchase_price else None,
        total_energy_supplied=round(available_supply, 2),
        total_energy_demanded=round(predicted_load, 2),
        deficit=round(deficit, 2),
        prosumers_served=cooperative_count,
        cooperative_count=cooperative_count,
        hoarding_count=hoarding_count,
    )

    market = MarketState(
        prosumers=prosumers,
        current_pricing=pricing,
        avg_cooperative_price=round(avg_coop_price, 4),
        avg_hoarding_price=round(avg_hoard_price, 4),
        price_reduction_pct=price_reduction,
        total_revenue=round(_total_revenue, 2),
        round_number=_round_number,
    )

    logger.info(
        "SmartPrice round %d: base=%.4f deficit=%.2f coop=%d hoard=%d reduction=%.1f%%",
        _round_number, base_price, deficit, cooperative_count, hoarding_count, price_reduction,
    )

    return market


def _calculate_base_price(total_load: float, base_cost: float) -> float:
    """Compute base price tied to generation costs and total load."""
    # Price increases with load (supply-demand)
    load_factor = 1.0 + 0.001 * total_load
    return base_cost * load_factor


def _calculate_purchase_price(
    deficit: float, prosumers: list[Prosumer], base_price: float
) -> float:
    """Compute purchase price to incentivize prosumer energy release."""
    # Premium above base price, scaled by deficit severity
    avg_stored = sum(p.stored_energy_kwh for p in prosumers) / max(len(prosumers), 1)
    scarcity_factor = 1.0 + (deficit / max(avg_stored, 1e-6))
    return base_price * scarcity_factor * 1.2


def _simulate_follower_responses(
    prosumers: list[Prosumer], purchase_price: float, deficit: float
) -> None:
    """Simulate rational prosumer decisions based on offered purchase price.

    Prosumers with higher cooperation indices are more likely to sell.
    Those who sell receive a CI boost for the next round.
    """
    remaining_deficit = deficit

    for p in prosumers:
        if remaining_deficit <= 0:
            p.status = ProsumerStatus.IDLE
            continue

        if p.stored_energy_kwh <= 0.5:
            p.status = ProsumerStatus.IDLE
            continue

        # Decision probability: higher CI → more likely to sell
        sell_probability = 0.3 + 0.5 * p.cooperation_index
        # Higher purchase price also increases willingness
        price_incentive = min(0.2, purchase_price * 0.1)
        total_probability = min(0.95, sell_probability + price_incentive)

        if random.random() < total_probability:
            # Prosumer sells energy
            sell_amount = min(p.stored_energy_kwh * 0.6, remaining_deficit)
            p.stored_energy_kwh = round(p.stored_energy_kwh - sell_amount, 2)
            p.total_energy_sold = round(p.total_energy_sold + sell_amount, 2)
            remaining_deficit -= sell_amount

            # CI boost for cooperation
            p.cooperation_index = round(min(1.0, p.cooperation_index + 0.05), 3)
            p.status = ProsumerStatus.SELLING
        else:
            # Prosumer hoards — CI penalty
            p.cooperation_index = round(max(0.0, p.cooperation_index - 0.02), 3)
            p.status = ProsumerStatus.HOARDING
