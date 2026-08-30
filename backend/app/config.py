"""Application configuration via Pydantic V2 Settings.

All environment variables are validated at startup. Defaults match .env.example.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Typed, validated application settings loaded from environment / .env file."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Redis ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Edge Node ────────────────────────────────────────
    edge_cpu_threshold: int = Field(default=80, ge=1, le=100)
    edge_host: str = "0.0.0.0"
    edge_port: int = Field(default=8000, ge=1, le=65535)
    edge_ws_update_hz: int = Field(default=2, ge=1, le=60)

    # ── Celery / Cloud ───────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_worker_concurrency: int = Field(default=4, ge=1)

    # ── FALCON SDN ───────────────────────────────────────
    global_bandwidth_limit: int = Field(default=1000, ge=1, description="Mbps (B_global)")
    video_slice_allocation: int = Field(default=400, ge=0, description="QoS1 — Video")
    voip_slice_allocation: int = Field(default=300, ge=0, description="QoS2 — VoIP")
    data_slice_allocation: int = Field(default=300, ge=0, description="QoS3 — Data")
    falcon_realloc_interval_s: float = Field(default=5.0, ge=0.5)
    falcon_drop_threshold: float = Field(default=0.1, ge=0.0, le=1.0)

    # ── SmartPrice ───────────────────────────────────────
    prosumer_count: int = Field(default=50, ge=1)
    base_energy_cost: float = Field(default=0.12, ge=0.0, description="$/kWh (p_base)")
    smartprice_alpha: float = Field(default=0.7, ge=0.0, le=1.0)
    smartprice_decay_rate: float = Field(default=1.5, ge=0.0)

    # ── Latency Simulation ───────────────────────────────
    wan_delay_ms: int = Field(default=50, ge=0)
    wan_jitter_ms: int = Field(default=10, ge=0)


def get_settings() -> Settings:
    """Factory for dependency injection; allows override in tests."""
    return Settings()
