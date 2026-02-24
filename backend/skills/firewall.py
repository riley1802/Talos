"""Prompt Injection Firewall — L1 security layer.

Spec § 2.11:
  L1: Keyword/pattern detection (CRITICAL -> lockdown)
  L2: Base64-encoded variant re-scan
  L3: Character ratio check (>30% non-alphanumeric -> flag)
  L4: Length limit (10,000 chars max)

Returns a FirewallResult. On CRITICAL detection, triggers lockdown.
"""
import base64
import logging
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

logger = logging.getLogger(__name__)

PROMPT_MAX_LENGTH = 10000
NON_ALPHANUM_RATIO_THRESHOLD = 0.30


class ThreatLevel(IntEnum):
    """Integer enum so comparison operators work correctly."""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class FirewallResult:
    allowed: bool
    threat_level: ThreatLevel
    detections: list[str] = field(default_factory=list)
    sanitized_text: Optional[str] = None


# Detection patterns: (name, regex, threat_level)
PATTERNS: list[tuple[str, re.Pattern, ThreatLevel]] = [
    # CRITICAL — direct override attempts
    ("SYSTEM_OVERRIDE", re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        re.IGNORECASE
    ), ThreatLevel.CRITICAL),
    ("JAILBREAK_DAN", re.compile(
        r"\bDAN\b.*\b(do|does|doing)\s+anything\s+now",
        re.IGNORECASE
    ), ThreatLevel.CRITICAL),
    ("ROLE_OVERRIDE", re.compile(
        r"(you\s+are\s+now|act\s+as|pretend\s+(to\s+be|you\s+are))\s+(an?\s+)?ai\s+(without|with\s+no)\s+(restrictions?|limits?|filters?)",
        re.IGNORECASE
    ), ThreatLevel.CRITICAL),
    ("PROMPT_LEAK", re.compile(
        r"(repeat|output|print|show|display)\s+(your\s+)?(system\s+prompt|initial\s+instructions?)",
        re.IGNORECASE
    ), ThreatLevel.HIGH),
    # HIGH — manipulation attempts
    ("INSTRUCTION_INJECTION", re.compile(
        r"<\s*(system|user|assistant)\s*>",
        re.IGNORECASE
    ), ThreatLevel.HIGH),
    ("DELIMITER_INJECTION", re.compile(
        r"(\[INST\]|\[\/INST\]|<\|im_start\|>|<\|im_end\|>|###\s*System:)",
        re.IGNORECASE
    ), ThreatLevel.HIGH),
    # MEDIUM — suspicious patterns
    ("UNICODE_OBFUSCATION", re.compile(
        r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]"
    ), ThreatLevel.MEDIUM),
]


def _check_base64(text: str) -> Optional[str]:
    """Attempt to decode base64 segments and return decoded text if found."""
    b64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
    for match in b64_pattern.finditer(text):
        try:
            decoded = base64.b64decode(match.group()).decode("utf-8", errors="ignore")
            if decoded.strip():
                return decoded
        except Exception:
            pass
    return None


def _non_alphanum_ratio(text: str) -> float:
    if not text:
        return 0.0
    non_alphanum = sum(1 for c in text if not c.isalnum() and not c.isspace())
    return non_alphanum / len(text)


_THREAT_LEVEL_NAMES = {
    ThreatLevel.NONE: "NONE",
    ThreatLevel.LOW: "LOW",
    ThreatLevel.MEDIUM: "MEDIUM",
    ThreatLevel.HIGH: "HIGH",
    ThreatLevel.CRITICAL: "CRITICAL",
}


def scan(text: str) -> FirewallResult:
    """Run all firewall layers against the input text."""
    detections: list[str] = []
    max_threat = ThreatLevel.NONE

    # L4: Length limit
    if len(text) > PROMPT_MAX_LENGTH:
        detections.append(f"LENGTH_EXCEEDED:{len(text)}")
        return FirewallResult(
            allowed=False,
            threat_level=ThreatLevel.HIGH,
            detections=detections,
        )

    # L1: Pattern matching
    for name, pattern, level in PATTERNS:
        if pattern.search(text):
            detections.append(name)
            if level > max_threat:
                max_threat = level

    # L2: Base64 re-scan
    decoded = _check_base64(text)
    if decoded:
        for name, pattern, level in PATTERNS:
            if pattern.search(decoded):
                detections.append(f"BASE64_{name}")
                if level > max_threat:
                    max_threat = level

    # L3: Character ratio
    ratio = _non_alphanum_ratio(text)
    if ratio > NON_ALPHANUM_RATIO_THRESHOLD:
        detections.append(f"HIGH_NON_ALPHANUM:{ratio:.2f}")
        if ThreatLevel.MEDIUM > max_threat:
            max_threat = ThreatLevel.MEDIUM

    if detections:
        from security.audit_log import log_injection_attempt
        log_injection_attempt(text, ", ".join(detections), severity=_THREAT_LEVEL_NAMES[max_threat])

    if max_threat == ThreatLevel.CRITICAL:
        _trigger_lockdown(detections)
        return FirewallResult(allowed=False, threat_level=max_threat, detections=detections)

    allowed = max_threat < ThreatLevel.HIGH
    return FirewallResult(
        allowed=allowed,
        threat_level=max_threat,
        detections=detections,
        sanitized_text=text if allowed else None,
    )


def _trigger_lockdown(detections: list[str]) -> None:
    import secrets as _secrets
    unlock_code = f"{_secrets.randbelow(10000):04d}"
    logger.critical(
        "SECURITY LOCKDOWN triggered! Detections: %s | Unlock code: %s",
        detections, unlock_code
    )
    from security.audit_log import log_lockdown
    log_lockdown(reason=", ".join(detections), unlock_code=unlock_code)

    # Persist lockdown state to Redis via fire-and-forget background task.
    # Cannot use run_until_complete() here because we are inside the event loop.
    try:
        import asyncio
        from memory.redis_client import set_value
        loop = asyncio.get_running_loop()
        loop.create_task(
            set_value("talos:security:lockdown", {"active": True, "unlock_code": unlock_code})
        )
    except RuntimeError:
        # No running loop — skip Redis persistence (audit log already written)
        logger.warning("No event loop available to persist lockdown to Redis")
