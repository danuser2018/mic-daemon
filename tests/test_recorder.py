"""
test_recorder.py — Unit tests for src/recorder.py.

sounddevice and soundfile are mocked throughout so no audio hardware
or real filesystem audio I/O is needed. Tests focus on:
  - Correct stream lifecycle (open/close)
  - WAV file written with the right arguments
  - No file written when buffer is empty or recording is too short
  - Graceful error handling when sounddevice raises

Note on the mocking strategy:
  recorder.py uses lazy imports (import inside methods) to avoid requiring
  the PortAudio native library at module import time. However, even lazy
  imports cause `@patch("sounddevice.InputStream")` to call
  `__import__("sounddevice")` at decorator setup time — which still triggers
  the PortAudio OSError.

  The fix: inject fake modules into sys.modules at the TOP of this file,
  before any @patch decorator or import from src.recorder is processed.
  Once sys.modules["sounddevice"] exists, @patch finds it there and never
  tries to load the real C extension.
"""

import sys
from unittest.mock import MagicMock, patch

# ── MUST come before any import of src.recorder or @patch decorators ─────────
_fake_sounddevice = MagicMock()
_fake_soundfile = MagicMock()
sys.modules.setdefault("sounddevice", _fake_sounddevice)
sys.modules.setdefault("soundfile", _fake_soundfile)
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
import pytest
from pathlib import Path

from src.config import Config
from src.recorder import Recorder, build_output_path, MIN_DURATION_S


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config(tmp_path):
    """Minimal Config for testing."""
    return Config(
        output_dir=tmp_path,
        device=None,
        sample_rate=16000,
        channels=1,
        poll_interval_s=0.1,
    )


@pytest.fixture
def recorder(config):
    return Recorder(config)


@pytest.fixture(autouse=True)
def reset_audio_mocks():
    """Reset the fake sounddevice/soundfile mocks between tests.

    reset_mock() does NOT clear side_effect by default, so we must do it
    explicitly. Otherwise an OSError set in one test bleeds into the next.
    """
    _fake_sounddevice.InputStream.side_effect = None
    _fake_sounddevice.InputStream.return_value = MagicMock()
    _fake_soundfile.write.side_effect = None
    _fake_sounddevice.reset_mock()
    _fake_soundfile.reset_mock()
    yield
    # Post-test cleanup: ensure no state leaks forward
    _fake_sounddevice.InputStream.side_effect = None
    _fake_soundfile.write.side_effect = None


def _make_frames(sample_rate: int, duration_s: float) -> list[np.ndarray]:
    """Generate a list with a single audio frame of the given duration."""
    n_samples = int(sample_rate * duration_s)
    return [np.zeros((n_samples, 1), dtype="int16")]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRecorderStart:
    def test_opens_stream_with_correct_params(self, recorder, config, tmp_path):
        """start() should open an InputStream with config parameters."""
        mock_stream = MagicMock()
        _fake_sounddevice.InputStream.return_value = mock_stream

        recorder.start(tmp_path / "test.wav")

        _fake_sounddevice.InputStream.assert_called_once_with(
            samplerate=config.sample_rate,
            channels=config.channels,
            dtype="int16",
            device=None,
            callback=recorder._audio_callback,
        )
        mock_stream.start.assert_called_once()

    def test_double_start_is_ignored(self, recorder, tmp_path):
        """Calling start() twice should not open a second stream."""
        _fake_sounddevice.InputStream.return_value = MagicMock()

        recorder.start(tmp_path / "first.wav")
        recorder.start(tmp_path / "second.wav")

        assert _fake_sounddevice.InputStream.call_count == 1

    def test_start_failure_leaves_recorder_idle(self, recorder, tmp_path):
        """If InputStream raises, the recorder should remain in idle state."""
        _fake_sounddevice.InputStream.side_effect = OSError("No audio device")

        recorder.start(tmp_path / "test.wav")

        # Should not raise; stream and buffer should be reset
        assert recorder._stream is None
        assert recorder._buffer == []


