"""Microphone capture via ``sounddevice`` (16 kHz mono PCM). See handover §5."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AudioConfig


class MicCapture:
    """Start/stop microphone capture and return the buffered audio as bytes.

    Implement per handover §11 step 7: ``sounddevice.InputStream`` with a
    callback that appends into a pre-sized numpy ring buffer. ``stop()`` returns
    the trimmed PCM16 bytes.
    """

    def __init__(self, config: "AudioConfig") -> None:
        self._config = config

    def start(self) -> None:
        raise NotImplementedError("Implement per handover §11 step 7.")

    def stop(self) -> bytes:
        raise NotImplementedError("Implement per handover §11 step 7.")
