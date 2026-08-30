"""FALCON SDN bandwidth slice status endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import RedisDep, SettingsDep
from app.models.falcon import BandwidthAllocation
from app.services.falcon_service import get_bandwidth_allocation

router = APIRouter(prefix="/api", tags=["falcon"])


@router.get(
    "/falcon/slices",
    response_model=BandwidthAllocation,
    summary="Get SDN bandwidth slice status",
    description="Returns current allocation, usage, and drop counts for all QoS meter slices.",
)
async def get_falcon_slices(
    redis: RedisDep,
    settings: SettingsDep,
) -> BandwidthAllocation:
    """Return the current state of all FALCON SDN meter table slices."""
    return await get_bandwidth_allocation(redis, settings)
