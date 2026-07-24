from unittest.mock import AsyncMock
import pytest
from src.events import SpeechCapturedEvent
from src.event_publisher import EventPublisher


@pytest.mark.asyncio
async def test_publish_speech_captured_success():
    mock_bus = AsyncMock()
    publisher = EventPublisher(event_bus=mock_bus)

    await publisher.publish_speech_captured(
        correlation_id="test-cid-123",
        channel="voice",
        audio_path="2026-07-24_17-30-00.wav",
    )

    mock_bus.publish.assert_awaited_once()
    published_evt = mock_bus.publish.await_args[0][0]
    assert isinstance(published_evt, SpeechCapturedEvent)
    assert published_evt.correlation_id == "test-cid-123"
    assert published_evt.channel == "voice"
    assert published_evt.audio_path == "2026-07-24_17-30-00.wav"


@pytest.mark.asyncio
async def test_publish_speech_captured_handles_exception(caplog):
    mock_bus = AsyncMock()
    mock_bus.publish.side_effect = Exception("NATS network error")
    publisher = EventPublisher(event_bus=mock_bus)

    # Should not raise exception
    await publisher.publish_speech_captured(
        correlation_id="test-cid-123",
        channel="voice",
        audio_path="2026-07-24_17-30-00.wav",
    )

    assert "Failed to publish SpeechCapturedEvent for audio_path=2026-07-24_17-30-00.wav" in caplog.text
