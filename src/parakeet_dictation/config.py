"""Typed config loader for ``config.toml``. See handover §6 for the full schema."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


class HotkeyConfig(BaseModel):
    mode: Literal["hold", "toggle"] = "hold"
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


class CorpusConfig(BaseModel):
    """Structured JSONL event log. Paired with Claude Code's UserPromptSubmit
    hook to mine (raw transcript, final submitted prompt) pairs for fixups.
    See handover §10 / README 'Training data'."""

    enabled: bool = True
    events_file: str = "./training_data/events.jsonl"


class AppConfig(BaseModel):
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    paste: PasteConfig = Field(default_factory=PasteConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    corpus: CorpusConfig = Field(default_factory=CorpusConfig)


class ConfigError(RuntimeError):
    """Raised when ``config.toml`` is missing or malformed."""


def load_config(path: Path | str = Path("config.toml")) -> AppConfig:
    """Parse ``config.toml`` from disk into an :class:`AppConfig`."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config in {path}:\n{exc}") from exc
