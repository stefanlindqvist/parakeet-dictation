"""Main daemon loop. Wires hotkey → audio → VAD → ASR → fixups → paste.

See handover §8d for lifecycle rules:
- ``asyncio`` main loop.
- ``pynput`` runs its own thread; bridge to asyncio via ``loop.call_soon_threadsafe``.
- Log every transcription with a latency breakdown (record / VAD / encode / decode / paste).
- Graceful shutdown on ``Ctrl+C``: stop hotkey listener, close ONNX sessions, flush log.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import AppConfig


async def run(config: "AppConfig") -> None:
    """Run the dictation daemon until interrupted.

    Implement per handover §11 step 9.
    """
    raise NotImplementedError("Implement per handover §11 step 9.")
