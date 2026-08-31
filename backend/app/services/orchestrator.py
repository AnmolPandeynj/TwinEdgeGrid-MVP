"""Orchestration pipeline: FALCON → AuGrid → SmartPrice.

Central intelligence hub that chains the three research algorithms into a
continuous data flow on each incoming batch of smart meter readings.

Pipeline sequence:
1. Data passes FALCON traffic police middleware (pre-routing)
2. Aggregate readings into historical load sequence
3. AuGrid: CPU-aware LSTM prediction
4. SmartPrice: Stackelberg game pricing round
5. Cache all results to Redis for WebSocket broadcast
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import Settings
from app.models.augrid import AuGridState
from app.models.smartprice import MarketState
from app.models.telemetry import SystemMetrics, TelemetryBatch
from app.models.websocket import DashboardUpdate
from app.services import augrid_service, smartprice_service, offload_service
from app.services.falcon_service import get_bandwidth_allocation

logger = logging.getLogger("orchestrator")

# ── In-memory load history (circular buffer) ────────────
_load_history: list[float] = []
_MAX_HISTORY = 200


async def process_telemetry_batch(
    batch: TelemetryBatch,
    redis: Redis,
    settings: Settings,
) -> DashboardUpdate:
    """Execute the full orchestration pipeline on a telemetry batch.

    This is the core function called after FALCON traffic policing passes
    the request through. It chains AuGrid and SmartPrice sequentially.
    """
    # ── Step 1: Aggregate batch into load value ──────────
    total_load = sum(r.load_kw for r in batch.readings)
    _load_history.append(total_load)
    if len(_load_history) > _MAX_HISTORY:
        _load_history.pop(0)

    # ── Step 2: AuGrid — LSTM prediction ─────────────────
    if len(_load_history) >= 2:
        prediction = await augrid_service.predict_load(
            historical_data=_load_history,
            actual_load=total_load,
            settings=settings,
        )
        predicted_load = prediction.predicted_load
        is_offloading = prediction.execution_location == "cloud"
    else:
        predicted_load = total_load
        is_offloading = False

    # ── Step 3: SmartPrice — Stackelberg game round ──────
    market = await smartprice_service.execute_stackelberg_round(
        predicted_load=predicted_load,
        actual_load=total_load,
        redis=redis,
        settings=settings,
    )

    # ── Step 4: Collect all subsystem states ─────────────
    edge_metrics = offload_service.get_system_metrics("edge", is_offloading)
    cloud_metrics = SystemMetrics(
        cpu_percent=0.0,  # Cloud metrics would come from cloud node
        memory_percent=0.0,
        is_offloading=False,
        node_type="cloud",
    )
    falcon_state = await get_bandwidth_allocation(redis, settings)
    augrid_state = augrid_service.get_augrid_state()

    # ── Step 5: Build and cache dashboard update ─────────
    update = DashboardUpdate(
        timestamp=datetime.now(timezone.utc),
        edge_metrics=edge_metrics,
        cloud_metrics=cloud_metrics,
        falcon=falcon_state,
        augrid=augrid_state,
        smartprice=market,
    )

    # Cache for WebSocket broadcast
    await redis.set(
        "dashboard:latest",
        json.dumps(update.model_dump(mode="json"), default=str),
        ex=30,
    )

    logger.info(
        "Pipeline complete: load=%.2f predicted=%.2f offloading=%s round=%d",
        total_load, predicted_load, is_offloading, market.round_number,
    )

    return update


async def get_latest_dashboard_update(redis: Redis, settings: Settings) -> DashboardUpdate:
    """Retrieve the latest cached dashboard update, or build a fresh one."""
    cached = await redis.get("dashboard:latest")
    if cached:
        data = json.loads(cached)
        return DashboardUpdate(**data)

    # Build a minimal update if no pipeline data exists yet
    edge_metrics = offload_service.get_system_metrics("edge", False)
    cloud_metrics = SystemMetrics(
        cpu_percent=0.0, memory_percent=0.0, is_offloading=False, node_type="cloud"
    )
    falcon_state = await get_bandwidth_allocation(redis, settings)
    augrid_state = augrid_service.get_augrid_state()
    
    # Fetch current prosumer states instead of returning an empty list
    prosumers = await smartprice_service.get_all_prosumers(redis, settings)

    return DashboardUpdate(
        timestamp=datetime.now(timezone.utc),
        edge_metrics=edge_metrics,
        cloud_metrics=cloud_metrics,
        falcon=falcon_state,
        augrid=augrid_state,
        smartprice=MarketState(prosumers=prosumers),
    )
