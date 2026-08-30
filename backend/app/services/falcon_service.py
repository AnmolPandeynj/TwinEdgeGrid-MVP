"""D-FALCON heuristic bandwidth reallocation service.

Implements the Dynamic FALCON algorithm from the FALCON paper. Runs as a
periodic background task that monitors all SDN meter slices and heuristically
reallocates bandwidth from underutilized slices to overloaded ones.

Time complexity: O(S × M × E) where S=switches, M=meters, E=edges.
In the MVP (single switch, 3 meters, 1 edge), this reduces to O(3) per tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import Settings
from app.models.falcon import (
    BandwidthAllocation,
    MeterSlice,
    ReallocationEvent,
)

logger = logging.getLogger("falcon.service")

# Redis hash keys for the three QoS meter slices
METER_KEYS = ["meter:qos1", "meter:qos2", "meter:qos3"]
METER_NAMES = {"meter:qos1": "video", "meter:qos2": "voip", "meter:qos3": "data"}


async def init_meter_tables(redis: Redis, settings: Settings) -> None:
    """Initialize Redis meter table hashes with default allocations.

    Called once at application startup to seed the SDN meter state.
    """
    allocations = {
        "meter:qos1": settings.video_slice_allocation,
        "meter:qos2": settings.voip_slice_allocation,
        "meter:qos3": settings.data_slice_allocation,
    }
    for key, alloc in allocations.items():
        await redis.hset(key, mapping={
            "allocated_bandwidth": alloc,
            "current_usage": 0,
            "packet_drop_count": 0,
        })
    logger.info(
        "FALCON meter tables initialized: video=%d voip=%d data=%d",
        settings.video_slice_allocation,
        settings.voip_slice_allocation,
        settings.data_slice_allocation,
    )


async def get_all_meter_slices(redis: Redis) -> list[MeterSlice]:
    """Read all meter slice states from Redis."""
    slices = []
    for key in METER_KEYS:
        data = await redis.hgetall(key)
        if data:
            slices.append(MeterSlice(
                name=METER_NAMES[key],
                allocated_bandwidth=int(data.get("allocated_bandwidth", 0)),
                current_usage=int(data.get("current_usage", 0)),
                packet_drop_count=int(data.get("packet_drop_count", 0)),
            ))
    return slices


async def get_bandwidth_allocation(redis: Redis, settings: Settings) -> BandwidthAllocation:
    """Build a complete bandwidth allocation snapshot for the dashboard."""
    slices = await get_all_meter_slices(redis)
    total_drops = sum(s.packet_drop_count for s in slices)

    # Read recent reallocations from Redis list
    raw_events = await redis.lrange("falcon:reallocations", 0, 9)
    events = []
    for raw in raw_events:
        import json
        evt = json.loads(raw)
        events.append(ReallocationEvent(**evt))

    return BandwidthAllocation(
        global_limit=settings.global_bandwidth_limit,
        slices=slices,
        recent_reallocations=events,
        total_drops=total_drops,
    )


async def d_falcon_reallocation(redis: Redis, settings: Settings) -> list[ReallocationEvent]:
    """Execute one round of the D-FALCON heuristic reallocation.

    Algorithm:
    1. Scan all meter slices for utilization and drop rates.
    2. Identify overloaded slices (drop_rate > threshold).
    3. Identify underutilized slices (utilization < 50%).
    4. Transfer bandwidth from underutilized → overloaded.
    5. Log reallocation events for dashboard visualization.
    """
    slices = await get_all_meter_slices(redis)
    if not slices:
        return []

    # A slice is overloaded if its attempted usage exceeds its allocation
    overloaded = [s for s in slices if s.deficit > 0]
    underutilized = [s for s in slices if s.utilization < 0.5]

    events: list[ReallocationEvent] = []

    for over_slice in overloaded:
        for under_slice in underutilized:
            if under_slice.surplus <= 0:
                continue

            # Transfer the minimum of what's needed and what's available
            transfer = min(over_slice.deficit, under_slice.surplus)
            if transfer <= 0:
                continue

            # Atomic Redis update
            over_key = f"meter:qos{_slice_qos_number(over_slice.name)}"
            under_key = f"meter:qos{_slice_qos_number(under_slice.name)}"

            await redis.hincrby(over_key, "allocated_bandwidth", transfer)
            await redis.hincrby(under_key, "allocated_bandwidth", -transfer)
            
            # Update in-memory models so surplus/deficit recalculate correctly in the inner loop
            under_slice.allocated_bandwidth -= transfer
            over_slice.allocated_bandwidth += transfer

            event = ReallocationEvent(
                timestamp=datetime.now(timezone.utc),
                from_slice=under_slice.name,
                to_slice=over_slice.name,
                amount_mbps=transfer,
            )
            events.append(event)

            # Store in Redis for dashboard
            import json
            await redis.lpush("falcon:reallocations", json.dumps(event.model_dump(mode="json")))
            await redis.ltrim("falcon:reallocations", 0, 19)

            logger.info(
                "D-FALCON REALLOC: %s → %s (%d Mbps)",
                under_slice.name, over_slice.name, transfer,
            )

    # Reset usage counters periodically (simulates meter table epoch)
    for key in METER_KEYS:
        await redis.hset(key, mapping={"current_usage": 0, "packet_drop_count": 0})

    return events


async def d_falcon_background_loop(redis: Redis, settings: Settings) -> None:
    """Continuous background loop running D-FALCON reallocation.

    Runs every `falcon_realloc_interval_s` seconds.
    """
    logger.info("D-FALCON background loop started (interval=%ss)", settings.falcon_realloc_interval_s)
    while True:
        try:
            await d_falcon_reallocation(redis, settings)
        except Exception:
            logger.error("D-FALCON reallocation error", exc_info=True)
        await asyncio.sleep(settings.falcon_realloc_interval_s)


def _slice_qos_number(name: str) -> int:
    """Map slice name to QoS number."""
    return {"video": 1, "voip": 2, "data": 3}.get(name, 3)
