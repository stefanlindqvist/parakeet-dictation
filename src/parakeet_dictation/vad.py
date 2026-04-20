"""Silero VAD wrapper. See handover §8c.

Uses the ONNX build bundled with ``silero-vad`` (CPU — tiny model, not worth GPU).
Feeds fixed-size windows of PCM-16 audio. In hold mode: trim leading/trailing silence
only. In toggle mode: also terminate recording after ``silence_timeout_ms``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .config import VadConfig

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
# Silero's ONNX model expects 512-sample windows at 16 kHz (32 ms).
_WINDOW = 512
# Padding kept around detected speech so we don't clip consonants.
_EDGE_PAD_MS = 120


class SileroVad:
    def __init__(self, config: "VadConfig") -> None:
        self._config = config
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from silero_vad import load_silero_vad  # type: ignore[import-not-found]

            self._model = load_silero_vad(onnx=True)
        return self._model

    def warmup(self) -> None:
        """Load the Silero ONNX session and run one window so the first real
        ``trim`` call isn't cold. Cheap (tiny model, CPU) and avoids the
        ~700 ms hit on the first real dictation after startup.
        """
        if not self._config.enabled:
            return
        import torch  # type: ignore[import-not-found]

        model = self._ensure_model()
        self._reset()
        chunk = np.zeros(_WINDOW, dtype=np.float32)
        tensor = torch.from_numpy(chunk)
        try:
            with torch.no_grad():
                model(tensor, _SAMPLE_RATE)
        except Exception as exc:
            log.warning("VAD warmup failed: %s", exc)

    def _reset(self) -> None:
        model = self._model
        if model is not None and hasattr(model, "reset_states"):
            try:
                model.reset_states()
            except Exception:
                pass

    def trim(self, audio: bytes) -> bytes:
        """Return ``audio`` with leading/trailing silence removed."""
        if not self._config.enabled or not audio:
            return audio

        import torch  # type: ignore[import-not-found]

        model = self._ensure_model()
        self._reset()

        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size < _WINDOW:
            return audio

        threshold = self._config.threshold
        window_count = samples.size // _WINDOW
        speech_mask = np.zeros(window_count, dtype=bool)

        for i in range(window_count):
            chunk = samples[i * _WINDOW : (i + 1) * _WINDOW]
            tensor = torch.from_numpy(chunk)
            with torch.no_grad():
                prob = float(model(tensor, _SAMPLE_RATE).item())
            speech_mask[i] = prob >= threshold

        if not speech_mask.any():
            log.debug("VAD: no speech detected in %d ms", samples.size * 1000 // _SAMPLE_RATE)
            return b""

        first = int(np.argmax(speech_mask))
        last = int(window_count - 1 - np.argmax(speech_mask[::-1]))

        speech_ms = (last - first + 1) * _WINDOW * 1000 // _SAMPLE_RATE
        if speech_ms < self._config.min_speech_ms:
            log.debug("VAD: speech too short (%d ms < %d ms)", speech_ms, self._config.min_speech_ms)
            return b""

        pad_windows = max(1, (_EDGE_PAD_MS * _SAMPLE_RATE // 1000) // _WINDOW)
        start = max(0, first - pad_windows) * _WINDOW
        end = min(window_count, last + 1 + pad_windows) * _WINDOW

        trimmed = samples[start:end]
        pcm16 = (np.clip(trimmed, -1.0, 1.0) * 32767.0).astype(np.int16)
        return pcm16.tobytes()
