"""
config.py — Configuration loader for mic-daemon.

Reads configuration exclusively from environment variables.
Raises a descriptive error at startup if required variables are missing
or invalid, so systemd logs show the problem immediately.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Validated runtime configuration for the daemon."""

    output_dir: Path
    # None means "use system default device"
    device: str | int | None
    sample_rate: int
    channels: int
    poll_interval_s: float

    # Derived constant — not configurable
    flag_path: Path = field(
        default=Path("/tmp/voice_assistant/recording.flag"),
        init=False,
    )


def load_config() -> Config:
    """
    Load and validate configuration from environment variables.

    Returns a Config dataclass with all values validated and ready to use.
    Raises ValueError if required variables are missing or values are invalid.
    """
    # --- Required ---
    raw_output_dir = os.environ.get("MIC_OUTPUT_DIR", "").strip()
    if not raw_output_dir:
        raise ValueError(
            "MIC_OUTPUT_DIR environment variable is required but not set. "
            "Create ~/.config/mic-daemon/env with MIC_OUTPUT_DIR=/path/to/dir."
        )

    output_dir = Path(raw_output_dir)
    # Create it if it does not exist so the daemon can start without manual setup
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Optional with defaults ---
    raw_device = os.environ.get("MIC_DEVICE", "").strip()
    device: str | int | None = None
    if raw_device:
        # Accept numeric index or device name string
        device = int(raw_device) if raw_device.isdigit() else raw_device

    raw_sample_rate = os.environ.get("MIC_SAMPLE_RATE", "16000").strip()
    try:
        sample_rate = int(raw_sample_rate)
        if sample_rate <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(
            f"MIC_SAMPLE_RATE must be a positive integer, got: '{raw_sample_rate}'"
        )

    raw_channels = os.environ.get("MIC_CHANNELS", "1").strip()
    try:
        channels = int(raw_channels)
        if channels not in (1, 2):
            raise ValueError
    except ValueError:
        raise ValueError(
            f"MIC_CHANNELS must be 1 (mono) or 2 (stereo), got: '{raw_channels}'"
        )

    raw_poll_ms = os.environ.get("MIC_POLL_INTERVAL_MS", "100").strip()
    try:
        poll_interval_s = int(raw_poll_ms) / 1000.0
        if poll_interval_s <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(
            f"MIC_POLL_INTERVAL_MS must be a positive integer, got: '{raw_poll_ms}'"
        )

    return Config(
        output_dir=output_dir,
        device=device,
        sample_rate=sample_rate,
        channels=channels,
        poll_interval_s=poll_interval_s,
    )
