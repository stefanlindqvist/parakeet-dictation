"""Tests for ``parakeet_dictation.fixups``."""

from __future__ import annotations

from pathlib import Path

import pytest

from parakeet_dictation.fixups import FixupEngine


@pytest.mark.skip(reason="Implement alongside parakeet_dictation.fixups.FixupEngine (handover §11 step 5)")
def test_fixups_apply_known_patterns() -> None:
    engine = FixupEngine(Path("vocab_fixups.json"))
    assert engine.apply("install the dependabot workflow") == "install the Dependabot workflow"
    assert engine.apply("configure pg vector and q drant") == "configure pgvector and Qdrant"
    assert engine.apply("open vs code") == "open VS Code"
