"""Structured JSONL event log for training-data mining.

Produces the ``training_data/events.jsonl`` file that ``scripts/claude_hook.py``
also appends to. The two records share a file and are joined later by the
correction-mining script.

Schema
------
Every line is a single JSON object with a ``kind`` discriminator:

- ``kind="dictation"`` — emitted by the daemon after every successful paste::

    {
      "kind": "dictation",
      "ts": "2026-04-21T10:32:15.123456+00:00",
      "raw": "install the dependable workflow...",
      "fixed": "install the Dependabot workflow...",
      "audio_ms": 15234,
      "stages": {"record_ms": 25, "vad_ms": 42, "asr_ms": 309, "fixup_ms": 0.2, "paste_ms": 24},
      "fixup_hits": 3
    }

- ``kind="submit"`` — emitted by the Claude Code ``UserPromptSubmit`` hook::

    {
      "kind": "submit",
      "ts": "2026-04-21T10:32:42.987654+00:00",
      "prompt": "Install the Dependabot workflow for the fitnesscoach repo...",
      "cwd": "D:/ClaudeProjects/Dictation",
      "session_id": "...",
      "transcript_path": "..."
    }

Write discipline
----------------
- One JSON object per line (``ensure_ascii=False`` so Swedish survives).
- Opened in append mode on every write so multiple processes (daemon + hook +
  ad-hoc tools) can coexist; POSIX-style appends of < PIPE_BUF are atomic and
  Windows' NTFS behaves similarly for short lines, which these are.
- Failures to log never propagate — the daemon keeps running; we just emit a
  warning and move on.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import CorpusConfig

log = logging.getLogger(__name__)


class EventLogger:
    def __init__(self, config: "CorpusConfig") -> None:
        self._config = config
        self._path = Path(config.events_file)
        self._ready = False
        if config.enabled:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._ready = True
            except OSError as exc:
                log.warning("Could not create events dir %s: %s", self._path.parent, exc)

    @property
    def enabled(self) -> bool:
        return self._ready

    @property
    def path(self) -> Path:
        return self._path

    def log_dictation(
        self,
        raw: str,
        fixed: str,
        audio_ms: int,
        stages: dict[str, float],
        fixup_hits: int | None = None,
    ) -> None:
        if not self._ready:
            return
        record = {
            "kind": "dictation",
            "ts": datetime.now(timezone.utc).isoformat(),
            "raw": raw,
            "fixed": fixed,
            "audio_ms": int(audio_ms),
            "stages": {k: round(float(v), 2) for k, v in stages.items()},
        }
        if fixup_hits is not None:
            record["fixup_hits"] = int(fixup_hits)
        self._append(record)

    def _append(self, record: dict) -> None:
        try:
            line = json.dumps(record, ensure_ascii=False)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")
        except OSError as exc:
            log.warning("Events log append failed (%s): %s", self._path, exc)
