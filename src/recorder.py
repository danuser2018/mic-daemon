"""
recorder.py — Audio capture and WAV writing for mic-daemon.

Wraps sounddevice.InputStream so that the rest of the daemon
deals only with start/stop commands and never with raw audio APIs.

Design decisions:
- The audio buffer is a plain list of NumPy arrays; concatenation happens
  only at write time to avoid unnecessary copies during capture.
- A minimum-duration guard (MIN_DURATION_S) prevents writing empty or
  near-empty WAV files caused by accidental rapid toggles.
- Exceptions inside the sounddevice callback are logged but never raised,
  so a transient audio error does not crash the daemon.
- sounddevice and soundfile are imported lazily (inside methods) so that
  the module can be imported on systems without PortAudio installed —
  which is required to mock them in unit tests and to import the module
  in CI environments that lack the native library.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Recordings shorter than this threshold are discarded
MIN_DURATION_S = 0.1


class Recorder:
    """
    Stateful audio recorder.

    Lifecycle:
        recorder = Recorder(config)
        recorder.start(output_filename)   # opens stream, begins capture
        recorder.stop()                   # closes stream, writes WAV
    """

    def __init__(self, config: "Config") -> None:
        self._config = config
        self._stream: Any = None  # sounddevice.InputStream at runtime
        self._buffer: list[np.ndarray] = []
        self._output_path: Path | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, output_path: Path) -> None:
        """
        Open the audio stream and begin accumulating frames in memory.

        Args:
            output_path: Full path (including filename) for the WAV to be written
                         when stop() is called.
        """
        if self._stream is not None:
            logger.warning("start() called while already recording — ignoring")
            return

        # Lazy import: only executed at daemon runtime, not at import time.
        # This allows the module to be imported (and mocked) in test environments
        # that do not have the PortAudio native library installed.
        import sounddevice as sd  # noqa: PLC0415

        self._buffer = []
        self._output_path = output_path
        cfg = self._config

        try:
            self._stream = sd.InputStream(
                samplerate=cfg.sample_rate,
                channels=cfg.channels,
                dtype="int16",
                device=cfg.device if cfg.device is not None else None,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("Recording started → %s", output_path)
        except Exception:
            logger.exception("Failed to open audio stream")
            self._stream = None
            self._buffer = []
            self._output_path = None

    def stop(self) -> None:
        """
        Stop capture, flush the buffer to disk as a WAV file and reset state.
        """
        if self._stream is None:
            logger.warning("stop() called while not recording — ignoring")
            return

        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logger.exception("Error while closing audio stream")
        finally:
            self._stream = None

        self._write_buffer()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,  # noqa: ARG002
        time: Any,    # noqa: ARG002
        status: Any,
    ) -> None:
        """sounddevice callback — called from a background thread."""
        if status:
            # Informational: input overflow is the most common case on busy systems
            logger.warning("Audio callback status: %s", status)
        # Append a copy so the original buffer is not mutated after the call
        self._buffer.append(indata.copy())

    def _write_buffer(self) -> None:
        """Concatenate frames and write WAV to disk, then clear the buffer."""
        if not self._buffer:
            logger.info("Buffer is empty — no WAV file written")
            return

        audio = np.concatenate(self._buffer, axis=0)
        duration_s = len(audio) / self._config.sample_rate

        if duration_s < MIN_DURATION_S:
            logger.info(
                "Recording too short (%.2f s < %.2f s) — discarded",
                duration_s,
                MIN_DURATION_S,
            )
            self._buffer = []
            self._output_path = None
            return

        if self._output_path is None:
            logger.error("No output path set — cannot write WAV")
            return

        # Lazy import — same rationale as in start()
        import soundfile as sf  # noqa: PLC0415

        try:
            sf.write(
                file=str(self._output_path),
                data=audio,
                samplerate=self._config.sample_rate,
                subtype="PCM_16",
            )
            logger.info(
                "WAV written: %s (%.1f s, %d frames)",
                self._output_path,
                duration_s,
                len(audio),
            )
        except Exception:
            logger.exception("Failed to write WAV file: %s", self._output_path)
        finally:
            self._buffer = []
            self._output_path = None


def build_output_path(output_dir: Path) -> Path:
    """
    Generate a timestamped WAV file path.

    Format: YYYY-MM-DD_HH-MM-SS.wav
    The timestamp is taken at call time (i.e. when recording starts).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return output_dir / f"{timestamp}.wav"
