"""Redis client — short-term memory (512MB LRU)."""
import asyncio
import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_pool: Optional[ConnectionPool] = None


async def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


async def get_client() -> aioredis.Redis:
    pool = await get_pool()
    return aioredis.Redis(connection_pool=pool)


async def ping() -> bool:
    try:
        r = await get_client()
        return await r.ping()
    except Exception as exc:
        logger.error("Redis ping failed: %s", exc)
        return False


async def set_value(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    r = await get_client()
    serialized = json.dumps(value) if not isinstance(value, str) else value
    if ttl:
        return await r.set(key, serialized, ex=ttl)
    return await r.set(key, serialized)


async def get_value(key: str) -> Optional[Any]:
    r = await get_client()
    raw = await r.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


async def delete_key(key: str) -> int:
    r = await get_client()
    return await r.delete(key)


async def set_hash(name: str, mapping: dict) -> None:
    r = await get_client()
    serialized = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in mapping.items()}
    await r.hset(name, mapping=serialized)


async def get_hash(name: str) -> dict:
    r = await get_client()
    raw = await r.hgetall(name)
    result = {}
    for k, v in raw.items():
        try:
            result[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            result[k] = v
    return result


async def publish(channel: str, message: Any) -> None:
    r = await get_client()
    payload = json.dumps(message) if not isinstance(message, str) else message
    await r.publish(channel, payload)


async def wait_for_redis(retries: int = 10, delay: float = 1.0) -> bool:
    for attempt in range(1, retries + 1):
        if await ping():
            logger.info("Redis connected (attempt %d)", attempt)
            return True
        logger.warning("Redis not ready, attempt %d/%d", attempt, retries)
        await asyncio.sleep(delay)
    logger.error("Redis failed to connect after %d attempts", retries)
    return False
