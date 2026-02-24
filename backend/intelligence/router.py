"""Model router — decide between local Qwen and cloud Gemini.

Routing logic:
  1. Use Qwen Coder (local) for code, reasoning, and general tasks
  2. Use Qwen VL (local) when images are provided
  3. Escalate to Gemini when:
     - Qwen fails or is unavailable
     - Task is explicitly marked complex
     - Prompt length exceeds local context window
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

LOCAL_CONTEXT_LIMIT_CHARS = 30000  # ~32K tokens for Qwen
ESCALATION_KEYWORDS = {"complex", "analyze", "summarize long", "research"}


async def route(
    prompt: str,
    system: Optional[str] = None,
    model_hint: Optional[str] = None,
    images: Optional[list[str]] = None,
    force_cloud: bool = False,
) -> str:
    """Route prompt to the appropriate model and return the response."""
    from intelligence.vram_mutex import vram_mutex
    from intelligence.ollama_client import generate as ollama_generate, is_available as ollama_ok
    from intelligence.gemini_client import generate as gemini_generate, get_status

    if force_cloud:
        return await _call_gemini(prompt, system)

    # Vision request → Qwen VL
    if images:
        return await _call_local("vl", prompt, system, images=images)

    # Prompt too long for local model
    if len(prompt) > LOCAL_CONTEXT_LIMIT_CHARS:
        logger.info("Prompt length %d > %d — escalating to Gemini", len(prompt), LOCAL_CONTEXT_LIMIT_CHARS)
        return await _call_gemini(prompt, system)

    # Try local first
    if await ollama_ok():
        try:
            return await _call_local("coder", prompt, system)
        except Exception as exc:
            logger.warning("Local model failed: %s — falling back to Gemini", exc)

    # Fallback to Gemini
    return await _call_gemini(prompt, system)


async def _call_local(
    model_type: str,
    prompt: str,
    system: Optional[str],
    images: Optional[list[str]] = None,
) -> str:
    from intelligence.vram_mutex import vram_mutex
    from intelligence.ollama_client import generate as ollama_generate

    async with vram_mutex.acquire(model_type):
        return await ollama_generate(
            model_type=model_type,
            prompt=prompt,
            system=system,
            images=images,
        )


async def _call_gemini(prompt: str, system: Optional[str]) -> str:
    from intelligence.gemini_client import generate as gemini_generate
    return await gemini_generate(prompt=prompt, system_instruction=system)
