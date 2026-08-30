"""SmartPrice Stackelberg game-theoretic pricing schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProsumerStatus(StrEnum):
    """Prosumer behavioral classification."""

    COOPERATIVE = "cooperative"
    HOARDING = "hoarding"
    SELLING = "selling"
    IDLE = "idle"


class Prosumer(BaseModel):
    """State of a single prosumer in the Stackelberg game."""

    prosumer_id: str = Field(..., min_length=1)
    cooperation_index: float = Field(default=0.5, ge=0.0, le=1.0, description="CI_i")
    reward_factor: float = Field(default=0.5, ge=0.0, description="RF_i")
    variable_price: float = Field(default=0.0, ge=0.0, description="p_var(i)")
    stored_energy_kwh: float = Field(default=5.0, ge=0.0)
    status: ProsumerStatus = Field(default=ProsumerStatus.IDLE)
    total_energy_sold: float = Field(default=0.0, ge=0.0)
    rounds_participated: int = Field(default=0, ge=0)


class PricingResult(BaseModel):
    """Output of a single Stackelberg pricing round."""

    base_price: float = Field(..., ge=0.0, description="p_base")
    deviation_metric: float = Field(default=0.0, ge=0.0, description="Δ")
    purchase_price: float | None = Field(default=None, description="p_buy (if deficit)")
    total_energy_supplied: float = Field(default=0.0, ge=0.0)
    total_energy_demanded: float = Field(default=0.0, ge=0.0)
    deficit: float = Field(default=0.0, ge=0.0)
    prosumers_served: int = Field(default=0, ge=0)
    cooperative_count: int = Field(default=0, ge=0)
    hoarding_count: int = Field(default=0, ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MarketState(BaseModel):
    """Complete SmartPrice market state for dashboard telemetry."""

    prosumers: list[Prosumer] = Field(default_factory=list)
    current_pricing: PricingResult | None = None
    avg_cooperative_price: float = Field(default=0.0, ge=0.0)
    avg_hoarding_price: float = Field(default=0.0, ge=0.0)
    price_reduction_pct: float = Field(default=0.0, description="% reduction for cooperators")
    total_revenue: float = Field(default=0.0, ge=0.0)
    round_number: int = Field(default=0, ge=0)
