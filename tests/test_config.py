"""Tests for ``parakeet_dictation.config``."""

from __future__ import annotations

from pathlib import Path

import pytest

from parakeet_dictation.config import AppConfig, load_config


@pytest.mark.skip(reason="Implement alongside parakeet_dictation.config.load_config (handover §11 step 3)")
def test_load_config_returns_appconfig(sample_config_toml: Path) -> None:
    cfg = load_config(sample_config_toml)
    assert isinstance(cfg, AppConfig)
    assert cfg.audio.sample_rate == 16000
    assert cfg.asr.encoder_provider == "DmlExecutionProvider"
    assert cfg.asr.decoder_provider == "CPUExecutionProvider"
