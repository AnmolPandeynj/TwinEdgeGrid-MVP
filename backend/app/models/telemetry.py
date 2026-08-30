"""Telemetry and system metrics schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class TrafficType(StrEnum):
    """QoS traffic classification matching FALCON meter slices."""

    VIDEO = "video"   # QoS1
    VOIP = "voip"     # QoS2
    DATA = "data"     # QoS3


class SmartMeterReading(BaseModel):
    """A single smart meter telemetry reading from an IoT device."""

    meter_id: str = Field(..., min_length=1, description="Unique meter identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    load_kw: float = Field(..., ge=0.0, description="Instantaneous load in kW")
    voltage: float = Field(default=230.0, ge=0.0)
    traffic_type: TrafficType = Field(default=TrafficType.DATA)
    payload_size_bytes: int = Field(default=256, ge=1, description="Simulated packet size")

    @field_validator("meter_id")
    @classmethod
    def strip_meter_id(cls, v: str) -> str:
        return v.strip()


class TelemetryBatch(BaseModel):
    """Batch of smart meter readings for bulk ingestion."""

    readings: list[SmartMeterReading] = Field(..., min_length=1, max_length=1000)
    source_node: str = Field(default="edge_001")


class SystemMetrics(BaseModel):
    """Real-time hardware utilization metrics from a compute node."""

    cpu_percent: float = Field(..., ge=0.0, le=100.0)
    memory_percent: float = Field(..., ge=0.0, le=100.0)
    is_offloading: bool = Field(default=False, description="True when tasks are being sent to cloud")
    active_celery_tasks: int = Field(default=0, ge=0)
    node_type: str = Field(default="edge")  # "edge" or "cloud"
