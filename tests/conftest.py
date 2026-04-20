"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_config_toml(tmp_path: Path) -> Path:
    """A minimal config.toml on disk at ``tmp_path / 'config.toml'``."""
    path = tmp_path / "config.toml"
    path.write_text(
        """
[hotkey]
mode = "hold"
key = "<cmd>+`"

[audio]
sample_rate = 16000
device_index = -1
silence_timeout_ms = 1200

[vad]
enabled = true
threshold = 0.5
min_speech_ms = 200

[asr]
model_path = "./models/parakeet-tdt-0.6b-v3"
language = "auto"
encoder_provider = "DmlExecutionProvider"
decoder_provider = "CPUExecutionProvider"

[paste]
restore_clipboard = true
restore_delay_ms = 500

[logging]
level = "INFO"
file = "./parakeet-dictation.log"
""".strip(),
        encoding="utf-8",
    )
    return path
