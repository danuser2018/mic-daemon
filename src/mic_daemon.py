"""
mic_daemon.py — Entry point for the mic-daemon systemd user service.

Orchestrates the three core modules:
  1. config   — loads and validates environment variables
  2. recorder — manages audio capture and WAV writing
  3. state_watcher — polls the flag file and fires start/stop callbacks

Startup behaviour (per README § Robustez):
  - If the flag file already exists when the daemon starts (e.g. after a
    crash), it is deleted and a warning is logged. Recording is NOT started
    automatically to avoid "ghost recordings".

Shutdown behaviour:
  - systemd sends SIGTERM on `systemctl --user stop mic-daemon`.
  - The SIGTERM handler sets the watcher stop event so the main thread
    exits cleanly.
"""

import logging
import signal
import sys
from pathlib import Path

from src.config import load_config
from src.recorder import Recorder, build_output_path
from src.state_watcher import StateWatcher

# ------------------------------------------------------------------
# Logging: output goes to stdout/stderr → journald picks it up
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("mic_daemon")


def _cleanup_stale_flag(flag_path: Path) -> None:
    """
    Remove a pre-existing flag file left over from a previous crash.

    Per the README design spec: we do NOT start recording automatically
    because we cannot know whether the user still intends to record.
    """
    if flag_path.exists():
        logger.warning(
            "Stale flag found at startup: %s — removing it. "
            "This may indicate the daemon crashed while recording.",
            flag_path,
        )
        try:
            flag_path.unlink()
        except OSError:
            logger.exception("Could not remove stale flag: %s", flag_path)


def main() -> None:
    logger.info("mic-daemon starting up")

    # 1. Load configuration (raises ValueError with a clear message if invalid)
    try:
        config = load_config()
    except ValueError as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    logger.info(
        "Config loaded — output_dir=%s, sample_rate=%d Hz, channels=%d, "
        "device=%s, poll_interval=%.0f ms",
        config.output_dir,
        config.sample_rate,
        config.channels,
        config.device if config.device is not None else "default",
        config.poll_interval_s * 1000,
    )

    # 2. Ensure the flag directory exists
    config.flag_path.parent.mkdir(parents=True, exist_ok=True)

    # 3. Handle stale flag from a previous crash
    _cleanup_stale_flag(config.flag_path)

    # 4. Build the recorder and wire callbacks
    recorder = Recorder(config)

    def on_start() -> None:
        output_path = build_output_path(config.output_dir)
        recorder.start(output_path)

    def on_stop() -> None:
        recorder.stop()

    # 5. Build the state watcher
    watcher = StateWatcher(
        flag_path=config.flag_path,
        on_start=on_start,
        on_stop=on_stop,
        poll_interval_s=config.poll_interval_s,
    )

    # 6. Register SIGTERM handler so systemd can stop us cleanly
    def _sigterm_handler(signum, frame) -> None:  # noqa: ARG001
        logger.info("SIGTERM received — requesting clean shutdown")
        watcher.stop()

    signal.signal(signal.SIGTERM, _sigterm_handler)

    # 7. Run the watcher (blocks until SIGTERM or KeyboardInterrupt)
    logger.info("mic-daemon ready — waiting for recording flag")
    watcher.run()

    logger.info("mic-daemon shut down cleanly")


if __name__ == "__main__":
    main()
