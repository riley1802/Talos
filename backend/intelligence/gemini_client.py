"""Gemini Flash client — cloud escalation with circuit breaker.

Spec § 2.4:
  Circuit breaker states: CLOSED → OPEN → HALF_OPEN
  60-minute cooldown on 429/safety blocks.
  Daily token limit: 50K soft limit.
"""
import asyncio
import logging
import os
import time
from enum import Enum
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3-flash")
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "8192"))
GEMINI_MAX_TOKENS_PER_DAY = int(os.getenv("GEMINI_MAX_TOKENS_PER_DAY", "50000"))
CIRCUIT_BREAKER_COOLDOWN = 3600.0  # 60 minutes


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject requests
    HALF_OPEN = "half_open" # Testing if service recovered


class GeminiCircuitBreaker:
    """State machine: CLOSED → OPEN (on failure) → HALF_OPEN → CLOSED."""

    def __init__(self) -> None:
        self._state = CircuitState.CLOSED
        self._open_since: Optional[float] = None
        self._failure_count = 0
        self._failure_threshold = 3

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - (self._open_since or 0) >= CIRCUIT_BREAKER_COOLDOWN:
                self._state = CircuitState.HALF_OPEN
                logger.info("Gemini circuit breaker: OPEN → HALF_OPEN")
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            self._state = CircuitState.CLOSED
            logger.info("Gemini circuit breaker: → CLOSED")

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold or self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._open_since = time.monotonic()
            logger.warning(
                "Gemini circuit breaker: → OPEN (cooldown %ds)", CIRCUIT_BREAKER_COOLDOWN
            )

    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN


class TokenTracker:
    """Daily token usage counter. Resets at midnight."""

    def __init__(self) -> None:
        self._day_start = self._today()
        self._used = 0

    @staticmethod
    def _today() -> str:
        import datetime
        return datetime.date.today().isoformat()

    def _maybe_reset(self) -> None:
        if self._today() != self._day_start:
            self._day_start = self._today()
            self._used = 0

    def add(self, tokens: int) -> None:
        self._maybe_reset()
        self._used += tokens

    @property
    def used(self) -> int:
        self._maybe_reset()
        return self._used

    def within_limit(self) -> bool:
        return self.used < GEMINI_MAX_TOKENS_PER_DAY

    def remaining(self) -> int:
        return max(0, GEMINI_MAX_TOKENS_PER_DAY - self.used)


_circuit_breaker = GeminiCircuitBreaker()
_token_tracker = TokenTracker()
_primary_model = None
_fallback_model = None
_last_used_model = GEMINI_MODEL


def _get_model(use_fallback: bool = False):
    global _primary_model, _fallback_model
    
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
        
    genai.configure(api_key=GEMINI_API_KEY)
    
    if use_fallback:
        if _fallback_model is None:
            _fallback_model = genai.GenerativeModel(
                model_name=GEMINI_FALLBACK_MODEL,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=GEMINI_MAX_TOKENS,
                    temperature=0.7,
                ),
            )
        return _fallback_model
    else:
        if _primary_model is None:
            _primary_model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=GEMINI_MAX_TOKENS,
                    temperature=0.7,
                ),
            )
        return _primary_model


async def generate(
    prompt: str,
    system_instruction: Optional[str] = None,
) -> str:
    if not _circuit_breaker.is_available():
        raise RuntimeError(
            f"Gemini circuit breaker is OPEN — retry in "
            f"{int(CIRCUIT_BREAKER_COOLDOWN / 60)} minutes"
        )
    if not _token_tracker.within_limit():
        raise RuntimeError(
            f"Gemini daily token limit reached ({GEMINI_MAX_TOKENS_PER_DAY} tokens/day)"
        )

    global _last_used_model
    try:
        model = _get_model(use_fallback=False)

        if system_instruction:
            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                system_instruction=system_instruction,
                generation_config=genai.GenerationConfig(max_output_tokens=GEMINI_MAX_TOKENS),
            )

        response = await asyncio.to_thread(model.generate_content, prompt)
        text = response.text
        _last_used_model = GEMINI_MODEL

        usage = getattr(response, "usage_metadata", None)
        if usage:
            _token_tracker.add(usage.total_token_count or 0)

        _circuit_breaker.record_success()
        logger.debug("Gemini response (%s): %d chars, tokens_used=%d", _last_used_model, len(text), _token_tracker.used)
        return text

    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            logger.warning("Primary model (%s) rate limited/exhausted. Attempting fallback (%s).", GEMINI_MODEL, GEMINI_FALLBACK_MODEL)
            try:
                fallback = _get_model(use_fallback=True)
                if system_instruction:
                    fallback = genai.GenerativeModel(
                        model_name=GEMINI_FALLBACK_MODEL,
                        system_instruction=system_instruction,
                        generation_config=genai.GenerationConfig(max_output_tokens=GEMINI_MAX_TOKENS),
                    )
                fallback_response = await asyncio.to_thread(fallback.generate_content, prompt)
                text = fallback_response.text
                _last_used_model = GEMINI_FALLBACK_MODEL
                
                usage = getattr(fallback_response, "usage_metadata", None)
                if usage:
                    _token_tracker.add(usage.total_token_count or 0)

                _circuit_breaker.record_success()
                logger.debug("Gemini fallback response (%s): %d chars, tokens_used=%d", _last_used_model, len(text), _token_tracker.used)
                return text
                
            except Exception as fallback_exc:
                logger.error("Fallback model (%s) also failed: %s", GEMINI_FALLBACK_MODEL, fallback_exc)
                _circuit_breaker.record_failure()
                raise fallback_exc
        elif "SAFETY" in err_str.upper() or "BLOCKED" in err_str.upper():
            logger.warning("Gemini safety block — tripping circuit breaker")
            _circuit_breaker.record_failure()
        else:
            _circuit_breaker.record_failure()
        raise


def get_status() -> dict:
    return {
        "circuit_state": _circuit_breaker.state.value,
        "tokens_used_today": _token_tracker.used,
        "tokens_remaining": _token_tracker.remaining(),
        "available": _circuit_breaker.is_available() and _token_tracker.within_limit(),
        "active_model": _last_used_model,
        "primary_model": GEMINI_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL
    }
