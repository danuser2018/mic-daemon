import logging
from nova_event_bus import EventBus
from src.events import SpeechCapturedEvent

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Handles publishing domain events for mic-daemon over NATS event bus.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def publish_speech_captured(
        self,
        correlation_id: str,
        channel: str,
        audio_path: str,
    ) -> None:
        """
        Publish SpeechCapturedEvent to subject 'event.speech.captured'.
        """
        evt = SpeechCapturedEvent(
            correlation_id=correlation_id,
            channel=channel,
            audio_path=audio_path,
        )
        try:
            await self._event_bus.publish(evt)
            logger.info(
                "Published SpeechCapturedEvent: correlation_id=%s, channel=%s, audio_path=%s",
                correlation_id,
                channel,
                audio_path,
            )
        except Exception:
            logger.exception(
                "Failed to publish SpeechCapturedEvent for audio_path=%s",
                audio_path,
            )
