"""
event_subscriber.py — Subscribes to NATS speech capture commands for mic-daemon.
"""

import logging
from typing import Callable
from nova_event_bus import EventBus
from novactl.events import StartSpeechCaptureCommand, StopSpeechCaptureCommand

logger = logging.getLogger(__name__)


class EventSubscriber:
    """
    Manages NATS event bus connection and subscribes to speech capture commands.
    """

    def __init__(
        self,
        event_bus: EventBus,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        self._event_bus = event_bus
        self._on_start = on_start
        self._on_stop = on_stop

    async def start(self) -> None:
        """Connect to NATS broker and subscribe to command events."""
        await self._event_bus.connect()
        await self._event_bus.subscribe(StartSpeechCaptureCommand, self._handle_start)
        await self._event_bus.subscribe(StopSpeechCaptureCommand, self._handle_stop)
        logger.info(
            "EventSubscriber subscribed to StartSpeechCaptureCommand and StopSpeechCaptureCommand"
        )

    async def stop(self) -> None:
        """Disconnect cleanly from NATS event bus."""
        await self._event_bus.disconnect()
        logger.info("EventSubscriber disconnected from NATS")

    async def _handle_start(self, event: StartSpeechCaptureCommand) -> None:
        logger.info("Handling StartSpeechCaptureCommand")
        self._on_start()

    async def _handle_stop(self, event: StopSpeechCaptureCommand) -> None:
        logger.info("Handling StopSpeechCaptureCommand")
        self._on_stop()
