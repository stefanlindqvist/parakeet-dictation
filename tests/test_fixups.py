"""Tests for ``parakeet_dictation.fixups``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakeet_dictation.fixups import FixupEngine

VOCAB_FIXUPS = Path(__file__).resolve().parent.parent / "vocab_fixups.json"


def test_fixups_apply_known_patterns() -> None:
    engine = FixupEngine(VOCAB_FIXUPS)
    assert engine.apply("install the dependabot workflow") == "install the Dependabot workflow"
    assert engine.apply("configure pg vector and q drant") == "configure pgvector and Qdrant"
    assert engine.apply("open vs code") == "open VS Code"


def test_fixups_apply_multiple_terms_one_pass() -> None:
    engine = FixupEngine(VOCAB_FIXUPS)
    out = engine.apply("deploy cue bit torrent next to gleeton and sin ology")
    assert "qBittorrent" in out
    assert "Gluetun" in out
    assert "Synology" in out


def test_fixups_are_case_insensitive_on_match() -> None:
    engine = FixupEngine(VOCAB_FIXUPS)
    assert engine.apply("JSON and YAML and DSM") == "JSON and YAML and DSM"
    assert engine.apply("json and yaml") == "JSON and YAML"


def test_fixups_leave_unrelated_text_alone() -> None:
    engine = FixupEngine(VOCAB_FIXUPS)
    text = "this is just some ordinary prose without any keywords"
    assert engine.apply(text) == text


def test_fixups_rule_count_matches_file() -> None:
    engine = FixupEngine(VOCAB_FIXUPS)
    raw = json.loads(VOCAB_FIXUPS.read_text(encoding="utf-8"))
    assert engine.rule_count == len(raw["substitutions"])


def test_fixups_invalid_regex_raises(tmp_path: Path) -> None:
    bad = tmp_path / "fixups.json"
    bad.write_text(
        json.dumps({"substitutions": [{"pattern": "(unclosed", "replacement": "x"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid regex"):
        FixupEngine(bad)


def test_fixups_non_string_entries_raise(tmp_path: Path) -> None:
    bad = tmp_path / "fixups.json"
    bad.write_text(
        json.dumps({"substitutions": [{"pattern": 42, "replacement": "x"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be strings"):
        FixupEngine(bad)
