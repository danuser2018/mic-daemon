"""
test_mic_daemon.py — Unit tests for src/mic_daemon.py.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.mic_daemon import main_async, main


@pytest.mark.asyncio
async def test_main_async_configuration_error(monkeypatch):
    """If load_config fails, main_async logs critical and exits."""
    monkeypatch.delenv("MIC_OUTPUT_DIR", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        await main_async()

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_main_async_normal_lifecycle(monkeypatch, tmp_path):
    """Test main_async starts subscriber and cleans up when stop_event is set."""
    monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))

    mock_event_bus = AsyncMock()
    mock_subscriber = AsyncMock()
    mock_recorder = MagicMock()
    mock_recorder.is_recording.return_value = True

    with patch("src.mic_daemon.EventBus", return_value=mock_event_bus), \
         patch("src.mic_daemon.EventSubscriber", return_value=mock_subscriber) as mock_sub_cls, \
         patch("src.mic_daemon.Recorder", return_value=mock_recorder):

        # Launch main_async task and cancel/trigger signal
        task = asyncio.create_task(main_async())
        await asyncio.sleep(0.1)

        # Trigger stop_event by raising/simulating signal or canceling loop
        # We can inspect subscriber.start call
        mock_subscriber.start.assert_awaited_once()

        # Get on_start and on_stop passed to EventSubscriber
        call_kwargs = mock_sub_cls.call_args.kwargs
        on_start = call_kwargs["on_start"]
        on_stop = call_kwargs["on_stop"]

        # Call callbacks to verify integration with recorder
        on_start()
        mock_recorder.start.assert_called_once()

        on_stop()
        mock_recorder.stop.assert_called_once()

        # Now cancel the task to simulate shutdown
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
