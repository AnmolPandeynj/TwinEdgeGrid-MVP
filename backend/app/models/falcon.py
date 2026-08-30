"""FALCON SDN bandwidth orchestration schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MeterSlice(BaseModel):
    """State of a single SDN OpenFlow meter table slice stored in Redis."""

    name: str = Field(..., description="Slice name: video / voip / data")
    allocated_bandwidth: int = Field(..., ge=0, description="Mbps allocated to this slice")
    current_usage: int = Field(default=0, ge=0, description="Current usage in Mbps")
    packet_drop_count: int = Field(default=0, ge=0)

    @property
    def utilization(self) -> float:
        """Usage as fraction of allocation (0.0–1.0+)."""
        if self.allocated_bandwidth == 0:
            return 0.0
        return self.current_usage / self.allocated_bandwidth

    @property
    def drop_rate(self) -> float:
        """Packet drop rate as fraction of total traffic attempted."""
        total = self.current_usage + self.packet_drop_count
        if total == 0:
            return 0.0
        return self.packet_drop_count / total

    @property
    def surplus(self) -> int:
        """Available bandwidth that can be donated to overloaded slices."""
        return max(0, self.allocated_bandwidth - self.current_usage)

    @property
    def deficit(self) -> int:
        """Bandwidth shortfall (how much more is needed)."""
        return max(0, self.current_usage - self.allocated_bandwidth)


class ReallocationEvent(BaseModel):
    """Record of a D-FALCON heuristic bandwidth reallocation."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    from_slice: str
    to_slice: str
    amount_mbps: int = Field(..., ge=1)


class BandwidthAllocation(BaseModel):
    """Snapshot of global bandwidth distribution across all slices."""

    global_limit: int
    slices: list[MeterSlice]
    recent_reallocations: list[ReallocationEvent] = Field(default_factory=list)
    total_drops: int = Field(default=0, ge=0)


class PacketDropEvent(BaseModel):
    """A single packet drop event from the traffic police middleware."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    traffic_type: str
    payload_size: int
    slice_utilization: float
