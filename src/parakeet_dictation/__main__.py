"""Entry point: ``python -m parakeet_dictation``.

Wires config loading, daemon startup, and graceful shutdown. See handover §8d.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from .config import ConfigError, load_config
from .daemon import run as daemon_run

log = logging.getLogger("parakeet_dictation")


def _configure_logging(level: str, file_path: str) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = RichHandler(rich_tracebacks=True, show_time=False, show_path=False)
    console.setLevel(level.upper())
    root.addHandler(console)

    try:
        log_path = Path(file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        file_handler.setLevel(level.upper())
        root.addHandler(file_handler)
    except OSError as exc:
        log.warning("Could not open log file %s: %s", file_path, exc)


def main() -> None:
    parser = argparse.ArgumentParser(prog="parakeet-dictation")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config.toml (default: ./config.toml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        sys.exit(2)

    _configure_logging(config.logging.level, config.logging.file)

    try:
        asyncio.run(daemon_run(config))
    except KeyboardInterrupt:
        log.info("Interrupted — shutting down")


if __name__ == "__main__":
    main()
