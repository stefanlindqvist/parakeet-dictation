"""Claude Code ``UserPromptSubmit`` hook — captures the final-submitted prompt.

Registered via ``~/.claude/settings.json`` (user-global) so it fires across
every Claude Code session regardless of project. The hook reads the JSON
payload Claude Code sends on stdin and appends one line to the same
``training_data/events.jsonl`` the daemon writes to — the correction-mining
script pairs ``dictation`` records with ``submit`` records by time + text
similarity.

Schema written (see ``events.py`` for the daemon-side counterpart)::

    {"kind": "submit",
     "ts": "2026-04-21T10:32:42.987654+00:00",
     "prompt": "Install the Dependabot workflow…",
     "cwd": "D:/ClaudeProjects/Dictation",
     "session_id": "…",
     "transcript_path": "…"}

Design constraints
------------------
- Stdlib only: this runs in whatever Python is on PATH when Claude Code fires
  it, not necessarily the parakeet-dictation venv.
- **Never block the user's prompt.** Any failure — bad JSON, locked file,
  missing path — is caught, logged to stderr, and followed by ``exit 0``.
  An exit-2 from this hook would swallow your actual prompt.
- **Emit nothing on stdout.** Claude Code treats hook stdout as additional
  prompt context; staying silent keeps the conversation clean.

Wiring (user-global)
--------------------
In ``%USERPROFILE%\\.claude\\settings.json``::

    {
      "hooks": {
        "UserPromptSubmit": [
          {
            "hooks": [
              {
                "type": "command",
                "command": "python D:\\\\ClaudeProjects\\\\Dictation\\\\scripts\\\\claude_hook.py D:\\\\ClaudeProjects\\\\Dictation\\\\training_data\\\\events.jsonl"
              }
            ]
          }
        ]
      }
    }

Usage::

    python scripts/claude_hook.py <events_file> < payload.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _eprint(msg: str) -> None:
    """stderr-only logging — anything on stdout would become prompt context."""
    print(f"[claude_hook] {msg}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Claude Code UserPromptSubmit hook — append submitted prompt to events.jsonl"
    )
    parser.add_argument(
        "events_file",
        type=Path,
        help="Path to the shared training_data/events.jsonl",
    )
    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _eprint(f"could not parse stdin JSON: {exc}")
        return 0

    prompt = payload.get("prompt") or ""
    if not prompt.strip():
        return 0

    record = {
        "kind": "submit",
        "ts": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "cwd": payload.get("cwd"),
        "session_id": payload.get("session_id"),
        "transcript_path": payload.get("transcript_path"),
    }

    try:
        args.events_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with args.events_file.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.write("\n")
    except OSError as exc:
        _eprint(f"could not append to {args.events_file}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
