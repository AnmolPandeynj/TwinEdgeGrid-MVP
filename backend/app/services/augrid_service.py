"""AuGrid LSTM load prediction service with CPU-aware task routing.

Implements the core Edge-Cloud offloading logic:
- Monitor edge CPU utilization via psutil
- Route LSTM inference locally if CPU < threshold (80%)
- Offload to Celery cloud worker if CPU ≥ threshold
- Track prediction history for dashboard visualization
- Normalize inputs / denormalize outputs using saved scaler params
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time

import psutil
from redis.asyncio import Redis

from app.config import Settings
from app.models.augrid import AuGridState, LoadPrediction

logger = logging.getLogger("augrid.service")

# ── In-memory state (persisted to Redis for dashboard) ──
_prediction_history: list[LoadPrediction] = []
_total_predictions = 0
_edge_predictions = 0
_cloud_predictions = 0
_running_mse_sum = 0.0

# ── Scaler parameters (loaded once from trained weights dir) ──
_SCALER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "lstm", "weights", "scaler_params.json",
)
_scaler_params: dict | None = None


def _load_scaler() -> dict | None:
    """Load scaler parameters from disk if available."""
    global _scaler_params
    if _scaler_params is not None:
        return _scaler_params
    if os.path.exists(_SCALER_PATH):
        with open(_SCALER_PATH) as f:
            _scaler_params = json.load(f)
        logger.info(
            "Scaler loaded: min=%.4f max=%.4f",
            _scaler_params["data_min"], _scaler_params["data_max"],
        )
    else:
        logger.warning("No scaler_params.json found — using raw values")
    return _scaler_params


def _normalize(value: float, params: dict) -> float:
    """Min-Max normalize a single value to [0, 1]."""
    return (value - params["data_min"]) / (params["data_max"] - params["data_min"])


def _denormalize(value: float, params: dict) -> float:
    """Inverse Min-Max transform from [0, 1] back to original scale."""
    return value * (params["data_max"] - params["data_min"]) + params["data_min"]


async def predict_load(
    historical_data: list[float],
    actual_load: float | None,
    settings: Settings,
) -> LoadPrediction:
    """Execute AuGrid LSTM prediction with CPU-aware routing.

    Args:
        historical_data: At least 2 aggregated load values [L(t-2), L(t-1)].
        actual_load: Current actual load for deviation calculation.
        settings: Application settings with CPU threshold.

    Returns:
        LoadPrediction with value, execution location, and metrics.
    """
    global _total_predictions, _edge_predictions, _cloud_predictions, _running_mse_sum

    cpu_usage = psutil.cpu_percent(interval=0.1)
    lookback = historical_data[-2:] if len(historical_data) >= 2 else historical_data

    start = time.monotonic()

    if cpu_usage < settings.edge_cpu_threshold:
        # ── LOCAL EDGE EXECUTION ─────────────────────────
        prediction_value = await _predict_local(lookback)
        location = "edge"
        _edge_predictions += 1
    else:
        # ── CLOUD OFFLOAD VIA CELERY ─────────────────────
        prediction_value = await _predict_cloud(lookback)
        location = "cloud"
        _cloud_predictions += 1

    # Clamp prediction to prevent negative load values (LSTM overshooting 0)
    prediction_value = max(0.0, prediction_value)

    elapsed_ms = (time.monotonic() - start) * 1000
    _total_predictions += 1

    prediction = LoadPrediction(
        predicted_load=prediction_value,
        actual_load=actual_load,
        execution_location=location,
        cpu_at_decision=cpu_usage,
        latency_ms=round(elapsed_ms, 2),
    )

    # Update running RMSE
    if actual_load is not None and actual_load > 0:
        _running_mse_sum += (prediction_value - actual_load) ** 2

    # Keep history bounded
    _prediction_history.append(prediction)
    if len(_prediction_history) > 100:
        _prediction_history.pop(0)

    logger.info(
        "AuGrid predict: location=%s cpu=%.1f%% latency=%.1fms predicted=%.2f",
        location, cpu_usage, elapsed_ms, prediction_value,
    )

    return prediction


async def _predict_local(lookback: list[float]) -> float:
    """Execute LSTM inference locally on the edge node.

    If scaler parameters exist (trained model), normalizes inputs
    before inference and denormalizes the output back to kW.
    """
    import torch
    from lstm.model import load_model

    model = load_model()
    scaler = _load_scaler()

    if scaler is not None:
        # Normalize input values to [0, 1] range the model was trained on
        normalized = [_normalize(v, scaler) for v in lookback]
        input_tensor = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
    else:
        input_tensor = torch.tensor(lookback, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_inference, model, input_tensor)

    if scaler is not None:
        # Denormalize output from [0, 1] back to kW
        result = round(_denormalize(result, scaler), 4)

    return result


def _run_inference(model, input_tensor) -> float:
    """Synchronous inference call (runs in executor thread)."""
    import torch
    with torch.no_grad():
        output = model(input_tensor)
    return round(output.item(), 4)


async def _predict_cloud(lookback: list[float]) -> float:
    """Offload LSTM inference to cloud Celery worker."""
    from app.tasks.predict_load import predict_load_task

    task = predict_load_task.delay(lookback)

    # Non-blocking poll for result (up to 30 seconds max)
    try:
        for _ in range(600):  # 600 * 0.05s = 30s
            if task.ready():
                if task.successful():
                    return task.result.get("predicted_load", 0.0)
                break
            await asyncio.sleep(0.05)
    except Exception:
        logger.error("Cloud prediction failed, using fallback", exc_info=True)

    # Fallback: simple moving average if timeout or failure
    return sum(lookback) / len(lookback) if lookback else 0.0


def get_augrid_state() -> AuGridState:
    """Build current AuGrid state for dashboard telemetry."""
    running_rmse = 0.0
    if _total_predictions > 0:
        running_rmse = math.sqrt(_running_mse_sum / _total_predictions)

    return AuGridState(
        current_prediction=_prediction_history[-1] if _prediction_history else None,
        prediction_history=_prediction_history[-50:],
        running_rmse=round(running_rmse, 4),
        total_predictions=_total_predictions,
        edge_predictions=_edge_predictions,
        cloud_predictions=_cloud_predictions,
    )
