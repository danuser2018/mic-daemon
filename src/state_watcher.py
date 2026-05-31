"""
state_watcher.py — Filesystem-based state observer for mic-daemon.

Implements a polling loop that watches the presence/absence of the
recording flag file and fires callbacks on state transitions.

Design decisions:
- Pure polling (no inotify/watchdog) as the primary mechanism.
  A 100 ms interval introduces at most 100 ms of latency at recording
  start, which is imperceptible to the user. See README § Decisiones de
  diseño for the full rationale.
- The module contains no audio logic; state transitions are communicated
  exclusively via on_start / on_stop callbacks. This keeps each module
  focused on a single responsibility.
- The loop is interrupted cleanly on KeyboardInterrupt or when the
  stop() method sets the internal stop event.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class StateWatcher:
    """
    Polls the flag file and fires callbacks on state transitions.

    Usage::

        watcher = StateWatcher(
            flag_path=Path("/tmp/voice_assistant/recording.flag"),
            on_start=recorder.start,
            on_stop=recorder.stop,
            poll_interval_s=0.1,
        )
        watcher.run()   # blocks; call stop() from another thread to exit
    """

    def __init__(
        self,
        flag_path: Path,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        poll_interval_s: float = 0.1,
    ) -> None:
        self._flag_path = flag_path
        self._on_start = on_start
        self._on_stop = on_stop
        self._poll_interval_s = poll_interval_s
        self._stop_event = threading.Event()
        # Track whether a recording is currently in progress
        self._recording = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start the polling loop. Blocks until stop() is called or a
        KeyboardInterrupt / SIGTERM is received.
        """
        logger.info(
            "State watcher started (flag=%s, interval=%.0f ms)",
            self._flag_path,
            self._poll_interval_s * 1000,
        )

        try:
            while not self._stop_event.is_set():
                self._tick()
                self._stop_event.wait(timeout=self._poll_interval_s)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received — stopping watcher")
        finally:
            # If we were recording when the loop ended, stop gracefully
            if self._recording:
                logger.warning(
                    "Watcher stopped while recording — triggering stop callback"
                )
                self._handle_stop()

        logger.info("State watcher stopped")

    def stop(self) -> None:
        """Signal the polling loop to exit on the next tick."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """Check the flag file and fire callbacks on state transitions."""
        flag_exists = self._flag_path.exists()

        if flag_exists and not self._recording:
            self._handle_start()
        elif not flag_exists and self._recording:
            self._handle_stop()

    def _handle_start(self) -> None:
        """Transition IDLE → RECORDING."""
        logger.info("Flag detected — transitioning to RECORDING")
        self._recording = True
        try:
            self._on_start()
        except Exception:
            logger.exception("on_start callback raised an exception")
            # Recover to IDLE so the watcher does not get stuck
            self._recording = False

    def _handle_stop(self) -> None:
        """Transition RECORDING → STOPPING → IDLE."""
        logger.info("Flag removed — transitioning to STOPPING → IDLE")
        self._recording = False
        try:
            self._on_stop()
        except Exception:
            logger.exception("on_stop callback raised an exception")
