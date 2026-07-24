import pytest
from nova_event_bus.event import get_subject_for_event
from src.events import (
    StartSpeechCaptureCommand,
    StopSpeechCaptureCommand,
    SpeechCapturedEvent,
    ResponseGeneratedEvent,
)


def test_start_speech_capture_command_subject():
    assert get_subject_for_event(StartSpeechCaptureCommand) == "command.speech.start-capture"


def test_stop_speech_capture_command_subject():
    assert get_subject_for_event(StopSpeechCaptureCommand) == "command.speech.stop-capture"


def test_speech_captured_event_subject():
    assert get_subject_for_event(SpeechCapturedEvent) == "event.speech.captured"


def test_response_generated_event_subject():
    assert get_subject_for_event(ResponseGeneratedEvent) == "event.interaction.response-generated"
