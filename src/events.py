from dataclasses import dataclass
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
