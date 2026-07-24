"""
test_event_subscriber.py — Unit tests for src/event_subscriber.py.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.events import StartSpeechCaptureCommand, StopSpeechCaptureCommand
from src.event_subscriber import EventSubscriber


@pytest.mark.asyncio
async def test_start_subscribes_to_events():
    event_bus = AsyncMock()
    on_start = MagicMock()
    on_stop = MagicMock()

    subscriber = EventSubscriber(
        event_bus=event_bus,
        on_start=on_start,
        on_stop=on_stop,
    )

    await subscriber.start()

    event_bus.connect.assert_awaited_once()
    assert event_bus.subscribe.await_count == 2
    subscribed_classes = [call.args[0] for call in event_bus.subscribe.await_args_list]
    assert StartSpeechCaptureCommand in subscribed_classes
    assert StopSpeechCaptureCommand in subscribed_classes


@pytest.mark.asyncio
async def test_stop_disconnects_bus():
    event_bus = AsyncMock()
    subscriber = EventSubscriber(
        event_bus=event_bus,
        on_start=MagicMock(),
        on_stop=MagicMock(),
    )

    await subscriber.stop()

    event_bus.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_start_triggers_callback():
    event_bus = AsyncMock()
    on_start = MagicMock()
    on_stop = MagicMock()

    subscriber = EventSubscriber(
        event_bus=event_bus,
        on_start=on_start,
        on_stop=on_stop,
    )

    cmd = StartSpeechCaptureCommand()
    await subscriber._handle_start(cmd)

    on_start.assert_called_once_with()
    on_stop.assert_not_called()


@pytest.mark.asyncio
async def test_handle_stop_triggers_callback():
    event_bus = AsyncMock()
    on_start = MagicMock()
    on_stop = MagicMock()

    subscriber = EventSubscriber(
        event_bus=event_bus,
        on_start=on_start,
        on_stop=on_stop,
    )

    cmd = StopSpeechCaptureCommand()
    await subscriber._handle_stop(cmd)

    on_stop.assert_called_once_with()
    on_start.assert_not_called()
