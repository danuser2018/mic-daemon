from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any
from nova_event_bus import Event, event


@event("command.speech.start-capture")
@dataclass
class StartSpeechCaptureCommand(Event):
    pass


@event("command.speech.stop-capture")
@dataclass
class StopSpeechCaptureCommand(Event):
    pass


@event("event.speech.captured")
@dataclass
class SpeechCapturedEvent(Event):
    correlation_id: str
    channel: str
    audio_path: str


@event("event.interaction.response-generated")
@dataclass
class ResponseGeneratedEvent(Event):
    response: str
    plugin: str
    confidence: float
    timestamp: datetime
    correlation_id: str
    execution_time_ms: int
    channel: str
    metadata: Dict[str, Any]
