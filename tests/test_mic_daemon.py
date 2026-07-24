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
    """Test main_async starts subscriber, publishes speech captured event on stop, and cleans up."""
    monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))

    mock_event_bus = AsyncMock()
    mock_subscriber = AsyncMock()
    mock_publisher = AsyncMock()
    mock_recorder = MagicMock()
    mock_recorder.is_recording.return_value = True
    mock_recorder.stop.return_value = ("2026-07-24_17-30-00.wav", "test-cid-123")

    with patch("src.mic_daemon.EventBus", return_value=mock_event_bus), \
         patch("src.mic_daemon.EventSubscriber", return_value=mock_subscriber) as mock_sub_cls, \
         patch("src.mic_daemon.EventPublisher", return_value=mock_publisher), \
         patch("src.mic_daemon.Recorder", return_value=mock_recorder):

        # Launch main_async task and cancel/trigger signal
        task = asyncio.create_task(main_async())
        await asyncio.sleep(0.1)

        # Inspect subscriber.start call
        mock_subscriber.start.assert_awaited_once()

        # Get on_start and on_stop passed to EventSubscriber
        call_kwargs = mock_sub_cls.call_args.kwargs
        on_start = call_kwargs["on_start"]
        on_stop = call_kwargs["on_stop"]

        # Call callbacks to verify integration with recorder and publisher
        on_start()
        mock_recorder.start.assert_called_once()

        on_stop()
        mock_recorder.stop.assert_called_once()
        await asyncio.sleep(0.01)
        mock_publisher.publish_speech_captured.assert_awaited_once_with(
            correlation_id="test-cid-123",
            channel="voice",
            audio_path="2026-07-24_17-30-00.wav",
        )

        # Now cancel the task to simulate shutdown
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_main_async_shutdown_with_active_recording(monkeypatch, tmp_path):
    """Test main_async performs graceful shutdown and publishes event if recording is active when stopped."""
    monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))

    mock_event_bus = AsyncMock()
    mock_subscriber = AsyncMock()
    mock_publisher = AsyncMock()
    mock_recorder = MagicMock()
    mock_recorder.is_recording.return_value = True
    mock_recorder.stop.return_value = ("shutdown_audio.wav", "shutdown-cid-999")

    fake_stop_event = asyncio.Event()
    fake_stop_event.set()

    with patch("src.mic_daemon.EventBus", return_value=mock_event_bus), \
         patch("src.mic_daemon.EventSubscriber", return_value=mock_subscriber), \
         patch("src.mic_daemon.EventPublisher", return_value=mock_publisher), \
         patch("src.mic_daemon.Recorder", return_value=mock_recorder), \
         patch("asyncio.Event", return_value=fake_stop_event):

        await main_async()

        mock_recorder.stop.assert_called_once()
        mock_publisher.publish_speech_captured.assert_awaited_once_with(
            correlation_id="shutdown-cid-999",
            channel="voice",
            audio_path="shutdown_audio.wav",
        )
        mock_subscriber.stop.assert_awaited_once()
