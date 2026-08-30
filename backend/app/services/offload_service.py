"""CPU monitoring and task offload dispatch service.

Provides real-time system metrics for the Edge and Cloud nodes using psutil.
Also exposes helpers for monitoring the Celery task queue depth.
"""

from __future__ import annotations

import logging

import psutil

from app.models.telemetry import SystemMetrics

logger = logging.getLogger("offload.service")


def get_system_metrics(node_type: str = "edge", is_offloading: bool = False) -> SystemMetrics:
    """Capture current system hardware utilization.

    Args:
        node_type: "edge" or "cloud"
        is_offloading: Whether tasks are currently being dispatched to cloud

    Returns:
        SystemMetrics with CPU, memory, and offload status.
    """
    return SystemMetrics(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        memory_percent=psutil.virtual_memory().percent,
        is_offloading=is_offloading,
        node_type=node_type,
    )


def is_cpu_overloaded(threshold: int = 80) -> bool:
    """Check if edge CPU usage exceeds the offloading threshold."""
    return psutil.cpu_percent(interval=0.1) >= threshold


async def get_celery_queue_depth() -> int:
    """Get the number of pending tasks in the Celery queue.

    Returns 0 if Redis/Celery is unavailable.
    """
    try:
        from app.tasks.celery_app import celery_app
        inspector = celery_app.control.inspect()
        active = inspector.active()
        if active:
            return sum(len(tasks) for tasks in active.values())
    except Exception:
        logger.debug("Could not inspect Celery queue", exc_info=True)
    return 0
