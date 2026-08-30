"""WebSocket message schemas for real-time dashboard telemetry."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.augrid import AuGridState
from app.models.falcon import BandwidthAllocation
from app.models.smartprice import MarketState
from app.models.telemetry import SystemMetrics


class DashboardUpdate(BaseModel):
    """Complete dashboard state broadcast via WebSocket at ~2 Hz."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    edge_metrics: SystemMetrics
    cloud_metrics: SystemMetrics
    falcon: BandwidthAllocation
    augrid: AuGridState
    smartprice: MarketState
    pipeline_active: bool = Field(default=True)


class WSMessage(BaseModel):
    """Envelope for typed WebSocket messages."""

    type: str = Field(..., description="Message type: 'update' | 'error' | 'status'")
    data: DashboardUpdate | dict | str
    sequence: int = Field(default=0, ge=0)
