"""Celery task: Cloud-side LSTM load prediction.

Consumed by the Cloud Server's Celery worker pool. Executes the
computationally heavy PyTorch LSTM inference that the Edge Node
offloads when its CPU exceeds the threshold.
"""

from __future__ import annotations

import time

from app.tasks.celery_app import celery_app


@celery_app.task(name="predict_load", bind=True, max_retries=3, default_retry_delay=5)
def predict_load_task(self, historical_data: list[float]) -> dict:
    """Execute AuGrid LSTM prediction on the cloud worker.

    Args:
        historical_data: Last two aggregated load values [L(t-2), L(t-1)].

    Returns:
        Dictionary with predicted load and timing metadata.
    """
    start = time.monotonic()

    try:
        import torch

        from lstm.model import AuGridLSTM, load_model

        model = load_model()
        input_tensor = torch.tensor(historical_data[-2:], dtype=torch.float32)
        input_tensor = input_tensor.unsqueeze(0).unsqueeze(-1)  # (1, 2, 1)

        with torch.no_grad():
            prediction = model(input_tensor)

        elapsed_ms = (time.monotonic() - start) * 1000

        return {
            "predicted_load": round(prediction.item(), 4),
            "latency_ms": round(elapsed_ms, 2),
            "location": "cloud",
        }

    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        # Retry on transient failures
        raise self.retry(exc=exc, countdown=5) from exc
