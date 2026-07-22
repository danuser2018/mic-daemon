"""
test_config.py — Unit tests for src/config.py.

All tests use environment variable injection via monkeypatch or unittest.mock
so no real filesystem or audio hardware is required.
"""

import os
import pytest

from src.config import load_config, Config


class TestLoadConfig:
    """Tests for load_config()."""

    def test_raises_when_output_dir_missing(self, monkeypatch):
        """MIC_OUTPUT_DIR is required; absence must raise ValueError."""
        monkeypatch.delenv("MIC_OUTPUT_DIR", raising=False)
        with pytest.raises(ValueError, match="MIC_OUTPUT_DIR"):
            load_config()

    def test_raises_when_output_dir_empty(self, monkeypatch, tmp_path):
        """An empty string for MIC_OUTPUT_DIR must raise ValueError."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", "   ")
        with pytest.raises(ValueError, match="MIC_OUTPUT_DIR"):
            load_config()

    def test_defaults(self, monkeypatch, tmp_path):
        """All optional variables should fall back to documented defaults."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.delenv("MIC_DEVICE", raising=False)
        monkeypatch.delenv("MIC_SAMPLE_RATE", raising=False)
        monkeypatch.delenv("MIC_CHANNELS", raising=False)
        monkeypatch.delenv("NATS_URL", raising=False)

        cfg = load_config()

        assert cfg.output_dir == tmp_path
        assert cfg.device is None
        assert cfg.sample_rate == 16000
        assert cfg.channels == 1
        assert cfg.nats_url == "nats://localhost:4222"

    def test_device_numeric_index(self, monkeypatch, tmp_path):
        """A numeric MIC_DEVICE should be parsed as int."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("MIC_DEVICE", "2")

        cfg = load_config()

        assert cfg.device == 2
        assert isinstance(cfg.device, int)

    def test_device_string_name(self, monkeypatch, tmp_path):
        """A non-numeric MIC_DEVICE should be kept as string."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("MIC_DEVICE", "HDA Intel PCH")

        cfg = load_config()

        assert cfg.device == "HDA Intel PCH"

    def test_custom_sample_rate(self, monkeypatch, tmp_path):
        """MIC_SAMPLE_RATE should override the default."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("MIC_SAMPLE_RATE", "44100")

        cfg = load_config()

        assert cfg.sample_rate == 44100

    def test_invalid_sample_rate_raises(self, monkeypatch, tmp_path):
        """A non-integer MIC_SAMPLE_RATE must raise ValueError."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("MIC_SAMPLE_RATE", "fast")

        with pytest.raises(ValueError, match="MIC_SAMPLE_RATE"):
            load_config()

    def test_invalid_channels_raises(self, monkeypatch, tmp_path):
        """MIC_CHANNELS must be 1 or 2; anything else raises ValueError."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("MIC_CHANNELS", "5")

        with pytest.raises(ValueError, match="MIC_CHANNELS"):
            load_config()

    def test_stereo_channels(self, monkeypatch, tmp_path):
        """MIC_CHANNELS=2 (stereo) should be accepted."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("MIC_CHANNELS", "2")

        cfg = load_config()

        assert cfg.channels == 2

    def test_custom_nats_url(self, monkeypatch, tmp_path):
        """NATS_URL environment variable should override default."""
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("NATS_URL", "nats://192.168.1.50:4222")

        cfg = load_config()

        assert cfg.nats_url == "nats://192.168.1.50:4222"

    def test_output_dir_created_if_missing(self, monkeypatch, tmp_path):
        """load_config() must create MIC_OUTPUT_DIR if it does not exist."""
        new_dir = tmp_path / "recordings" / "nested"
        monkeypatch.setenv("MIC_OUTPUT_DIR", str(new_dir))

        load_config()

        assert new_dir.exists()
