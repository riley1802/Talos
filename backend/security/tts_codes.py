"""TTS (Time-limited Transaction Signing) codes — 4-digit verification for skill promotion.

Spec § 2.7: Codes expire after 5 minutes. Constant-time comparison prevents timing attacks.
"""
import hmac
import logging
import os
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 300  # 5 minutes
_pending_codes: dict[str, tuple[str, float]] = {}  # skill_id → (code, expires_at)


def generate(skill_id: str) -> str:
    """Generate a 4-digit TTS code for a skill promotion request."""
    code = f"{secrets.randbelow(10000):04d}"
    _pending_codes[skill_id] = (code, time.monotonic() + CODE_TTL_SECONDS)
    logger.info("TTS code generated for skill %s (expires in %ds)", skill_id, CODE_TTL_SECONDS)
    return code


def verify(skill_id: str, submitted_code: str) -> bool:
    """Verify a submitted code. Uses constant-time comparison. Clears code on success."""
    entry = _pending_codes.get(skill_id)
    if entry is None:
        logger.warning("TTS verify: no pending code for skill %s", skill_id)
        return False

    stored_code, expires_at = entry
    if time.monotonic() > expires_at:
        del _pending_codes[skill_id]
        logger.warning("TTS verify: code expired for skill %s", skill_id)
        return False

    # Constant-time comparison to prevent timing attacks
    match = hmac.compare_digest(stored_code, submitted_code.strip())
    if match:
        del _pending_codes[skill_id]
        logger.info("TTS code verified for skill %s", skill_id)
    else:
        logger.warning("TTS verify: wrong code for skill %s", skill_id)
    return match


def invalidate(skill_id: str) -> None:
    _pending_codes.pop(skill_id, None)


def purge_expired() -> int:
    now = time.monotonic()
    expired = [k for k, (_, exp) in _pending_codes.items() if now > exp]
    for k in expired:
        del _pending_codes[k]
    return len(expired)
