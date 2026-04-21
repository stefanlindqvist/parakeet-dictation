"""Tests for :mod:`parakeet_dictation.events` and the Claude hook script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from parakeet_dictation.config import CorpusConfig
from parakeet_dictation.events import EventLogger


_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOK_PATH = _REPO_ROOT / "scripts" / "claude_hook.py"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_event_logger_disabled_does_not_write(tmp_path: Path) -> None:
    cfg = CorpusConfig(enabled=False, events_file=str(tmp_path / "events.jsonl"))
    logger = EventLogger(cfg)
    logger.log_dictation(raw="x", fixed="y", audio_ms=1000, stages={"asr_ms": 10})
    assert not (tmp_path / "events.jsonl").exists()
    assert logger.enabled is False


def test_event_logger_writes_dictation_record(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    cfg = CorpusConfig(enabled=True, events_file=str(path))
    logger = EventLogger(cfg)
    logger.log_dictation(
        raw="install the dependable workflow",
        fixed="install the Dependabot workflow",
        audio_ms=15234,
        stages={"vad_ms": 42.1, "asr_ms": 309.4},
        fixup_hits=2,
    )
    records = _read_jsonl(path)
    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "dictation"
    assert rec["raw"] == "install the dependable workflow"
    assert rec["fixed"] == "install the Dependabot workflow"
    assert rec["audio_ms"] == 15234
    assert rec["stages"] == {"vad_ms": 42.1, "asr_ms": 309.4}
    assert rec["fixup_hits"] == 2
    assert "ts" in rec and rec["ts"].endswith("+00:00")


def test_event_logger_creates_parent_dir(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "folder" / "events.jsonl"
    cfg = CorpusConfig(enabled=True, events_file=str(path))
    logger = EventLogger(cfg)
    logger.log_dictation(raw="a", fixed="a", audio_ms=100, stages={})
    assert path.exists()


def test_event_logger_appends_across_calls(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    cfg = CorpusConfig(enabled=True, events_file=str(path))
    logger = EventLogger(cfg)
    for i in range(3):
        logger.log_dictation(raw=f"r{i}", fixed=f"f{i}", audio_ms=i * 100, stages={})
    records = _read_jsonl(path)
    assert [r["raw"] for r in records] == ["r0", "r1", "r2"]


def test_event_logger_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    cfg = CorpusConfig(enabled=True, events_file=str(path))
    logger = EventLogger(cfg)
    swedish = "Kan du hjälpa mig med RAG-pipelinen?"
    logger.log_dictation(raw=swedish, fixed=swedish, audio_ms=5000, stages={})
    records = _read_jsonl(path)
    assert records[0]["raw"] == swedish


def _run_hook(payload: str, events_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH), str(events_file)],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )


def test_hook_appends_submit_record(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    payload = json.dumps(
        {
            "session_id": "sess-1",
            "transcript_path": "/tmp/x.jsonl",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Install the Dependabot workflow.",
            "cwd": "D:/ClaudeProjects/Dictation",
        }
    )
    result = _run_hook(payload, events)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    records = _read_jsonl(events)
    assert len(records) == 1
    assert records[0]["kind"] == "submit"
    assert records[0]["prompt"] == "Install the Dependabot workflow."
    assert records[0]["session_id"] == "sess-1"
    assert records[0]["cwd"] == "D:/ClaudeProjects/Dictation"


def test_hook_ignores_empty_prompt(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    result = _run_hook(json.dumps({"prompt": "   "}), events)
    assert result.returncode == 0
    assert not events.exists()


def test_hook_survives_malformed_payload(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    result = _run_hook("not-json", events)
    assert result.returncode == 0, "hook must not block the user's prompt"
    assert not events.exists()
    assert "could not parse" in result.stderr


def test_hook_survives_empty_stdin(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    result = _run_hook("", events)
    assert result.returncode == 0
    assert not events.exists()
