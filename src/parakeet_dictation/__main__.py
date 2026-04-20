"""Entry point: ``python -m parakeet_dictation``.

Wires config loading, daemon startup, and graceful shutdown. See handover §8d.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "Implement per handover §11 step 10: load config, start daemon.run(), "
        "handle Ctrl+C for graceful shutdown."
    )


if __name__ == "__main__":
    main()
