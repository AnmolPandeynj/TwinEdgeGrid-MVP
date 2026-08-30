"""FastAPI application factory — Edge Node entry point.

Assembles all middleware, routers, and background tasks into the main
application instance. Uses the lifespan context manager for startup/shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.config import get_settings
from app.dependencies import close_redis_pool, init_redis_pool
from app.middleware.falcon_traffic_police import FalconTrafficPoliceMiddleware
from app.routers import falcon, ingest, smartprice, telemetry, ws
from app.services.falcon_service import (
    d_falcon_background_loop,
    init_meter_tables,
)
from app.services.smartprice_service import init_prosumers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("twinedgegrid")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize services on startup, cleanup on shutdown."""
    settings = get_settings()

    # ── Startup ──────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("TwinEdgeGrid Edge Node starting...")
    logger.info("CPU offload threshold: %d%%", settings.edge_cpu_threshold)
    logger.info("FALCON bandwidth limit: %d Mbps", settings.global_bandwidth_limit)
    logger.info("Prosumer count: %d", settings.prosumer_count)
    logger.info("=" * 60)

    # Initialize Redis connection pool
    await init_redis_pool(settings)

    # Get a Redis client for initialization
    from app.dependencies import _redis_pool
    redis = Redis(connection_pool=_redis_pool)
    app.state.redis = redis

    # Seed SDN meter tables
    await init_meter_tables(redis, settings)

    # Seed virtual prosumers
    await init_prosumers(redis, settings)

    # Start D-FALCON background reallocation loop
    falcon_task = asyncio.create_task(
        d_falcon_background_loop(redis, settings),
        name="d_falcon_loop",
    )

    logger.info("All subsystems initialized — Edge Node ready")

    yield

    # ── Shutdown ─────────────────────────────────────────
    logger.info("Edge Node shutting down...")
    falcon_task.cancel()
    try:
        await falcon_task
    except asyncio.CancelledError:
        pass
    await redis.aclose()
    await close_redis_pool()
    logger.info("Shutdown complete")


# ── Application Instance ────────────────────────────────
app = FastAPI(
    title="TwinEdgeGrid Edge Node",
    description=(
        "Smart Meter Edge-Aggregation Dashboard and Task Offloading Simulator. "
        "Implements FALCON (SDN bandwidth orchestration), AuGrid (LSTM load prediction), "
        "and SmartPrice (Stackelberg game-theoretic pricing) as a unified pipeline."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware Stack ────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(FalconTrafficPoliceMiddleware)

# ── Routers ─────────────────────────────────────────────
app.include_router(ingest.router)
app.include_router(telemetry.router)
app.include_router(falcon.router)
app.include_router(smartprice.router)
app.include_router(ws.router)


@app.get("/", tags=["health"])
async def health_check() -> dict:
    """Root health check endpoint."""
    return {
        "service": "TwinEdgeGrid Edge Node",
        "status": "operational",
        "version": "0.1.0",
    }
