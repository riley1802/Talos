"""Ollama client — Qwen Coder 7B and Qwen VL via local Ollama server."""
import asyncio
import json
import logging
import os
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QWEN_CODER_MODEL = os.getenv("QWEN_CODER_MODEL", "qwen2.5-coder:7b")
QWEN_VL_MODEL = os.getenv("QWEN_VL_MODEL", "qwen2.5vl:7b")

_http: Optional[httpx.AsyncClient] = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=120.0)
    return _http


async def is_available() -> bool:
    try:
        r = await _get_http().get("/api/tags")
        return r.status_code == 200
    except Exception:
        return False


async def list_local_models() -> list[str]:
    try:
        r = await _get_http().get("/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception as exc:
        logger.error("Failed to list Ollama models: %s", exc)
        return []


async def pull_model_to_vram(model_name: str) -> None:
    """Ask Ollama to keep model hot by running an empty generation."""
    try:
        await _get_http().post(
            "/api/generate",
            json={"model": model_name, "prompt": "", "keep_alive": "10m"},
            timeout=60.0,
        )
        logger.info("Model %s warmed in VRAM", model_name)
    except Exception as exc:
        logger.error("Failed to pull %s into VRAM: %s", model_name, exc)
        raise


async def unload_model() -> None:
    """Tell Ollama to release all models from VRAM."""
    for model in [QWEN_CODER_MODEL, QWEN_VL_MODEL]:
        try:
            await _get_http().post(
                "/api/generate",
                json={"model": model, "prompt": "", "keep_alive": "0"},
                timeout=30.0,
            )
        except Exception:
            pass
    logger.info("Requested VRAM unload for all models")


async def generate(
    model_type: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    images: Optional[list[str]] = None,
) -> str:
    """Generate a response from a Qwen model."""
    model = QWEN_CODER_MODEL if model_type == "coder" else QWEN_VL_MODEL

    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if system:
        payload["system"] = system
    if images:
        payload["images"] = images

    r = await _get_http().post("/api/generate", json=payload, timeout=120.0)
    r.raise_for_status()
    return r.json().get("response", "")


async def generate_stream(
    model_type: str,
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    """Stream a response token by token."""
    model = QWEN_CODER_MODEL if model_type == "coder" else QWEN_VL_MODEL

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    async with _get_http().stream("POST", "/api/generate", json=payload, timeout=120.0) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if line.strip():
                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    pass


async def ensure_models_pulled() -> None:
    """Pull required models if not already downloaded."""
    existing = await list_local_models()
    for model in [QWEN_CODER_MODEL, QWEN_VL_MODEL]:
        if not any(model in m for m in existing):
            logger.info("Pulling model %s (this may take a while)...", model)
            async with _get_http().stream(
                "POST", "/api/pull",
                json={"name": model},
                timeout=3600.0,
            ) as r:
                async for _ in r.aiter_bytes():
                    pass
            logger.info("Model %s pulled", model)
        else:
            logger.info("Model %s already available", model)
