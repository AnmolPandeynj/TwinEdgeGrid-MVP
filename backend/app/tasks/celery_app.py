"""Celery application configuration.

Uses Redis as both broker and result backend. Configured for prefork pool
on the Cloud Server to handle CPU-intensive LSTM inference tasks.
"""

from __future__ import annotations

import os

from celery import Celery

# Read from environment; matches docker-compose.yml service config
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "twinedgegrid",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.predict_load"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timeouts
    task_soft_time_limit=25,   # seconds — soft limit
    task_time_limit=30,        # seconds — hard kill

    # Result expiry
    result_expires=300,        # 5 minutes

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,

    # Timezone
    timezone="UTC",
    enable_utc=True,
)
