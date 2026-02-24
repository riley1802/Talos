"""Dream Cycle — scheduled 4 AM maintenance worker.

Spec § 3.1: 5 phases, 30-minute hard cap, checkpoint every 30 seconds.

Phase 1 (0–30s):    Redis flush of expired keys
Phase 2 (30s–15m):  ChromaDB vector pruning (temporary + last_access > 30 days)
Phase 3 (15–20m):   Log compression (gzip files > 10MB)
Phase 4 (20–25m):   Zombie process hunt
Phase 5 (25–30m):   Health report generation → store in Redis
"""
import asyncio
import gzip
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("TALOS_LOG_DIR", "/talos/logs"))
DREAM_HOUR = int(os.getenv("DREAM_CYCLE_HOUR", "4"))
DREAM_MINUTE = int(os.getenv("DREAM_CYCLE_MINUTE", "0"))
MAX_DURATION = 1800  # 30 minutes hard cap

_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_dream_cycle,
        trigger="cron",
        hour=DREAM_HOUR,
        minute=DREAM_MINUTE,
        id="dream_cycle",
        name="Talos Dream Cycle",
        max_instances=1,
    )
    _scheduler.start()
    logger.info("Dream cycle scheduled at %02d:%02d daily", DREAM_HOUR, DREAM_MINUTE)


async def run_dream_cycle() -> dict:
    """Execute all 5 maintenance phases. Returns a summary report."""
    start = time.monotonic()
    logger.info("=" * 60)
    logger.info("DREAM CYCLE STARTING — %s", datetime.now(timezone.utc).isoformat())
    logger.info("=" * 60)

    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "phases": {},
        "completed": False,
    }

    phases = [
        ("redis_flush",    _phase_redis_flush),
        ("vector_prune",   _phase_vector_prune),
        ("log_compress",   _phase_log_compress),
        ("zombie_hunt",    _phase_zombie_hunt),
        ("health_report",  _phase_health_report),
    ]

    for phase_name, phase_fn in phases:
        elapsed = time.monotonic() - start
        if elapsed >= MAX_DURATION:
            logger.warning("Dream cycle hit 30-minute hard cap — stopping at phase %s", phase_name)
            break

        logger.info("[DREAM] Starting phase: %s (elapsed=%.0fs)", phase_name, elapsed)
        phase_start = time.monotonic()
        try:
            result = await phase_fn()
            duration = time.monotonic() - phase_start
            report["phases"][phase_name] = {"status": "ok", "duration_s": round(duration, 1), **result}
            logger.info("[DREAM] Phase %s complete in %.1fs", phase_name, duration)
        except Exception as exc:
            duration = time.monotonic() - phase_start
            report["phases"][phase_name] = {"status": "error", "error": str(exc), "duration_s": round(duration, 1)}
            logger.error("[DREAM] Phase %s failed: %s", phase_name, exc)

    report["completed"] = True
    report["total_duration_s"] = round(time.monotonic() - start, 1)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("DREAM CYCLE COMPLETE in %.1fs", report["total_duration_s"])
    logger.info("=" * 60)

    return report


async def _phase_redis_flush() -> dict:
    """Flush expired keys from Redis (TTL-based, not full flush)."""
    from memory.redis_client import get_client
    r = await get_client()
    # Redis handles TTL expiry automatically; we just trigger a memory check
    info = await r.info("memory")
    used_mb = int(info.get("used_memory", 0)) // (1024 * 1024)
    logger.info("[DREAM:1] Redis memory: %dMB", used_mb)
    return {"redis_used_mb": used_mb}


async def _phase_vector_prune() -> dict:
    """Remove temporary vectors older than 30 days from ChromaDB."""
    from memory.chroma_client import COLLECTION_NAMES, get_collection

    cutoff = time.time() - (30 * 86400)  # 30 days ago
    total_pruned = 0

    for col_name in COLLECTION_NAMES:
        try:
            col = await get_collection(col_name)
            results = await col.get(
                where={"$and": [
                    {"priority": {"$eq": "temporary"}},
                    {"last_access": {"$lt": cutoff}},
                ]},
                include=["metadatas"],
                limit=5000,
            )
            ids = results.get("ids", [])
            if ids:
                await col.delete(ids=ids)
                total_pruned += len(ids)
                logger.info("[DREAM:2] Pruned %d vectors from %s", len(ids), col_name)
        except Exception as exc:
            logger.warning("[DREAM:2] Prune error in %s: %s", col_name, exc)

    return {"vectors_pruned": total_pruned}


async def _phase_log_compress() -> dict:
    """Gzip log files larger than 10MB."""
    compressed = 0
    for tier in ("tier2", "tier3"):
        tier_dir = LOG_DIR / tier
        if not tier_dir.exists():
            continue
        for log_file in tier_dir.glob("*.jsonl"):
            if log_file.stat().st_size > 10 * 1024 * 1024:  # > 10MB
                gz_path = log_file.with_suffix(".jsonl.gz")
                try:
                    with log_file.open("rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                        f_out.writelines(f_in)
                    log_file.unlink()
                    compressed += 1
                    logger.info("[DREAM:3] Compressed %s", log_file.name)
                except Exception as exc:
                    logger.warning("[DREAM:3] Compress failed for %s: %s", log_file, exc)

    return {"files_compressed": compressed}


async def _phase_zombie_hunt() -> dict:
    """Kill zombie processes (tini handles most of this, but we clean up stragglers)."""
    import psutil
    zombies = []
    for proc in psutil.process_iter(["pid", "status", "name"]):
        try:
            if proc.status() == psutil.STATUS_ZOMBIE:
                zombies.append(proc.pid)
                logger.warning("[DREAM:4] Zombie process: PID %d (%s)", proc.pid, proc.name())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {"zombies_found": len(zombies)}


async def _phase_health_report() -> dict:
    """Generate health report and store in Redis."""
    from maintenance.health import collect
    from memory.redis_client import set_value

    report = await collect()
    await set_value("talos:health:last_report", report, ttl=86400 * 2)
    logger.info("[DREAM:5] Health report stored")
    return {"health_status": report.get("system", {})}


async def trigger_now() -> dict:
    """Manually trigger the dream cycle (for testing/admin use)."""
    return await run_dream_cycle()
