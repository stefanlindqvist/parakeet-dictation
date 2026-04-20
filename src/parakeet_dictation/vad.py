"""Silero VAD wrapper. See handover §8c.

Uses the ONNX build bundled with ``silero-vad`` (CPU — tiny model, not worth GPU).
Feeds 30 ms windows of PCM-16 audio. In hold mode: trim leading/trailing silence
only. In toggle mode: also terminate recording after ``silence_timeout_ms``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import VadConfig


class SileroVad:
    def __init__(self, config: "VadConfig") -> None:
        self._config = config

    def trim(self, audio: bytes) -> bytes:
        """Return the audio with leading/trailing silence removed.

        Implement per handover §11 step 8.
        """
        raise NotImplementedError("Implement per handover §11 step 8.")
