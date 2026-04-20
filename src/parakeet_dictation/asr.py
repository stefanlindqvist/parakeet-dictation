"""Parakeet-TDT 0.6B v3 ONNX wrapper. See handover §8a.

Load the model once at startup and reuse the session. Encoder on
``DmlExecutionProvider``, decoder_joint on ``CPUExecutionProvider`` (see handover
§3 for the hybrid GPU/CPU rationale — don't move the decoder to GPU, it's slower).
Warm up with ~1 s of silence to avoid first-call latency spikes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AsrConfig


class ParakeetAsr:
    def __init__(self, config: "AsrConfig") -> None:
        self._config = config

    def warmup(self) -> None:
        """Feed ~1 s of silence through the session to prime kernels.

        Implement per handover §11 step 4.
        """
        raise NotImplementedError("Implement per handover §11 step 4.")

    def transcribe(self, audio: bytes) -> str:
        """Transcribe PCM16 16 kHz mono audio to text.

        Implement per handover §11 step 4.
        """
        raise NotImplementedError("Implement per handover §11 step 4.")
