"""Microphone capture via ``sounddevice`` (16 kHz mono PCM). See handover §5."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .config import AudioConfig

log = logging.getLogger(__name__)

# Cap every recording at 60 s — any realistic dictation utterance fits.
_MAX_RECORD_SECONDS = 60
_BLOCKSIZE = 1600  # 100 ms at 16 kHz


class MicCapture:
    """Start/stop microphone capture, returning the buffered audio as PCM16 bytes."""

    def __init__(self, config: "AudioConfig") -> None:
        self._config = config
        self._stream: Any | None = None
        self._buffer: np.ndarray | None = None
        self._write_idx = 0
        self._lock = threading.Lock()

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            log.debug("sounddevice status: %s", status)
        with self._lock:
            if self._buffer is None:
                return
            end = self._write_idx + frames
            if end > self._buffer.shape[0]:
                frames = self._buffer.shape[0] - self._write_idx
                if frames <= 0:
                    return
                end = self._buffer.shape[0]
            self._buffer[self._write_idx : end] = indata[:frames, 0]
            self._write_idx = end

    def start(self) -> None:
        import sounddevice as sd  # type: ignore[import-not-found]

        if self._stream is not None:
            raise RuntimeError("MicCapture.start called while already recording")

        sr = self._config.sample_rate
        self._buffer = np.zeros(sr * _MAX_RECORD_SECONDS, dtype=np.float32)
        self._write_idx = 0
        device = None if self._config.device_index < 0 else self._config.device_index
        self._stream = sd.InputStream(
            samplerate=sr,
            channels=1,
            dtype="float32",
            blocksize=_BLOCKSIZE,
            device=device,
            callback=self._callback,
        )
        self._stream.start()
        log.debug("MicCapture started (device=%s sr=%d)", device, sr)

    def stop(self) -> bytes:
        if self._stream is None:
            raise RuntimeError("MicCapture.stop called while not recording")
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        with self._lock:
            assert self._buffer is not None
            captured = self._buffer[: self._write_idx].copy()
            self._buffer = None
            self._write_idx = 0

        # Convert float32 [-1, 1] → int16 PCM bytes.
        clipped = np.clip(captured, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        return pcm16.tobytes()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None
