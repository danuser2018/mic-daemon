"""
mic_daemon.py — Entry point for the mic-daemon systemd user service.

Orchestrates:
  1. config — loads and validates environment variables
  2. recorder — manages audio capture and WAV writing
  3. event_subscriber — subscribes to NATS speech capture commands

Shutdown behaviour:
  - systemd sends SIGTERM on `systemctl --user stop mic-daemon`.
  - SIGTERM/SIGINT signals trigger graceful shutdown (stop recording if active, disconnect NATS).
"""

import asyncio
import logging
import signal
import sys
from nova_event_bus import EventBus
from src.config import load_config
from src.event_subscriber import EventSubscriber
from src.recorder import Recorder, build_output_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("mic_daemon")


async def main_async() -> None:
    logger.info("mic-daemon starting up")

    try:
        config = load_config()
    except ValueError as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    logger.info(
        "Config loaded — output_dir=%s, sample_rate=%d Hz, channels=%d, "
        "device=%s, nats_url=%s",
        config.output_dir,
        config.sample_rate,
        config.channels,
        config.device if config.device is not None else "default",
        config.nats_url,
    )

    recorder = Recorder(config)
    event_bus = EventBus()

    def on_start(correlation_id: str) -> None:
        output_path = build_output_path(config.output_dir)
        recorder.start(output_path)

    def on_stop(correlation_id: str) -> None:
        recorder.stop()

    subscriber = EventSubscriber(
        event_bus=event_bus,
        on_start=on_start,
        on_stop=on_stop,
    )

    await subscriber.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: stop_event.set())

    logger.info("mic-daemon ready — listening for NATS speech capture commands")
    await stop_event.wait()

    # Graceful cleanup
    if recorder.is_recording():
        recorder.stop()
    await subscriber.stop()
    logger.info("mic-daemon shut down cleanly")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
