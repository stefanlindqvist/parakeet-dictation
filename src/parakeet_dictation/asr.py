"""Parakeet-TDT 0.6B v3 ONNX wrapper. See handover §8a.

Load the model once at startup and reuse the session. Encoder on
``DmlExecutionProvider``, decoder_joint on ``CPUExecutionProvider`` (see handover
§3 for the hybrid GPU/CPU rationale — don't move the decoder to GPU, it's slower).
Warm up with ~1 s of silence to avoid first-call latency spikes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .config import AsrConfig

log = logging.getLogger(__name__)

# onnx-asr uses these component names internally for Parakeet-TDT.
_ENCODER_COMPONENTS = ("encoder",)
_DECODER_COMPONENTS = ("decoder_joint", "decoder", "joint")


class ParakeetAsr:
    """Thin wrapper around :mod:`onnx_asr` for Parakeet-TDT 0.6B v3."""

    def __init__(self, config: "AsrConfig") -> None:
        self._config = config
        self._model: Any | None = None

    def load(self) -> None:
        """Load the ONNX model with the configured providers."""
        import onnx_asr  # type: ignore[import-not-found]

        path = Path(self._config.model_path)
        if not path.is_dir():
            raise FileNotFoundError(
                f"ASR model path does not exist: {path}. Run scripts/download_models.ps1 first."
            )

        providers = [self._config.encoder_provider, "CPUExecutionProvider"]
        # De-dup while preserving order.
        providers = list(dict.fromkeys(providers))

        log.info("Loading Parakeet-TDT from %s (providers=%s)", path, providers)
        model = onnx_asr.load_model(
            "nemo-parakeet-tdt-0.6b-v3",
            path=str(path),
            quantization="int8",
            providers=providers,
        )
        self._pin_decoder_to_cpu(model)
        self._log_active_providers(model)
        self._model = model

    def _pin_decoder_to_cpu(self, model: Any) -> None:
        """Force the TDT decoder/joint session onto CPU regardless of the encoder provider.

        onnx-asr uses a single providers list for every session; the handover's hybrid
        GPU/CPU split requires the decoder_joint on CPU specifically. We reach into the
        loaded model and rebuild the decoder session on CPU if needed.
        """
        target = self._config.decoder_provider
        if target == self._config.encoder_provider:
            return
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]
        except ImportError:
            return

        for attr in dir(model):
            if not any(name in attr for name in _DECODER_COMPONENTS):
                continue
            session = getattr(model, attr, None)
            if not hasattr(session, "get_providers") or not hasattr(session, "_model_path"):
                continue
            current = session.get_providers()
            if current and current[0] == target:
                continue
            try:
                new_session = ort.InferenceSession(
                    session._model_path,
                    providers=[target],
                )
            except Exception as exc:
                log.warning("Could not pin %s to %s: %s", attr, target, exc)
                continue
            setattr(model, attr, new_session)
            log.info("Pinned %s to %s", attr, target)

    @staticmethod
    def _log_active_providers(model: Any) -> None:
        for attr in dir(model):
            if attr.startswith("_"):
                continue
            obj = getattr(model, attr, None)
            if hasattr(obj, "get_providers"):
                try:
                    log.info("ASR session %s providers: %s", attr, obj.get_providers())
                except Exception:
                    pass

    def warmup(self) -> None:
        """Feed ~1 s of silence through the session to prime kernels."""
        if self._model is None:
            raise RuntimeError("ParakeetAsr.warmup called before load()")
        silence = np.zeros(16000, dtype=np.float32)
        try:
            self._model.recognize(silence)
        except Exception as exc:
            log.warning("Warmup transcribe failed: %s", exc)

    def transcribe(self, audio: bytes) -> str:
        """Transcribe PCM16 16 kHz mono audio to text."""
        if self._model is None:
            raise RuntimeError("ParakeetAsr.transcribe called before load()")
        if not audio:
            return ""
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        language = None if self._config.language == "auto" else self._config.language
        kwargs: dict[str, Any] = {}
        if language is not None:
            kwargs["language"] = language
        result = self._model.recognize(samples, **kwargs)
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, list) and result:
            return str(result[0]).strip()
        return str(result).strip()

    def close(self) -> None:
        self._model = None
