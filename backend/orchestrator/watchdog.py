"""Event loop watchdog — detects blocks > 30 seconds and triggers restart.

Spec § 4.3: If the event loop is blocked for more than 30 seconds,
log CRITICAL and signal for container restart.
"""
import asyncio
import logging
import os
import signal
import time

logger = logging.getLogger(__name__)

WATCHDOG_INTERVAL = 5.0   # Check every 5 seconds
BLOCK_THRESHOLD = 30.0    # Trigger if blocked longer than this


class EventLoopWatchdog:
    def __init__(self) -> None:
        self._last_heartbeat = time.monotonic()
        self._running = False

    def record_heartbeat(self) -> None:
        self._last_heartbeat = time.monotonic()

    def start(self) -> None:
        self._running = True
        # Run the watchdog in a background thread so it can detect event loop blocks
        import threading
        t = threading.Thread(target=self._watch_loop, daemon=True)
        t.start()
        logger.info("Watchdog started (threshold=%ds)", int(BLOCK_THRESHOLD))

    def stop(self) -> None:
        self._running = False

    def _watch_loop(self) -> None:
        import time as _time
        while self._running:
            _time.sleep(WATCHDOG_INTERVAL)
            elapsed = time.monotonic() - self._last_heartbeat
            if elapsed > BLOCK_THRESHOLD:
                logger.critical(
                    "EVENT LOOP BLOCKED for %.1fs (threshold=%ds) — signaling restart",
                    elapsed, int(BLOCK_THRESHOLD)
                )
                # Signal the process to restart gracefully
                os.kill(os.getpid(), signal.SIGTERM)
                return


watchdog = EventLoopWatchdog()


async def heartbeat_task() -> None:
    """Async task that continually updates the watchdog heartbeat."""
    while True:
        watchdog.record_heartbeat()
        await asyncio.sleep(WATCHDOG_INTERVAL)
