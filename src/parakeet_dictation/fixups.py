"""Post-transcription regex substitutions driven by ``vocab_fixups.json``.

See handover §7 for the seed dictionary and §8 for semantics: substitutions are
ordered (longer phrases before single words), compiled once at startup, applied
in order on every transcript.
"""

from __future__ import annotations

from pathlib import Path


class FixupEngine:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def apply(self, text: str) -> str:
        """Return ``text`` with all substitutions applied in order.

        Implement per handover §11 step 5.
        """
        raise NotImplementedError("Implement per handover §11 step 5.")
