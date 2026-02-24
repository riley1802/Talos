"""Tier-1 Audit Logger — indefinite retention, append-only JSON-L format.

Spec § 4.1: All security events, skill promotions, and lockdown events
are written here. Tier-1 is never rotated or deleted.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG_DIR = Path(os.getenv("TALOS_LOG_DIR", "/talos/logs"))
TIER1_DIR = LOG_DIR / "tier1"
TIER1_FILE = TIER1_DIR / "audit.jsonl"

logger = logging.getLogger(__name__)


def _ensure_dir() -> None:
    TIER1_DIR.mkdir(parents=True, exist_ok=True)


def _correlation_id() -> str:
    return str(uuid.uuid4())


def log_event(
    event_type: str,
    details: dict,
    severity: str = "INFO",
    correlation_id: Optional[str] = None,
) -> str:
    _ensure_dir()
    cid = correlation_id or _correlation_id()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": cid,
        "severity": severity,
        "event_type": event_type,
        "details": details,
    }
    try:
        with TIER1_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.error("Audit log write failed: %s", exc)
    return cid


def log_security_event(event_type: str, details: dict) -> str:
    return log_event(event_type, details, severity="CRITICAL")


def log_skill_promotion(skill_id: str, promoted_by: str) -> str:
    return log_event(
        "SKILL_PROMOTED",
        {"skill_id": skill_id, "promoted_by": promoted_by},
        severity="INFO",
    )


def log_skill_deprecation(skill_id: str, reason: str) -> str:
    return log_event(
        "SKILL_DEPRECATED",
        {"skill_id": skill_id, "reason": reason},
        severity="WARNING",
    )


def log_lockdown(reason: str, unlock_code: str) -> str:
    return log_event(
        "SECURITY_LOCKDOWN",
        {"reason": reason, "unlock_code_hint": "".join(ch for i, ch in enumerate(unlock_code) if i < 2) + "**"},
        severity="CRITICAL",
    )


def log_injection_attempt(input_text: str, detection: str, severity: str = "HIGH") -> str:
    return log_event(
        "PROMPT_INJECTION_ATTEMPT",
        {"detection_rule": detection, "input_length": len(input_text)},
        severity=severity,
    )