class TestRecorderStop:
    def test_writes_wav_on_stop(self, recorder, config, tmp_path):
        """stop() should concatenate the buffer and call soundfile.write."""
        mock_stream = MagicMock()
        _fake_sounddevice.InputStream.return_value = mock_stream

        output_path = tmp_path / "out.wav"
        recorder.start(output_path)

        # Simulate captured frames (2 seconds of audio)
        recorder._buffer = _make_frames(config.sample_rate, 2.0)

        recorder.stop()

        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        _fake_soundfile.write.assert_called_once()

        # Verify the correct path and samplerate were used
        _, kwargs = _fake_soundfile.write.call_args
        assert kwargs.get("file") == str(output_path)
        assert kwargs.get("samplerate") == config.sample_rate
        assert kwargs.get("subtype") == "PCM_16"

    def test_no_wav_written_when_buffer_empty(self, recorder, tmp_path):
        """stop() with an empty buffer must NOT call soundfile.write."""
        _fake_sounddevice.InputStream.return_value = MagicMock()

        recorder.start(tmp_path / "out.wav")
        recorder._buffer = []  # no frames captured

        recorder.stop()

        _fake_soundfile.write.assert_not_called()

    def test_no_wav_written_when_too_short(self, recorder, config, tmp_path):
        """stop() with a recording shorter than MIN_DURATION_S must discard it."""
        _fake_sounddevice.InputStream.return_value = MagicMock()

        recorder.start(tmp_path / "out.wav")
        # Extremely short — below MIN_DURATION_S
        recorder._buffer = _make_frames(config.sample_rate, MIN_DURATION_S * 0.5)

        recorder.stop()

        _fake_soundfile.write.assert_not_called()

    def test_stop_without_start_is_ignored(self, recorder):
        """Calling stop() when not recording should not raise."""
        recorder.stop()  # Should be a no-op

    def test_buffer_cleared_after_stop(self, recorder, config, tmp_path):
        """After stop(), the buffer should be empty and output_path None."""
        _fake_sounddevice.InputStream.return_value = MagicMock()

        recorder.start(tmp_path / "out.wav")
        recorder._buffer = _make_frames(config.sample_rate, 2.0)
        recorder.stop()

        assert recorder._buffer == []
        assert recorder._output_path is None


class TestAudioCallback:
    def test_callback_appends_copy(self, recorder):
        """_audio_callback should append a copy of indata to the buffer."""
        indata = np.ones((1024, 1), dtype="int16")
        status = MagicMock()
        status.__bool__ = lambda self: False  # no status flags

        recorder._audio_callback(indata, 1024, None, status)

        assert len(recorder._buffer) == 1
        # Must be a copy, not the same object
        assert recorder._buffer[0] is not indata
        np.testing.assert_array_equal(recorder._buffer[0], indata)

    def test_callback_warns_on_status(self, recorder, caplog):
        """_audio_callback should log a warning when status flags are set."""
        import logging
        indata = np.zeros((512, 1), dtype="int16")
        status = MagicMock()
        status.__bool__ = lambda self: True  # status flag set

        with caplog.at_level(logging.WARNING, logger="src.recorder"):
            recorder._audio_callback(indata, 512, None, status)

        assert any("Audio callback status" in r.message for r in caplog.records)


class TestBuildOutputPath:
    def test_returns_wav_extension(self, tmp_path):
        path = build_output_path(tmp_path)
        assert path.suffix == ".wav"

    def test_is_inside_output_dir(self, tmp_path):
        path = build_output_path(tmp_path)
        assert path.parent == tmp_path

    def test_filename_matches_timestamp_format(self, tmp_path):
        import re
        path = build_output_path(tmp_path)
        pattern = r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.wav"
        assert re.fullmatch(pattern, path.name), f"Unexpected filename: {path.name}"

    def test_unique_paths_on_consecutive_calls(self, tmp_path):
        """Two calls at least 1 s apart must produce different paths."""
        import time
        path1 = build_output_path(tmp_path)
        time.sleep(1.1)
        path2 = build_output_path(tmp_path)
        assert path1 != path2
