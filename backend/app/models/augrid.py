"""AuGrid LSTM load forecasting schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LSTMInput(BaseModel):
    """Input payload for the AuGrid LSTM model (lookback=2)."""

    historical_loads: list[float] = Field(
        ..., min_length=2, max_length=2,
        description="Aggregated load values for t-2 and t-1"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LoadPrediction(BaseModel):
    """Output of the AuGrid LSTM prediction step."""

    predicted_load: float = Field(..., description="L̂(t+1) — predicted load for next hour")
    actual_load: float | None = Field(default=None, description="Actual load (if available)")
    execution_location: str = Field(..., description="'edge' or 'cloud'")
    cpu_at_decision: float = Field(..., ge=0.0, le=100.0)
    latency_ms: float = Field(default=0.0, ge=0.0, description="Inference round-trip latency")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def deviation(self) -> float | None:
        """Δ = |L̂(t+1) - L(t+1)| / L(t+1) — deviation metric from AuGrid paper."""
        if self.actual_load is None or self.actual_load == 0:
            return None
        return abs(self.predicted_load - self.actual_load) / self.actual_load


class AuGridState(BaseModel):
    """Aggregated AuGrid state for dashboard telemetry."""

    current_prediction: LoadPrediction | None = None
    prediction_history: list[LoadPrediction] = Field(default_factory=list)
    running_rmse: float = Field(default=0.0, ge=0.0)
    total_predictions: int = Field(default=0, ge=0)
    edge_predictions: int = Field(default=0, ge=0)
    cloud_predictions: int = Field(default=0, ge=0)
