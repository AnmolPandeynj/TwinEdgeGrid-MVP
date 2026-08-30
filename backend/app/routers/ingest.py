"""Data ingestion endpoint.

Receives smart meter telemetry batches and feeds them into the
FALCON → AuGrid → SmartPrice orchestration pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.dependencies import RedisDep, SettingsDep
from app.models.telemetry import TelemetryBatch
from app.models.websocket import DashboardUpdate
from app.services.orchestrator import process_telemetry_batch

router = APIRouter(prefix="/api", tags=["ingestion"])


@router.post(
    "/ingest",
    response_model=DashboardUpdate,
    status_code=status.HTTP_200_OK,
    summary="Ingest smart meter telemetry batch",
    description=(
        "Accepts a batch of smart meter readings. The request first passes through "
        "the FALCON traffic police middleware for bandwidth enforcement, then triggers "
        "the full AuGrid → SmartPrice pipeline."
    ),
)
async def ingest_telemetry(
    batch: TelemetryBatch,
    redis: RedisDep,
    settings: SettingsDep,
) -> DashboardUpdate:
    """Process a batch of smart meter readings through the orchestration pipeline."""
    return await process_telemetry_batch(batch, redis, settings)
