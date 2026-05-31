"""
test_state_watcher.py — Unit tests for src/state_watcher.py.

Tests verify that:
  - on_start fires when the flag file is created
  - on_stop fires when the flag file is removed
  - No double-fire occurs for the same state
  - Exceptions in callbacks are swallowed (daemon never crashes)
  - stop() exits the loop cleanly
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from src.state_watcher import StateWatcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flag_path(tmp_path):
    return tmp_path / "recording.flag"


@pytest.fixture
def on_start():
    return MagicMock()


@pytest.fixture
def on_stop():
    return MagicMock()


def _make_watcher(flag_path, on_start, on_stop, poll_interval_s=0.01):
    return StateWatcher(
        flag_path=flag_path,
        on_start=on_start,
        on_stop=on_stop,
        poll_interval_s=poll_interval_s,
    )


def _run_watcher_briefly(watcher, duration_s=0.15):
    """Run the watcher in a thread and stop it after duration_s."""
    t = threading.Thread(target=watcher.run, daemon=True)
    t.start()
    time.sleep(duration_s)
    watcher.stop()
    t.join(timeout=2)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStateTriggers:
    def test_on_start_called_when_flag_created(self, flag_path, on_start, on_stop):
        """on_start must be called once when the flag file appears."""
        watcher = _make_watcher(flag_path, on_start, on_stop)

        t = threading.Thread(target=watcher.run, daemon=True)
        t.start()
        time.sleep(0.03)

        flag_path.touch()
        time.sleep(0.05)

        watcher.stop()
        t.join(timeout=2)

        on_start.assert_called_once()

    def test_on_stop_called_when_flag_removed(self, flag_path, on_start, on_stop):
        """on_stop must be called once when the flag file disappears."""
        flag_path.touch()  # start with flag present
        watcher = _make_watcher(flag_path, on_start, on_stop)

        t = threading.Thread(target=watcher.run, daemon=True)
        t.start()
        time.sleep(0.03)  # watcher detects flag → on_start fires

        flag_path.unlink()
        time.sleep(0.05)  # watcher detects removal → on_stop fires

        watcher.stop()
        t.join(timeout=2)

        on_stop.assert_called_once()

    def test_no_double_start_while_recording(self, flag_path, on_start, on_stop):
        """on_start must NOT fire again if the flag is already present."""
        flag_path.touch()
        watcher = _make_watcher(flag_path, on_start, on_stop)

        _run_watcher_briefly(watcher, duration_s=0.2)

        # Flag remained present the whole time — on_start should fire exactly once
        assert on_start.call_count == 1

    def test_full_toggle_cycle(self, flag_path, on_start, on_stop):
        """A full create → delete cycle must fire on_start then on_stop once each."""
        watcher = _make_watcher(flag_path, on_start, on_stop)

        t = threading.Thread(target=watcher.run, daemon=True)
        t.start()
        time.sleep(0.02)

        flag_path.touch()
        time.sleep(0.05)

        flag_path.unlink()
        time.sleep(0.05)

        watcher.stop()
        t.join(timeout=2)

        on_start.assert_called_once()
        on_stop.assert_called_once()


class TestErrorHandling:
    def test_exception_in_on_start_does_not_crash_watcher(self, flag_path, on_stop):
        """An exception in on_start must be swallowed; watcher keeps running."""
        on_start = MagicMock(side_effect=RuntimeError("boom"))
        watcher = _make_watcher(flag_path, on_start, on_stop)

        flag_path.touch()

        # Should not raise
        _run_watcher_briefly(watcher, duration_s=0.15)

    def test_exception_in_on_stop_does_not_crash_watcher(self, flag_path, on_start):
        """An exception in on_stop must be swallowed; watcher keeps running."""
        on_stop = MagicMock(side_effect=RuntimeError("boom"))
        flag_path.touch()
        watcher = _make_watcher(flag_path, on_start, on_stop)

        t = threading.Thread(target=watcher.run, daemon=True)
        t.start()
        time.sleep(0.03)

        flag_path.unlink()
        time.sleep(0.05)

        # Should not raise
        watcher.stop()
        t.join(timeout=2)


class TestCleanShutdown:
    def test_stop_exits_run_loop(self, flag_path, on_start, on_stop):
        """stop() must cause run() to return within a reasonable timeout."""
        watcher = _make_watcher(flag_path, on_start, on_stop)

        t = threading.Thread(target=watcher.run, daemon=True)
        t.start()
        time.sleep(0.03)

        watcher.stop()
        t.join(timeout=1)

        assert not t.is_alive(), "Watcher thread should have exited after stop()"

    def test_on_stop_called_on_shutdown_while_recording(self, flag_path, on_start, on_stop):
        """
        If the watcher is stopped while a recording is active,
        on_stop must be called to flush the buffer.
        """
        flag_path.touch()
        watcher = _make_watcher(flag_path, on_start, on_stop)

        t = threading.Thread(target=watcher.run, daemon=True)
        t.start()
        time.sleep(0.05)  # on_start has fired

        watcher.stop()
        t.join(timeout=2)

        on_stop.assert_called_once()
