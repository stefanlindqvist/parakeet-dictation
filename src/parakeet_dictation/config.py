"""Typed config loader for ``config.toml``. See handover §6 for the full schema."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class HotkeyConfig(BaseModel):
    mode: str = "hold"  # "hold" | "toggle"
    key: str = "<cmd>+`"


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    device_index: int = -1
    silence_timeout_ms: int = 1200


class VadConfig(BaseModel):
    enabled: bool = True
    threshold: float = 0.5
    min_speech_ms: int = 200


class AsrConfig(BaseModel):
    model_path: str = "./models/parakeet-tdt-0.6b-v3"
    language: str = "auto"
    encoder_provider: str = "DmlExecutionProvider"
    decoder_provider: str = "CPUExecutionProvider"


class PasteConfig(BaseModel):
    restore_clipboard: bool = True
    restore_delay_ms: int = 500


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "./parakeet-dictation.log"


class AppConfig(BaseModel):
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    paste: PasteConfig = Field(default_factory=PasteConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: Path | str = Path("config.toml")) -> AppConfig:
    """Parse ``config.toml`` from disk into an :class:`AppConfig`.

    Implement per handover §11 step 3: use ``tomllib`` (stdlib, 3.11+) to parse,
    then validate against :class:`AppConfig`. Raise a clear error if the file is
    missing or if a required table is malformed.
    """
    raise NotImplementedError("Implement per handover §11 step 3.")
