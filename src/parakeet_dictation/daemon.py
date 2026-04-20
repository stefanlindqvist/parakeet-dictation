"""Main daemon loop. Wires hotkey → audio → VAD → ASR → fixups → paste.

See handover §8d for lifecycle rules:
- ``asyncio`` main loop.
- ``pynput`` runs its own thread; bridge to asyncio via ``loop.call_soon_threadsafe``.
- Log every transcription with a latency breakdown (record / VAD / encode / decode / paste).
- Graceful shutdown on ``Ctrl+C``: stop hotkey listener, close ONNX sessions, flush log.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .asr import ParakeetAsr
from .audio import MicCapture
from .fixups import FixupEngine
from .paste import paste_to_active_window
from .vad import SileroVad

if TYPE_CHECKING:
    from .config import AppConfig

log = logging.getLogger(__name__)


class _Daemon:
    def __init__(self, config: "AppConfig") -> None:
        self.config = config
        self.loop: asyncio.AbstractEventLoop | None = None
        self.mic = MicCapture(config.audio)
        self.vad = SileroVad(config.vad)
        self.asr = ParakeetAsr(config.asr)
        self.fixups = FixupEngine(Path("vocab_fixups.json"))
        self._listener: Any | None = None
        self._stop_event: asyncio.Event | None = None
        # hold mode: pressed True while key is held.
        # toggle mode: pressed True between consecutive taps.
        self._pressed = False
        self._transcribe_lock = asyncio.Lock()

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        log.info("Loading ASR model…")
        self.asr.load()
        log.info("Warming up…")
        self.asr.warmup()
        self.vad.warmup()
        log.info("Ready. Hotkey=%s mode=%s", self.config.hotkey.key, self.config.hotkey.mode)

        self._start_hotkey_listener()
        try:
            await self._stop_event.wait()
        finally:
            self._stop_hotkey_listener()
            self.asr.close()

    def stop(self) -> None:
        if self.loop and self._stop_event:
            self.loop.call_soon_threadsafe(self._stop_event.set)

    # ------------------------------------------------------------------
    # Hotkey plumbing — pynput runs its own thread; bridge to asyncio.
    # ------------------------------------------------------------------

    def _start_hotkey_listener(self) -> None:
        from pynput import keyboard  # type: ignore[import-not-found]

        key_spec = self.config.hotkey.key
        mode = self.config.hotkey.mode

        if mode == "hold":
            hotkey = keyboard.HotKey(
                keyboard.HotKey.parse(key_spec),
                on_activate=self._on_press_threadsafe,
            )
            # pynput HotKey doesn't expose on_deactivate directly; wrap the listener.
            def _on_press(key: Any) -> None:
                listener_canonical = self._listener.canonical(key)  # type: ignore[union-attr]
                hotkey.press(listener_canonical)

            def _on_release(key: Any) -> None:
                listener_canonical = self._listener.canonical(key)  # type: ignore[union-attr]
                hotkey.release(listener_canonical)
                # Fire release when *any* part of the chord is released and we were pressed.
                if self._pressed:
                    self._on_release_threadsafe()

            self._listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        else:  # toggle
            def _toggle() -> None:
                if self._pressed:
                    self._on_release_threadsafe()
                else:
                    self._on_press_threadsafe()

            hotkey = keyboard.HotKey(keyboard.HotKey.parse(key_spec), on_activate=_toggle)

            def _on_press(key: Any) -> None:
                hotkey.press(self._listener.canonical(key))  # type: ignore[union-attr]

            def _on_release(key: Any) -> None:
                hotkey.release(self._listener.canonical(key))  # type: ignore[union-attr]

            self._listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)

        self._listener.start()

    def _stop_hotkey_listener(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _on_press_threadsafe(self) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._on_press)

    def _on_release_threadsafe(self) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._on_release)

    # ------------------------------------------------------------------
    # asyncio-side handlers
    # ------------------------------------------------------------------

    def _on_press(self) -> None:
        if self._pressed:
            return
        self._pressed = True
        try:
            self.mic.start()
            log.info("Recording…")
        except Exception as exc:
            log.exception("Failed to start mic: %s", exc)
            self._pressed = False

    def _on_release(self) -> None:
        if not self._pressed:
            return
        self._pressed = False
        if not self.mic.is_recording:
            return
        asyncio.create_task(self._finish_recording())

    async def _finish_recording(self) -> None:
        async with self._transcribe_lock:
            t0 = time.perf_counter()
            try:
                audio = self.mic.stop()
            except Exception as exc:
                log.exception("Mic stop failed: %s", exc)
                return
            t_record = time.perf_counter()

            if not audio:
                log.info("Empty recording")
                return

            try:
                trimmed = await asyncio.to_thread(self.vad.trim, audio)
            except Exception as exc:
                log.exception("VAD failed: %s", exc)
                trimmed = audio
            t_vad = time.perf_counter()

            if not trimmed:
                log.info("VAD dropped recording (no speech)")
                return

            try:
                raw_text = await asyncio.to_thread(self.asr.transcribe, trimmed)
            except Exception as exc:
                log.exception("ASR failed: %s", exc)
                return
            t_asr = time.perf_counter()

            final = self.fixups.apply(raw_text)
            t_fix = time.perf_counter()

            if not final.strip():
                log.info("Transcription was empty")
                return

            try:
                await asyncio.to_thread(
                    paste_to_active_window,
                    final,
                    restore_clipboard=self.config.paste.restore_clipboard,
                    restore_delay_ms=self.config.paste.restore_delay_ms,
                )
            except Exception as exc:
                log.exception("Paste failed: %s", exc)
                return
            t_paste = time.perf_counter()

            log.info(
                "Transcribed %d chars in %.0f ms (rec=%.0f vad=%.0f asr=%.0f fixup=%.1f paste=%.0f): %s",
                len(final),
                (t_paste - t0) * 1000,
                (t_record - t0) * 1000,
                (t_vad - t_record) * 1000,
                (t_asr - t_vad) * 1000,
                (t_fix - t_asr) * 1000,
                (t_paste - t_fix) * 1000,
                final,
            )


async def run(config: "AppConfig") -> None:
    """Run the dictation daemon until interrupted."""
    daemon = _Daemon(config)
    try:
        await daemon.run()
    except asyncio.CancelledError:
        pass
    finally:
        daemon.stop()
