"""3-Strike System — auto-deprecate skills after 3 execution failures.

Spec § 2.8: On 3rd strike, move skill from active/ → deprecated/ and log event.
Strike counts are tracked both in the skill metadata and in Redis for speed.
"""
import logging
import os

logger = logging.getLogger(__name__)

STRIKE_THRESHOLD = int(os.getenv("STRIKE_THRESHOLD", "3"))
REDIS_KEY_PREFIX = "talos:strikes:"


async def record_failure(skill_id: str) -> tuple[int, bool]:
    """
    Record an execution failure for a skill.
    Returns (strike_count, deprecated) where deprecated=True if threshold reached.
    """
    from memory.redis_client import get_value, set_value
    from skills.registry import increment_strike, update_state
    from security.audit_log import log_skill_deprecation

    redis_key = REDIS_KEY_PREFIX + skill_id
    current = int((await get_value(redis_key)) or 0) + 1
    await set_value(redis_key, current)

    # Also update persistent metadata
    strike_count = increment_strike(skill_id)

    logger.warning("Skill %s — strike %d/%d", skill_id, current, STRIKE_THRESHOLD)

    if current >= STRIKE_THRESHOLD:
        update_state(skill_id, "deprecated")
        log_skill_deprecation(skill_id, reason=f"{STRIKE_THRESHOLD} execution failures")
        await set_value(redis_key, 0)  # Reset counter after deprecation
        logger.warning("Skill %s deprecated after %d strikes", skill_id, STRIKE_THRESHOLD)
        return current, True

    return current, False


async def record_success(skill_id: str) -> None:
    """A successful run does NOT clear strikes — only deprecation resets them."""
    pass


async def get_strike_count(skill_id: str) -> int:
    from memory.redis_client import get_value
    return int((await get_value(REDIS_KEY_PREFIX + skill_id)) or 0)


async def clear_strikes(skill_id: str) -> None:
    from memory.redis_client import set_value
    await set_value(REDIS_KEY_PREFIX + skill_id, 0)
