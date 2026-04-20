"""Tests for ``parakeet_dictation.config``."""

from __future__ import annotations

from pathlib import Path

import pytest

from parakeet_dictation.config import AppConfig, ConfigError, load_config


def test_load_config_returns_appconfig(sample_config_toml: Path) -> None:
    cfg = load_config(sample_config_toml)
    assert isinstance(cfg, AppConfig)
    assert cfg.hotkey.mode == "hold"
    assert cfg.audio.sample_rate == 16000
    assert cfg.vad.threshold == 0.5
    assert cfg.asr.encoder_provider == "DmlExecutionProvider"
    assert cfg.asr.decoder_provider == "CPUExecutionProvider"
    assert cfg.paste.restore_clipboard is True
    assert cfg.logging.level == "INFO"


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "does-not-exist.toml")


def test_load_config_invalid_toml(tmp_path: Path) -> None:
    bad = tmp_path / "config.toml"
    bad.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_config(bad)


def test_load_config_invalid_value(tmp_path: Path) -> None:
    bad = tmp_path / "config.toml"
    bad.write_text('[hotkey]\nmode = "invalid"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid config"):
        load_config(bad)


def test_load_config_defaults_when_tables_omitted(tmp_path: Path) -> None:
    minimal = tmp_path / "config.toml"
    minimal.write_text("", encoding="utf-8")
    cfg = load_config(minimal)
    assert cfg.hotkey.mode == "hold"
    assert cfg.asr.encoder_provider == "DmlExecutionProvider"
