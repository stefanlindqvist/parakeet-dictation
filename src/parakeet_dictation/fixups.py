"""Post-transcription regex substitutions driven by ``vocab_fixups.json``.

See handover §7 for the seed dictionary and §8 for semantics: substitutions are
ordered (longer phrases before single words), compiled once at startup, applied
in order on every transcript.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class FixupEngine:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._rules: list[tuple[re.Pattern[str], str]] = self._load(self._path)

    @staticmethod
    def _load(path: Path) -> list[tuple[re.Pattern[str], str]]:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        subs = raw.get("substitutions", [])
        rules: list[tuple[re.Pattern[str], str]] = []
        for idx, entry in enumerate(subs):
            pattern = entry.get("pattern")
            replacement = entry.get("replacement")
            if not isinstance(pattern, str) or not isinstance(replacement, str):
                raise ValueError(
                    f"vocab_fixups.json entry {idx}: both 'pattern' and 'replacement' must be strings"
                )
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(
                    f"vocab_fixups.json entry {idx}: invalid regex {pattern!r}: {exc}"
                ) from exc
            rules.append((compiled, replacement))
        return rules

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def apply(self, text: str) -> str:
        """Return ``text`` with all substitutions applied in order."""
        for pattern, replacement in self._rules:
            text = pattern.sub(replacement, text)
        return text
