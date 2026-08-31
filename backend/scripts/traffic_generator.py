"""Stress-test traffic generator.

Blasts simulated smart meter payloads at the Edge Node to trigger:
1. FALCON packet drops (bandwidth exhaustion)
2. CPU threshold breach → Celery offloading
3. SmartPrice market dynamics under load

Usage:
    python scripts/traffic_generator.py --rate 200 --duration 30 --target http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from datetime import datetime, timezone

import httpx


async def generate_traffic(
    target: str,
    rate: int,
    duration: int,
    traffic_mix: dict[str, float] | None = None,
) -> None:
    """Generate simulated smart meter traffic at a specified rate."""
    if traffic_mix is None:
        traffic_mix = {"data": 0.5, "video": 0.3, "voip": 0.2}

    traffic_types = list(traffic_mix.keys())
    traffic_weights = list(traffic_mix.values())

    url = f"{target}/api/ingest"
    interval = 1.0 / rate

    stats = {"accepted": 0, "dropped": 0, "errors": 0, "total": 0}

    print(f"[START] Traffic generator started")
    print(f"   Target:   {url}")
    print(f"   Rate:     {rate} req/s")
    print(f"   Duration: {duration}s")
    print(f"   Mix:      {traffic_mix}")
    print("-" * 50)

    start_time = time.monotonic()

    # Limit concurrency to 20 active requests so Uvicorn doesn't get overwhelmed and drop connections
    semaphore = asyncio.Semaphore(20)

    async with httpx.AsyncClient(timeout=15.0) as client:
        while (time.monotonic() - start_time) < duration:
            batch_start = time.monotonic()

            # Generate batch of readings
            traffic_type = random.choices(traffic_types, weights=traffic_weights, k=1)[0]
            batch_size = random.randint(5, 20)  # Increased to create more load

            payload = {
                "readings": [
                    {
                        "meter_id": f"meter_{random.randint(1, 500):04d}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "load_kw": round(random.uniform(0.5, 50.0), 2),  # Reverted to LSTM training distribution
                        "voltage": round(random.uniform(220.0, 240.0), 1),
                        "traffic_type": traffic_type,
                        "payload_size_bytes": random.randint(128, 2048),
                    }
                    for _ in range(batch_size)
                ],
                "source_node": "traffic_gen",
            }

            def handle_response(t: asyncio.Task, t_type: str, sem: asyncio.Semaphore) -> None:
                sem.release()
                try:
                    resp = t.result()
                    stats["total"] += 1
                    if resp.status_code == 200:
                        stats["accepted"] += 1
                    elif resp.status_code == 429:
                        stats["dropped"] += 1
                    else:
                        stats["errors"] += 1
                except asyncio.CancelledError:
                    pass
                except Exception:
                    stats["total"] += 1
                    stats["errors"] += 1

            # Simulate heavy bandwidth usage to trigger FALCON reallocations
            simulated_mbps = str(random.randint(10, 50))
            
            await semaphore.acquire()
            task = asyncio.create_task(
                client.post(
                    url,
                    json=payload,
                    headers={
                        "X-Traffic-Type": traffic_type,
                        "X-Simulated-Mbps": simulated_mbps
                    },
                )
            )
            task.add_done_callback(lambda t, tt=traffic_type, s=semaphore: handle_response(t, tt, s))

            # Print progress every second
            elapsed = time.monotonic() - start_time
            if int(elapsed) > int(elapsed - interval):
                accept_rate = stats["accepted"] / max(stats["total"], 1) * 100
                print(
                    f"  [{elapsed:5.1f}s] "
                    f"total={stats['total']:4d} "
                    f"accepted={stats['accepted']:4d} "
                    f"dropped={stats['dropped']:4d} "
                    f"errors={stats['errors']:3d} "
                    f"rate={accept_rate:.0f}%"
                )

            # Rate limiting
            sleep_time = interval - (time.monotonic() - batch_start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        # Wait for any pending concurrent requests to finish before closing the client
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    # Final summary
    elapsed = time.monotonic() - start_time
    print("-" * 50)
    print(f"[DONE] Traffic generation complete in {elapsed:.1f}s")
    print(f"   Total:    {stats['total']}")
    print(f"   Accepted: {stats['accepted']} ({stats['accepted']/max(stats['total'],1)*100:.1f}%)")
    print(f"   Dropped:  {stats['dropped']} ({stats['dropped']/max(stats['total'],1)*100:.1f}%)")
    print(f"   Errors:   {stats['errors']}")
    print(f"   Avg rate: {stats['total']/elapsed:.1f} req/s")


def main() -> None:
    parser = argparse.ArgumentParser(description="TwinEdgeGrid Traffic Generator")
    parser.add_argument("--target", default="http://localhost:8000", help="Edge Node URL")
    parser.add_argument("--rate", type=int, default=100, help="Requests per second")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--video-ratio", type=float, default=0.3, help="Video traffic ratio")
    parser.add_argument("--voip-ratio", type=float, default=0.2, help="VoIP traffic ratio")
    parser.add_argument("--data-ratio", type=float, default=0.5, help="Data traffic ratio")

    args = parser.parse_args()

    traffic_mix = {
        "video": args.video_ratio,
        "voip": args.voip_ratio,
        "data": args.data_ratio,
    }

    asyncio.run(generate_traffic(args.target, args.rate, args.duration, traffic_mix))


if __name__ == "__main__":
    main()
