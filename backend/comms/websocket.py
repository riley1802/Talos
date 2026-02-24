"""WebSocket log streamer — real-time Tier-2/3 log streaming to dashboard clients.

Spec § 5.5: On connect, backfill 50 lines. Then stream new lines as they arrive.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("TALOS_LOG_DIR", "/talos/logs"))
TIER2_FILE = LOG_DIR / "tier2" / "ops.jsonl"
BACKFILL_LINES = 50

_active_connections: Set[WebSocket] = set()


async def connect(websocket: WebSocket) -> None:
    await websocket.accept()
    _active_connections.add(websocket)
    logger.debug("WebSocket client connected (%d total)", len(_active_connections))
    await _send_backfill(websocket)


async def disconnect(websocket: WebSocket) -> None:
    _active_connections.discard(websocket)
    logger.debug("WebSocket client disconnected (%d total)", len(_active_connections))


async def _send_backfill(websocket: WebSocket) -> None:
    """Send last N lines of the ops log to a newly connected client."""
    if not TIER2_FILE.exists():
        return
    try:
        lines = TIER2_FILE.read_text().splitlines()
        tail = lines[-BACKFILL_LINES:]
        for line in tail:
            await websocket.send_text(line)
    except Exception as exc:
        logger.warning("Backfill send failed: %s", exc)


async def broadcast(message: str) -> None:
    """Broadcast a log line to all connected WebSocket clients."""
    dead: Set[WebSocket] = set()
    for ws in _active_connections.copy():
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    _active_connections -= dead


class LogStreamer:
    """Tails the ops log file and broadcasts new lines to WebSocket clients."""

    def __init__(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        TIER2_FILE.parent.mkdir(parents=True, exist_ok=True)
        TIER2_FILE.touch(exist_ok=True)

        position = TIER2_FILE.stat().st_size  # Start at end of file
        while self._running:
            try:
                current_size = TIER2_FILE.stat().st_size
                if current_size > position:
                    with TIER2_FILE.open() as f:
                        f.seek(position)
                        new_lines = f.read()
                    position = current_size
                    for line in new_lines.splitlines():
                        if line.strip():
                            await broadcast(line)
            except Exception as exc:
                logger.warning("LogStreamer error: %s", exc)
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        self._running = False


log_streamer = LogStreamer()
