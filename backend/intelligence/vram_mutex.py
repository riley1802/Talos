"""VRAM Mutex — exclusive GPU memory access control.

Spec § 2.1: States IDLE → LOADING_CODER/LOADING_VL → UNLOADING → IDLE
All state transitions have a 30-second hard timeout.
State is persisted in Redis for observability.
"""
import asyncio
import logging
import os
import signal
import subprocess
import threading
import time
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class VRAMState(Enum):
    """Spec § 2.1.3 — State encoding (hex)."""
    IDLE = 0x00
    LOADING_CODER = 0x10
    LOADING_VL = 0x01
    UNLOADING = 0x20
    ERROR = 0xFF


class VRAMTimeoutConfig:
    """Spec § 2.1.6 — All timeouts in seconds."""
    SEMAPHORE_ACQUIRE_TIMEOUT = 30.0
    MODEL_LOAD_TIMEOUT = 30.0
    MODEL_UNLOAD_TIMEOUT = 30.0
    NVIDIA_SMI_TIMEOUT = 5.0
    PROCESS_KILL_TIMEOUT = 10.0
    RECOVERY_COOLDOWN = 60.0


REDIS_STATE_KEY = "talos:vram:state"
REDIS_MODEL_KEY = "talos:vram:loaded_model"


class VRAMMutex:
    """
    Exclusive VRAM access guard for Qwen model swapping.

    Usage:
        async with vram_mutex.acquire("coder"):
            await ollama.generate(model="qwen-coder", ...)
    """

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(1)
        self._state = VRAMState.IDLE
        self._loaded_model: Optional[str] = None  # "coder" | "vl" | None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> VRAMState:
        return self._state

    @property
    def loaded_model(self) -> Optional[str]:
        return self._loaded_model

    async def _set_state(self, state: VRAMState, model: Optional[str] = None) -> None:
        async with self._lock:
            self._state = state
            self._loaded_model = model
        await self._persist_state()

    async def _persist_state(self) -> None:
        try:
            from memory.redis_client import set_value
            await set_value(REDIS_STATE_KEY, self._state.name)
            await set_value(REDIS_MODEL_KEY, self._loaded_model or "none")
        except Exception as exc:
            logger.warning("Failed to persist VRAM state to Redis: %s", exc)

    def acquire(self, model_type: str) -> "_VRAMContext":
        """Return an async context manager for exclusive VRAM access."""
        return _VRAMContext(self, model_type)

    async def _request_load(self, model_type: str) -> None:
        loading_state = VRAMState.LOADING_CODER if model_type == "coder" else VRAMState.LOADING_VL
        await self._set_state(loading_state)
        logger.info("VRAM: loading %s model", model_type)

    async def _request_unload(self) -> None:
        await self._set_state(VRAMState.UNLOADING)
        logger.info("VRAM: unloading model")

    async def _complete_load(self, model_type: str) -> None:
        await self._set_state(VRAMState.IDLE, model=model_type)
        logger.info("VRAM: %s model loaded and ready", model_type)

    async def _complete_unload(self) -> None:
        await self._set_state(VRAMState.IDLE, model=None)
        logger.info("VRAM: model unloaded, IDLE")

    async def _enter_error(self, reason: str) -> None:
        await self._set_state(VRAMState.ERROR)
        logger.critical("VRAM: ERROR state — %s", reason)

    def _get_vram_used_mb(self) -> Optional[float]:
        """Query nvidia-smi for current VRAM usage."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True,
                timeout=VRAMTimeoutConfig.NVIDIA_SMI_TIMEOUT,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass
        return None


class _VRAMContext:
    """Async context manager returned by VRAMMutex.acquire()."""

    def __init__(self, mutex: VRAMMutex, model_type: str) -> None:
        self._mutex = mutex
        self._model_type = model_type

    async def __aenter__(self):
        try:
            await asyncio.wait_for(
                self._mutex._semaphore.acquire(),
                timeout=VRAMTimeoutConfig.SEMAPHORE_ACQUIRE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"VRAM semaphore acquire timed out after "
                f"{VRAMTimeoutConfig.SEMAPHORE_ACQUIRE_TIMEOUT}s"
            )

        # If a different model is loaded, unload it first
        if (
            self._mutex.loaded_model is not None
            and self._mutex.loaded_model != self._model_type
        ):
            await self._unload_current()

        await self._load_requested()
        return self._mutex

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._mutex._semaphore.release()
        # Don't unload on exit — keep model warm for reuse

    async def _load_requested(self) -> None:
        if self._mutex.loaded_model == self._model_type:
            return  # Already loaded

        await self._mutex._request_load(self._model_type)
        try:
            await asyncio.wait_for(
                self._do_load(),
                timeout=VRAMTimeoutConfig.MODEL_LOAD_TIMEOUT,
            )
            await self._mutex._complete_load(self._model_type)
        except asyncio.TimeoutError:
            await self._mutex._request_unload()
            await self._force_unload()
            raise TimeoutError(f"Model load timed out after {VRAMTimeoutConfig.MODEL_LOAD_TIMEOUT}s")
        except Exception as exc:
            await self._mutex._enter_error(str(exc))
            raise

    async def _do_load(self) -> None:
        """Trigger Ollama to load the model into VRAM."""
        from intelligence.ollama_client import pull_model_to_vram
        model_name = "qwen2.5-coder:7b" if self._model_type == "coder" else "qwen2.5vl:7b"
        await pull_model_to_vram(model_name)

    async def _unload_current(self) -> None:
        await self._mutex._request_unload()
        try:
            await asyncio.wait_for(
                self._force_unload(),
                timeout=VRAMTimeoutConfig.MODEL_UNLOAD_TIMEOUT,
            )
            await self._mutex._complete_unload()
        except asyncio.TimeoutError:
            logger.critical("VRAM unload hung at 29s — force-killing Ollama process")
            await self._kill_ollama()
            await self._mutex._complete_unload()

    async def _force_unload(self) -> None:
        from intelligence.ollama_client import unload_model
        await unload_model()

    async def _kill_ollama(self) -> None:
        try:
            result = subprocess.run(["pkill", "-SIGTERM", "ollama"], timeout=5)
            await asyncio.sleep(VRAMTimeoutConfig.PROCESS_KILL_TIMEOUT)
            # Escalate to SIGKILL if still running
            subprocess.run(["pkill", "-SIGKILL", "ollama"], timeout=5)
        except Exception as exc:
            logger.error("Failed to kill Ollama: %s", exc)


# Module-level singleton
vram_mutex = VRAMMutex()
