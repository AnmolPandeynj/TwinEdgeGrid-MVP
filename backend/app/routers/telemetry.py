"""System telemetry endpoint.

Provides real-time edge node hardware metrics for monitoring.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.telemetry import SystemMetrics
from app.services.offload_service import get_system_metrics

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get(
    "/telemetry",
    response_model=SystemMetrics,
    summary="Get edge node system metrics",
)
async def get_telemetry() -> SystemMetrics:
    """Return current CPU, memory, and offload status for the edge node."""
    return get_system_metrics("edge")
