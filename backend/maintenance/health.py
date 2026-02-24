"""Health checks and system metrics collection.

Spec § 4.3 / § 4.5: CPU%, memory%, Redis usage, ChromaDB vector count,
Ollama availability, Gemini quota. Exposed via GET /metrics.
"""
import logging
import os

import psutil

logger = logging.getLogger(__name__)


async def collect() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.getenv("TALOS_ROOT", "/talos"))

    redis_ok, redis_mem_mb = await _redis_health()
    chroma_ok, vector_count = await _chroma_health()
    ollama_ok = await _ollama_health()
    gemini_status = _gemini_status()

    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "mem_total_mb": mem.total // (1024 * 1024),
            "mem_used_mb": mem.used // (1024 * 1024),
            "mem_percent": mem.percent,
            "disk_total_gb": disk.total // (1024 ** 3),
            "disk_used_gb": disk.used // (1024 ** 3),
            "disk_percent": disk.percent,
        },
        "redis": {
            "ok": redis_ok,
            "used_mb": redis_mem_mb,
            "max_mb": 512,
            "percent": round(redis_mem_mb / 512 * 100, 1) if redis_mem_mb >= 0 else -1,
        },
        "chromadb": {
            "ok": chroma_ok,
            "vector_count": vector_count,
            "max_vectors": 100000,
            "percent": round(vector_count / 100000 * 100, 1) if vector_count >= 0 else -1,
        },
        "ollama": {"ok": ollama_ok},
        "gemini": gemini_status,
    }


async def _redis_health() -> tuple[bool, int]:
    try:
        from memory.redis_client import get_client, ping
        if not await ping():
            return False, -1
        r = await get_client()
        info = await r.info("memory")
        mb = int(info.get("used_memory", 0)) // (1024 * 1024)
        return True, mb
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return False, -1


async def _chroma_health() -> tuple[bool, int]:
    try:
        from memory.chroma_client import ping, get_total_vector_count
        if not await ping():
            return False, -1
        count = await get_total_vector_count()
        return True, count
    except Exception as exc:
        logger.warning("ChromaDB health check failed: %s", exc)
        return False, -1


async def _ollama_health() -> bool:
    try:
        from intelligence.ollama_client import is_available
        return await is_available()
    except Exception:
        return False


def _gemini_status() -> dict:
    try:
        from intelligence.gemini_client import get_status
        return get_status()
    except Exception:
        return {"available": False}
